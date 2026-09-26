"""Free providers chained over the OpenAI-compatible API: quota fallback, JSON handling, offline fallback."""
import asyncio
import dataclasses
import json

import httpx

from sales_pipeline.openai_compat import PROVIDERS, ChainBackend, OpenAICompatBackend, build_chain, parse_overrides
from sales_pipeline.relevance import Chunk
from sales_pipeline.schemas import CompanyInfo, QuestionSpec

COMPANY = CompanyInfo(name="Electrica", country="RO")
QUESTION = QuestionSpec(key="q:1", text="Has the company suffered a security incident?")
CHUNK = Chunk(doc_index=0, title="Atac cibernetic", text="Atac cibernetic la Electrica, sistemele esentiale nu sunt afectate.",
              url="https://news.example/1", date="2026-09-20", source_type="news")
ANSWER = {"answers": [{"key": "q:1", "answer": "yes", "confidence": 0.9, "reasoning": "r",
                       "evidence": [{"quote": "Atac cibernetic la Electrica", "doc_id": "D1"}]}]}


def fast(p):
    return dataclasses.replace(p, min_interval=0.0)


def backend(name, handler):
    return OpenAICompatBackend(fast(PROVIDERS[name]), "key", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


def run(chain, *args):
    return asyncio.run(chain.answer_questions(*args))


def test_a_provider_over_its_quota_hands_over_to_the_next():
    calls = []

    def gemini(req):
        calls.append("gemini")
        return httpx.Response(429, text="Resource has been exhausted (e.g. check quota) per day")

    def groq(req):
        calls.append("groq")
        return ok(json.dumps(ANSWER))

    chain = ChainBackend([backend("gemini", gemini), backend("groq", groq)])
    answers, _ = run(chain, COMPANY, [QUESTION], [CHUNK])
    assert answers[0].answer == "yes" and answers[0].evidence[0].url == "https://news.example/1"
    run(chain, COMPANY, [QUESTION], [CHUNK])
    assert calls == ["gemini", "groq", "groq"]  # gemini stays skipped during its cooldown
    assert chain.used == {"groq": 2}


def test_when_every_provider_is_down_the_offline_heuristic_answers():
    down = lambda req: httpx.Response(503, text="overloaded")  # noqa: E731
    chain = ChainBackend([backend("gemini", down), backend("groq", down)])
    answers, _ = run(chain, COMPANY, [QUESTION], [CHUNK])
    assert chain.used == {"heuristic": 1} and answers[0].key == "q:1"


def test_json_schema_rejected_falls_back_to_a_json_object_in_fences():
    formats = []

    def handler(req):
        body = json.loads(req.content)
        formats.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, text="response_format json_schema not supported")
        return ok("```json\n" + json.dumps(ANSWER) + "\n```")

    b = backend("nvidia", handler)
    answers, usage = asyncio.run(b.answer_questions(COMPANY, [QUESTION], [CHUNK]))
    assert answers[0].answer == "yes" and usage.input_tokens == 10 and usage.cost_usd == 0
    asyncio.run(b.answer_questions(COMPANY, [QUESTION], [CHUNK]))
    assert formats == ["json_schema", "json_object", "json_object"]  # remembered


def test_only_providers_with_a_key_join_the_chain_and_models_can_be_overridden():
    chain = build_chain({"groq": "k", "gemini": "k"}, overrides="groq=openai/gpt-oss-120b|openai/gpt-oss-20b", ollama_available=False)
    assert [b.name for b in chain.backends] == ["gemini", "groq"]  # chain order, not key order; no key -> left out
    groq = chain.backends[1]
    assert (groq.model, groq.small_model) == ("openai/gpt-oss-120b", "openai/gpt-oss-20b")
    assert build_chain({}, chain=("gemini", "groq")) is None
    assert [b.name for b in build_chain({}, ollama_available=True).backends] == ["ollama"]  # local, no key needed
    assert parse_overrides("gemini=gemini-3.5-flash") == {"gemini": ("gemini-3.5-flash", None)}


def test_a_busy_gemini_model_hands_over_to_its_other_models_first():
    models = []

    def handler(req):
        m = json.loads(req.content)["model"]
        models.append(m)
        return httpx.Response(503, text="high demand") if m == "gemini-3.5-flash" else ok(json.dumps(ANSWER))

    chain = ChainBackend([backend("gemini", handler)])
    answers, _ = run(chain, COMPANY, [QUESTION], [CHUNK])
    assert answers[0].answer == "yes" and chain.used == {"gemini": 1}
    assert models == ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
