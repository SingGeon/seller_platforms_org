"""Business-press feeds (one request per outlet) and Bing News per company."""
import asyncio

import httpx

from sales_pipeline.collectors.news import fetch_bing_news
from sales_pipeline.documents import Document
from sales_pipeline.schemas import CompanyInfo
from sales_pipeline.sources.localnews import CompanyMatcher, Feed, fetch_feed

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{items}</channel></rss>"""
ITEM = "<item><title>{title}</title><link>{link}</link><description>{desc}</description><pubDate>Fri, 25 Sep 2026 08:19:00 GMT</pubDate></item>"


def doc(title, text=""):
    return Document(source_type="news", url=f"https://x.example/{abs(hash(title))}", title=title, text=text)


def test_matcher_needs_whole_words_and_exact_case_for_one_word_names():
    m = CompanyMatcher([(1, "Digi Communications N.V."), (2, "Catena"), (3, "Banca Transilvania S.A."), (4, "BT")])
    assert m.match(doc("Digi Communications raportează profit")) == [1]
    assert m.match(doc("Catena deschide 20 de farmacii")) == [2]
    assert m.match(doc("o catena de magazine")) == []  # ordinary word, not the brand
    assert m.match(doc("Catenaccio în fotbal")) == []  # not a whole word
    assert m.match(doc("BANCA TRANSILVANIA lansează un credit")) == [3]  # multi-word: case-insensitive
    assert m.match(doc("BT anunță")) == []  # names under 4 characters are skipped for bulk matching


def test_matcher_skips_one_word_names_that_are_usually_people():
    m = CompanyMatcher([(1, "Roman S.A."), (2, "Dacia S.A.")])
    assert m.match(doc("Inspectorul Roman Popescu, depistat cu avere nejustificată")) == []
    assert m.match(doc("Dacia lansează noul Bigster")) == [2]


def test_wordpress_feed_is_paged_until_empty():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("paged", "1"))
        pages.append(page)
        items = "" if page > 2 else ITEM.format(title=f"Catena p{page}", link=f"https://zdg.example/{page}", desc="d")
        return httpx.Response(200, text=RSS.format(items=items))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_feed(client, Feed("ZdG", "https://zdg.example/feed/", ("MD",), paged=True), pages=5)

    docs = asyncio.run(go())
    assert [d.url for d in docs] == ["https://zdg.example/1", "https://zdg.example/2"] and pages == [1, 2, 3]
    assert docs[0].meta["provider"] == "local_rss" and docs[0].source == "ZdG"


def test_bing_news_keeps_the_publisher_url_and_source():
    link = "http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.forbes.ro%2fdigi-dividende&amp;c=1"
    body = RSS.format(items=ITEM.format(title="Digi România va distribui dividende", link=link, desc="Forbes").replace(
        "</item>", "<News:Source xmlns:News='https://www.bing.com/news/search?q=x&amp;format=rss'>Forbes România</News:Source></item>"))
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, text=body)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_bing_news(client, CompanyInfo(id=1, name="Digi România S.A.", country="RO"))

    docs = asyncio.run(go())
    assert "cc=RO" in seen["url"] and "setlang=ro" in seen["url"]
    assert docs[0].url == "https://www.forbes.ro/digi-dividende"
    assert docs[0].published_at is not None and docs[0].meta["provider"] == "bing_news_rss"


def test_heuristic_understands_romanian_news():
    from sales_pipeline import HeuristicBackend
    from sales_pipeline.relevance import Chunk
    from sales_pipeline.schemas import QuestionSpec

    chunks = [Chunk(doc_index=0, url="https://ro.example/1", title="Atac", date="2026-09-20", source_type="news",
                    text="Compania a fost victima unui atac cibernetic cu ransomware, iar o parte din datele clienților a fost furată.")]
    q = QuestionSpec(key="q:1", text="Has the company suffered a recent security incident, data breach or ransomware attack?",
                     keywords=["data breach", "ransomware", "cyberattack", "security incident"])
    answers, _ = asyncio.run(HeuristicBackend().answer_questions(None, [q], chunks))
    assert answers[0].answer == "yes" and "atac cibernetic" in answers[0].evidence[0].quote

    events, _ = asyncio.run(HeuristicBackend().classify_events(None, [
        *chunks,
        Chunk(doc_index=1, url="https://ro.example/2", title="Numire", date="2026-09-21", source_type="news",
              text="Maria Popescu a fost numită director general al companiei începând cu 1 octombrie."),
    ]))
    assert {e.event_type for e in events} == {"security_incident", "leadership_change"}
