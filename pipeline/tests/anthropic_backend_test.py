"""AnthropicBackend request/response handling through the real SDK with a mocked transport."""
import asyncio
import json

import anthropic
import httpx2

from sales_pipeline import AnthropicBackend, CompanyInfo, QuestionSpec
from sales_pipeline.relevance import Chunk

CHUNK = Chunk(doc_index=0, url="https://news.example/1", title="Acme automation", date="2026-09-01", source_type="news",
              text="Acme Logistics launched a group-wide automation programme to cut costs.")


def make_backend(reply: dict, captured: list):
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        captured.append({"headers": dict(request.headers), "body": body, "path": request.url.path})
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": json.dumps(reply)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 200},
        })

    client = anthropic.AsyncAnthropic(api_key="test-key", http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    return AnthropicBackend(client=client)


def test_answer_questions_request_and_parsing():
    captured = []
    reply = {"answers": [{"key": "q:1", "answer": "yes", "confidence": 0.85,
                          "evidence": [{"quote": "launched a group-wide automation programme", "doc_id": "D1"}], "reasoning": "Explicit programme."}]}
    backend = make_backend(reply, captured)
    answers, usage = asyncio.run(backend.answer_questions(
        CompanyInfo(name="Acme Logistics"), [QuestionSpec(key="q:1", text="Automation initiatives?"), QuestionSpec(key="q:2", text="Hiring RPA?")], [CHUNK]))
    req = captured[0]
    assert req["body"]["model"] == "claude-opus-5"
    assert req["body"]["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req["headers"]["anthropic-beta"]
    assert req["body"]["output_config"]["format"]["type"] == "json_schema"
    assert req["body"]["output_config"]["effort"] == "medium"
    assert "[D1]" in req["body"]["messages"][0]["content"]
    assert answers[0].answer == "yes" and answers[0].evidence[0].url == CHUNK.url and answers[0].evidence[0].date == "2026-09-01"
    assert answers[1].answer == "unknown"  # key missing from the model's reply
    assert usage.cost_usd == round((1000 * 5 + 200 * 25) / 1e6, 6)


def test_event_classification_uses_small_model_without_fallbacks():
    captured = []
    reply = {"events": [{"doc_id": "D1", "event_type": "tech_stack", "subtype": "automation", "title": "Acme automation programme",
                         "summary": "s", "entities": ["UiPath"], "polarity": "positive"}]}
    events, _ = asyncio.run(make_backend(reply, captured).classify_events(CompanyInfo(name="Acme"), [CHUNK]))
    body = captured[0]["body"]
    assert body["model"] == "claude-haiku-4-5" and "fallbacks" not in body and "effort" not in body["output_config"]
    assert events[0].url == CHUNK.url and events[0].event_type == "tech_stack"
