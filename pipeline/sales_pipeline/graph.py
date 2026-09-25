"""LangGraph signal-extraction flow (GIG-25):

    load_context -> relevance_filter -> answer_questions -> detect_events -> aggregate

The graph is storage-agnostic: documents and questions come in, answers and
events come out; `aggregate` hands them to an optional `on_result` callback
(the backend uses it to write `signals` / `company_events`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from .documents import Document, docs_hash
from .evidence import validate_answer
from .llm import Cache, LLMBackend, MemoryCache, cache_key
from .relevance import Chunk, select_chunks, split_chunks
from .schemas import Answer, CompanyInfo, DetectedEvent, PipelineResult, QuestionSpec, Usage

log = logging.getLogger(__name__)

MAX_CHUNKS_PER_CALL = 30
EVENT_BATCH = 15


class SignalState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    company: CompanyInfo
    questions: list[QuestionSpec]
    documents: list[Document] = Field(default_factory=list)
    detect_events: bool = True
    chunks_by_question: dict[str, list[Chunk]] = Field(default_factory=dict)
    answers: list[Answer] = Field(default_factory=list)
    events: list[DetectedEvent] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    errors: list[str] = Field(default_factory=list)


async def _with_retry(fn: Callable[[], Awaitable[Any]], attempts: int = 3, base_delay: float = 2.0) -> Any:
    """Retry on transient LLM failures. The Anthropic SDK already retries 429/5xx;
    this adds a coarser outer retry for long outages and malformed responses."""
    for attempt in range(attempts):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts - 1:
                raise
            log.warning("LLM call failed (%s), retry %d/%d", exc, attempt + 1, attempts - 1)
            await asyncio.sleep(base_delay * 2**attempt)


def build_graph(
    llm: LLMBackend,
    *,
    cache: Cache | None = None,
    on_result: Callable[[PipelineResult], Awaitable[None] | None] | None = None,
    batch_questions: bool = True,
):
    cache = cache or MemoryCache()

    async def load_context(state: SignalState) -> dict:
        # Drop empty docs; cap text so one giant annual report can't crowd out the rest.
        docs = [d.model_copy(update={"text": d.text[:60000]}) for d in state.documents if (d.text or d.title)]
        return {"documents": docs}

    async def relevance_filter(state: SignalState) -> dict:
        return {"chunks_by_question": {q.key: select_chunks(state.documents, q) for q in state.questions}}

    async def answer_questions(state: SignalState) -> dict:
        usage = Usage()
        answers: dict[str, Answer] = {}
        pending: list[QuestionSpec] = []
        for q in state.questions:
            chunks = state.chunks_by_question.get(q.key, [])
            if not chunks:
                answers[q.key] = Answer(key=q.key, answer="unknown", reasoning="No relevant documents found.")
                continue
            key = cache_key("answer", llm.model, state.company.name, q.text, q.source_hint, [c.model_dump() for c in chunks])
            hit = cache.get(key)
            if hit is not None:
                answers[q.key] = Answer.model_validate({**hit, "key": q.key})
                usage.cache_hits += 1
            else:
                pending.append(q)

        # GIG-28: several questions share one call over the union of their passages.
        groups: list[list[QuestionSpec]] = []
        if batch_questions:
            cur: list[QuestionSpec] = []
            seen: set[tuple[str, str]] = set()
            for q in pending:
                new = {(c.url, c.text[:50]) for c in state.chunks_by_question[q.key]} - seen
                if cur and len(seen) + len(new) > MAX_CHUNKS_PER_CALL:
                    groups.append(cur)
                    cur, seen = [], set()
                    new = {(c.url, c.text[:50]) for c in state.chunks_by_question[q.key]}
                cur.append(q)
                seen |= new
            if cur:
                groups.append(cur)
        else:
            groups = [[q] for q in pending]

        async def run_group(group: list[QuestionSpec]) -> tuple[list[Answer], Usage, list[Chunk]]:
            merged: list[Chunk] = []
            keys = set()
            for q in group:
                for c in state.chunks_by_question[q.key]:
                    k = (c.url, c.text[:50])
                    if k not in keys:
                        keys.add(k)
                        merged.append(c)
            result, u = await _with_retry(lambda: llm.answer_questions(state.company, group, merged))
            return result, u, merged

        errors = []
        results = await asyncio.gather(*(run_group(g) for g in groups), return_exceptions=True)
        for group, res in zip(groups, results):
            if isinstance(res, BaseException):
                errors.append(f"answer_questions failed for {[q.key for q in group]}: {res}")
                for q in group:
                    answers[q.key] = Answer(key=q.key, reasoning="LLM error; retry on next run.")
                continue
            group_answers, u, _ = res
            usage.add(u)
            group_keys = {q.key for q in group}
            for a in group_answers:
                if a.key not in group_keys:
                    continue
                own_chunks = state.chunks_by_question[a.key]
                # Validate against this question's own passages: in a batched call the model also
                # sees passages selected for other questions (e.g. news for a jobs-only question).
                validated = validate_answer(a, own_chunks)
                answers[a.key] = validated
                q = next(q for q in group if q.key == a.key)
                key = cache_key("answer", llm.model, state.company.name, q.text, q.source_hint, [c.model_dump() for c in own_chunks])
                cache.set(key, validated.model_dump())
        total = state.usage.model_copy()
        total.add(usage)
        return {"answers": [answers[q.key] for q in state.questions if q.key in answers], "usage": total, "errors": state.errors + errors}

    async def detect_events(state: SignalState) -> dict:
        if not state.detect_events:
            return {}
        # News plus dated web pages; each document contributes its lead passage.
        chunks = []
        for i, d in enumerate(state.documents):
            if d.source_type not in ("news", "web") or d.meta.get("kind") == "tech_stack":
                continue
            lead = split_chunks(d.text, 800)[:1] or [d.title]
            chunks.append(Chunk(doc_index=i, url=d.url, title=d.title, date=d.date_str, source_type=d.source_type, text=lead[0]))
        usage = Usage()
        events: list[DetectedEvent] = []
        errors = []
        batches = [chunks[i : i + EVENT_BATCH] for i in range(0, len(chunks), EVENT_BATCH)]

        async def run_batch(batch: list[Chunk]):
            key = cache_key("events", llm.small_model, state.company.name, [c.model_dump() for c in batch])
            hit = cache.get(key)
            if hit is not None:
                return [DetectedEvent.model_validate(e) for e in hit], Usage(cache_hits=1)
            evs, u = await _with_retry(lambda: llm.classify_events(state.company, batch))
            cache.set(key, [e.model_dump() for e in evs])
            return evs, u

        for res in await asyncio.gather(*(run_batch(b) for b in batches), return_exceptions=True):
            if isinstance(res, BaseException):
                errors.append(f"detect_events failed: {res}")
                continue
            evs, u = res
            events.extend(evs)
            usage.add(u)
        # Same event reported by several outlets -> keep one per (type, title).
        unique: dict[tuple[str, str], DetectedEvent] = {}
        for e in events:
            unique.setdefault((e.event_type, e.title.lower()[:80]), e)
        total = state.usage.model_copy()
        total.add(usage)
        return {"events": list(unique.values()), "usage": total, "errors": state.errors + errors}

    async def aggregate(state: SignalState) -> dict:
        if on_result is not None:
            result = PipelineResult(
                company=state.company,
                answers=state.answers,
                events=state.events,
                usage=state.usage,
                meta={"documents": len(state.documents), "docs_hash": docs_hash(state.documents), "errors": state.errors},
            )
            maybe = on_result(result)
            if asyncio.iscoroutine(maybe):
                await maybe
        return {}

    g = StateGraph(SignalState)
    g.add_node("load_context", load_context)
    g.add_node("relevance_filter", relevance_filter)
    g.add_node("answer_questions", answer_questions)
    g.add_node("detect_events", detect_events)
    g.add_node("aggregate", aggregate)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "relevance_filter")
    g.add_edge("relevance_filter", "answer_questions")
    g.add_edge("answer_questions", "detect_events")
    g.add_edge("detect_events", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


async def run_signal_pipeline(
    llm: LLMBackend,
    company: CompanyInfo,
    questions: list[QuestionSpec],
    documents: list[Document],
    *,
    cache: Cache | None = None,
    detect_events: bool = True,
    on_result: Callable[[PipelineResult], Awaitable[None] | None] | None = None,
) -> PipelineResult:
    graph = build_graph(llm, cache=cache, on_result=on_result)
    final = await graph.ainvoke(
        SignalState(company=company, questions=questions, documents=documents, detect_events=detect_events)
    )
    state = final if isinstance(final, dict) else final.model_dump()
    return PipelineResult(
        company=company,
        answers=state["answers"],
        events=state["events"],
        usage=state["usage"],
        meta={"documents": len(state["documents"]), "errors": state["errors"]},
    )
