import asyncio
from datetime import datetime, timedelta, timezone

from sales_pipeline import Answer, CompanyInfo, Document, Evidence, HeuristicBackend, MemoryCache, QuestionSpec, Usage, dedupe, run_signal_pipeline
from sales_pipeline.collectors import categorize_role, detect_tech_stack
from sales_pipeline.collectors.web import url_priority
from sales_pipeline.evidence import validate_answer
from sales_pipeline.relevance import Chunk, select_chunks

NOW = datetime.now(timezone.utc)
COMPANY = CompanyInfo(name="Acme Logistics", domain="acme.example")
DOCS = [
    Document(source_type="news", url="https://news.example/1", title="Acme launches automation programme",
             text="Acme Logistics launched a group-wide automation programme to cut costs and improve operational efficiency.", published_at=NOW - timedelta(days=5)),
    Document(source_type="jobs", url="https://jobs.example/rpa", title="RPA Developer", text="Job posting at Acme: RPA Developer (UiPath).", published_at=NOW - timedelta(days=3)),
    Document(source_type="news", url="https://news.example/old", title="Acme hit by ransomware", text="Acme Logistics was hit by a ransomware attack.", published_at=NOW - timedelta(days=900)),
]
QUESTIONS = [
    QuestionSpec(key="q:1", text="Does the company mention automation initiatives?", keywords=["automation", "operational efficiency", "cut costs"]),
    QuestionSpec(key="q:2", text="Is the company hiring RPA developers?", source_hint="jobs", keywords=["rpa", "uipath"]),
    QuestionSpec(key="q:3", text="Recent breach?", source_hint="news", lookback_days=365, keywords=["ransomware", "breach"]),
]


class FakeLLM:
    """Records calls; hallucinates a quote for q:1 to exercise evidence validation."""

    name = model = small_model = "fake"

    def __init__(self):
        self.answer_calls = 0

    async def answer_questions(self, company, questions, chunks):
        self.answer_calls += 1
        out = []
        for q in questions:
            if q.key == "q:1":
                out.append(Answer(key=q.key, answer="yes", confidence=0.9, evidence=[Evidence(quote="Acme will fire half of its staff next year", url=chunks[0].url)]))
            else:
                c = next(c for c in chunks if c.source_type == "jobs")
                out.append(Answer(key=q.key, answer="yes", confidence=0.8, evidence=[Evidence(quote=c.text[:60], url=c.url)]))
        return out, Usage(input_tokens=100, output_tokens=10, llm_calls=1, cost_usd=0.001)

    async def classify_events(self, company, chunks):
        return [], Usage(llm_calls=1)


def test_dedupe_by_url_and_title():
    docs = [
        Document(source_type="news", url="https://a.example/x?utm_source=feed", title="Acme appoints new CIO to lead digital transformation"),
        Document(source_type="news", url="https://a.example/x", title="dupe"),
        Document(source_type="news", url="https://b.example/y", title="Acme appoints new CIO to lead digital transformation!"),
        Document(source_type="news", url="https://c.example/z", title="Something else entirely about Acme"),
    ]
    assert [d.url for d in dedupe(docs)] == ["https://a.example/x?utm_source=feed", "https://c.example/z"]


def test_relevance_respects_source_hint_and_lookback():
    assert {c.url for c in select_chunks(DOCS, QUESTIONS[1])} == {"https://jobs.example/rpa"}
    assert select_chunks(DOCS, QUESTIONS[2]) == []  # the ransomware story is 900 days old


def test_evidence_validation_rejects_fabricated_quotes():
    chunk = Chunk(doc_index=0, url="https://news.example/1", title="t", date="2026-01-01", source_type="news", text=DOCS[0].text)
    good = Answer(key="q", answer="yes", confidence=0.9, evidence=[Evidence(quote="launched a group-wide automation programme", url="https://news.example/1")])
    assert validate_answer(good, [chunk]).answer == "yes"
    assert validate_answer(good, [chunk]).evidence[0].date == "2026-01-01"
    fake = Answer(key="q", answer="yes", confidence=0.9, evidence=[Evidence(quote="Acme signed a contract with Orange Systems", url="https://news.example/1")])
    out = validate_answer(fake, [chunk])
    assert out.answer == "unknown" and out.confidence == 0 and not out.evidence
    wrong_url = Answer(key="q", answer="no", confidence=0.9, evidence=[Evidence(quote="launched a group-wide automation programme", url="https://other.example")])
    assert validate_answer(wrong_url, [chunk]).answer == "unknown"


def test_graph_end_to_end_batches_validates_and_caches():
    llm, cache = FakeLLM(), MemoryCache()
    res = asyncio.run(run_signal_pipeline(llm, COMPANY, QUESTIONS, DOCS, cache=cache))
    by_key = {a.key: a for a in res.answers}
    assert by_key["q:1"].answer == "unknown"  # hallucinated quote dropped
    assert by_key["q:2"].answer == "yes" and by_key["q:2"].evidence[0].url == "https://jobs.example/rpa"
    assert by_key["q:3"].answer == "unknown" and "No relevant documents" in by_key["q:3"].reasoning
    assert llm.answer_calls == 1  # q:1 and q:2 batched in one call
    assert res.usage.cost_usd == 0.001
    asyncio.run(run_signal_pipeline(llm, COMPANY, QUESTIONS, DOCS, cache=cache))
    assert llm.answer_calls == 1  # second run served from cache


def test_batched_answer_cannot_cite_other_questions_passages():
    class CrossCiting(FakeLLM):
        async def answer_questions(self, company, questions, chunks):
            news = next(c for c in chunks if c.source_type == "news")
            return [Answer(key=q.key, answer="yes", confidence=0.9, evidence=[Evidence(quote=news.text[:60], url=news.url)]) for q in questions], Usage()

    res = asyncio.run(run_signal_pipeline(CrossCiting(), COMPANY, QUESTIONS[:2], DOCS))
    by_key = {a.key: a for a in res.answers}
    assert by_key["q:1"].answer == "yes"
    assert by_key["q:2"].answer == "unknown"  # jobs-only question may not cite a news article


def test_heuristic_backend_runs_offline():
    res = asyncio.run(run_signal_pipeline(HeuristicBackend(), COMPANY, QUESTIONS, DOCS))
    assert {a.key: a.answer for a in res.answers} == {"q:1": "yes", "q:2": "yes", "q:3": "unknown"}


def test_role_categorization_and_tech_stack():
    assert categorize_role("Senior RPA Developer (UiPath)") == ["RPA"]
    assert "AI/ML" in categorize_role("Machine Learning Engineer")
    assert "Security" in categorize_role("SOC Analyst - Cyber Defense")
    assert categorize_role("Truck Driver") == []
    html = '<script src="https://js.hs-scripts.com/1.js"></script><link href="/etc.clientlibs/site.css"> SAP S/4HANA'
    assert detect_tech_stack(html) == ["Adobe Experience Manager", "HubSpot", "SAP"]
    assert url_priority("https://acme.example/newsroom/2026") > url_priority("https://acme.example/products")
