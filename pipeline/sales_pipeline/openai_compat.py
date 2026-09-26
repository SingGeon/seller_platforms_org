"""Free LLM providers behind one OpenAI-compatible client, chained so the platform never stops.

`OpenAICompatBackend` sends the same prompts and JSON schemas as `AnthropicBackend` to any provider that speaks the
OpenAI chat-completions API (Google Gemini, Groq, NVIDIA NIM, Mistral, OpenRouter, a local Ollama). `ChainBackend`
tries them in order: a provider that hits its daily quota, rate limit or an outage is skipped for a while and the
next one answers; when none is left, the offline `HeuristicBackend` does, so a run always finishes.

Providers without an API key are left out (Ollama only when it answers on localhost). Model names can be changed
with LLM_MODEL_OVERRIDES, e.g. "groq=openai/gpt-oss-120b|openai/gpt-oss-20b, gemini=gemini-3.5-flash" (model, then
an optional small model after "|").
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, replace
from typing import Any

import httpx

from .llm import AnthropicBackend, HeuristicBackend
from .prompts import EXPLAIN_SYSTEM
from .schemas import Usage

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    small_model: str
    min_interval: float  # seconds between requests, to stay under the free requests-per-minute limit
    needs_key: bool = True
    busy_fallbacks: tuple[str, ...] = ()  # same provider, other models to try when one answers 503 "high demand"
    timeout: float = 120.0  # seconds for one answer
    max_concurrency: int = 2


# Free tiers as of Sep 2026 (github.com/mnfst/awesome-free-llm-apis). Only Gemini was checked live; the other model
# ids are the providers' documented free models and can be overridden without a code change.
PROVIDERS: dict[str, Provider] = {
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash", "gemini-3.5-flash-lite", 4.5,
                       busy_fallbacks=("gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-flash-lite-latest")),
    "groq": Provider("groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "openai/gpt-oss-20b", 2.5),
    "nvidia": Provider("nvidia", "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct", "meta/llama-3.3-70b-instruct", 1.6),
    "mistral": Provider("mistral", "https://api.mistral.ai/v1", "mistral-small-latest", "mistral-small-latest", 2.0),
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free",
                           "meta-llama/llama-3.3-70b-instruct:free", 3.5),
    # The base model when every cloud quota is used up: runs on this machine's CPU, so one request at a time and a long
    # timeout. OLLAMA_MODEL picks another model.
    "ollama": Provider("ollama", "http://localhost:11434/v1", "qwen2.5:3b", "qwen2.5:3b", 0.0, needs_key=False,
                       timeout=900.0, max_concurrency=1),
}
DEFAULT_CHAIN = ("gemini", "groq", "nvidia", "mistral", "openrouter", "ollama")


class ProviderUnavailable(Exception):
    """The provider cannot answer now (quota, rate limit, auth, outage); `cooldown` = seconds to skip it."""

    def __init__(self, message: str, cooldown: float) -> None:
        super().__init__(message)
        self.cooldown = cooldown


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


class OpenAICompatBackend(AnthropicBackend):
    """AnthropicBackend's prompts and parsing over an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, provider: Provider, api_key: str | None, *, client: httpx.AsyncClient | None = None,
                 max_concurrency: int | None = None, timeout: float | None = None) -> None:
        self.provider = provider
        self.name = provider.name
        self.model = provider.model
        self.small_model = provider.small_model
        self.effort = "medium"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(timeout=timeout or provider.timeout)
        self._sem = asyncio.Semaphore(max_concurrency or provider.max_concurrency)
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._plain_json = False  # set when the provider rejects json_schema: ask for a JSON object instead

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self.provider.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    async def _chat(self, *, model: str, system: str, user: str, max_tokens: int, response_format: dict | None) -> tuple[str, Usage]:
        """One request; a model that is overloaded (503) hands over to the provider's other models before giving up."""
        models = [model, *(m for m in self.provider.busy_fallbacks if m != model)]
        for i, m in enumerate(models):
            try:
                return await self._chat_once(model=m, system=system, user=user, max_tokens=max_tokens, response_format=response_format)
            except _Busy as exc:
                if i == len(models) - 1:
                    raise ProviderUnavailable(str(exc), cooldown=120) from exc
                log.info("%s is busy, trying %s", m, models[i + 1])
        raise AssertionError("unreachable")  # pragma: no cover

    async def _chat_once(self, *, model: str, system: str, user: str, max_tokens: int, response_format: dict | None) -> tuple[str, Usage]:
        body: dict[str, Any] = {"model": model, "max_tokens": min(max_tokens, 8000),
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if response_format:
            body["response_format"] = response_format
        async with self._sem:
            await self._throttle()
            try:
                resp = await self._client.post(f"{self.provider.base_url}/chat/completions", json=body, headers=self._headers)
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f"{self.name}: {type(exc).__name__}: {exc}", cooldown=300) from exc
        if resp.status_code == 429:
            retry = resp.headers.get("retry-after")
            quota = "quota" in resp.text.lower() or "per day" in resp.text.lower() or "exhausted" in resp.text.lower()
            raise ProviderUnavailable(f"{self.name}: 429 {resp.text[:200]}",
                                      cooldown=float(retry) if retry and retry.isdigit() else (3600 if quota else 60))
        if resp.status_code in (401, 402, 403):
            raise ProviderUnavailable(f"{self.name}: {resp.status_code} {resp.text[:200]}", cooldown=6 * 3600)
        if resp.status_code >= 500:
            raise _Busy(f"{self.name}/{model}: {resp.status_code} {resp.text[:200]}")
        if resp.status_code == 400 and response_format and response_format.get("type") == "json_schema":
            raise _SchemaRejected(resp.text[:200])
        if resp.status_code >= 400:
            raise ProviderUnavailable(f"{self.name}: {resp.status_code} {resp.text[:200]}", cooldown=600)
        data = resp.json()
        u = data.get("usage") or {}
        usage = Usage(input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0), llm_calls=1, cost_usd=0.0)
        choice = (data.get("choices") or [{}])[0]
        return ((choice.get("message") or {}).get("content") or "").strip(), usage

    async def _json_call(self, *, model: str, system: str, user: str, schema: dict, max_tokens: int = 16000,
                         effort: str | None = None) -> tuple[dict, Usage]:
        schema_format = {"type": "json_schema", "json_schema": {"name": "result", "schema": schema}}
        if not self._plain_json:
            try:
                text, usage = await self._chat(model=model, system=system, user=user, max_tokens=max_tokens, response_format=schema_format)
            except _SchemaRejected:
                log.info("%s rejects json_schema, falling back to json_object", self.name)
                self._plain_json = True
        if self._plain_json:
            text, usage = await self._chat(
                model=model, max_tokens=max_tokens, response_format={"type": "json_object"},
                system=f"{system}\n\nAnswer with one JSON object that matches this JSON schema:\n{json.dumps(schema)}", user=user,
            )
        try:
            return json.loads(_strip_fences(text)), usage
        except json.JSONDecodeError:
            log.warning("%s returned invalid JSON: %s", self.name, text[:200])
            return {}, usage

    async def explain_lead(self, payload):
        return await self._chat(model=self.model, system=EXPLAIN_SYSTEM, max_tokens=2000, response_format=None,
                                user=json.dumps(payload, ensure_ascii=False, default=str))


class _SchemaRejected(Exception):
    pass


class _Busy(Exception):
    pass


class ChainBackend:
    """Tries each backend in order; one that is unavailable is skipped for its cooldown; the offline heuristic ends it."""

    small_model = "chain"

    def __init__(self, backends: list[OpenAICompatBackend], fallback: Any | None = None) -> None:
        self.backends = backends
        self.fallback = fallback or HeuristicBackend()
        self.name = "chain(" + ",".join(b.name for b in backends) + ")"
        self.model = backends[0].model if backends else "heuristic"
        self._until: dict[str, float] = {}
        self.used: dict[str, int] = {}  # calls answered per backend, for logs and tests

    async def _call(self, method: str, *args: Any) -> Any:
        for b in self.backends:
            if self._until.get(b.name, 0) > time.monotonic():
                continue
            try:
                result = await getattr(b, method)(*args)
            except ProviderUnavailable as exc:
                self._until[b.name] = time.monotonic() + exc.cooldown
                log.warning("LLM provider %s unavailable for %.0f s: %s", b.name, exc.cooldown, exc)
                continue
            self.used[b.name] = self.used.get(b.name, 0) + 1
            return result
        self.used["heuristic"] = self.used.get("heuristic", 0) + 1
        return await getattr(self.fallback, method)(*args)

    async def answer_questions(self, company, questions, chunks):
        return await self._call("answer_questions", company, questions, chunks)

    async def classify_events(self, company, chunks):
        return await self._call("classify_events", company, chunks)

    async def explain_lead(self, payload):
        return await self._call("explain_lead", payload)

    async def write_outreach(self, payload):
        return await self._call("write_outreach", payload)

    async def extract_companies(self, texts):
        return await self._call("extract_companies", texts)


def parse_overrides(value: str) -> dict[str, tuple[str, str | None]]:
    """'groq=openai/gpt-oss-120b|openai/gpt-oss-20b, gemini=gemini-3.5-flash' -> {name: (model, small_model or None)}."""
    out: dict[str, tuple[str, str | None]] = {}
    for part in filter(None, (p.strip() for p in (value or "").split(","))):
        name, _, models = part.partition("=")
        model, _, small = models.partition("|")
        out[name.strip()] = (model.strip(), small.strip() or None)
    return out


def build_chain(keys: dict[str, str], *, chain: tuple[str, ...] = DEFAULT_CHAIN, overrides: str = "",
                client: httpx.AsyncClient | None = None, ollama_url: str | None = None, ollama_model: str = "",
                ollama_available: bool | None = None) -> ChainBackend | None:
    """The configured providers that have a key (Ollama: that answers), in chain order; None when there is none."""
    ov = parse_overrides(overrides)
    backends = []
    for name in chain:
        p = PROVIDERS.get(name)
        if p is None:
            continue
        if name == "ollama":
            base = (ollama_url or "http://localhost:11434").rstrip("/")
            if ollama_available is None:  # probe it
                try:
                    httpx.get(f"{base}/api/tags", timeout=1.0).raise_for_status()
                    ollama_available = True
                except httpx.HTTPError:
                    ollama_available = False
            if not ollama_available:
                continue
            p = replace(p, base_url=f"{base}/v1", model=ollama_model or p.model, small_model=ollama_model or p.small_model)
        elif p.needs_key and not keys.get(name):
            continue
        if name in ov:
            model, small = ov[name]
            p = replace(p, model=model or p.model, small_model=small or model or p.small_model)
        backends.append(OpenAICompatBackend(p, keys.get(name), client=client))
    return ChainBackend(backends) if backends else None
