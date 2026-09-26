from typing import Any

from sales_pipeline import AnthropicBackend, HeuristicBackend
from sales_pipeline.llm import LLMBackend

from .config import get_settings
from . import mongo


_FREE_CHAIN = None


def free_chain():
    """The chained free providers, built once per process so their cooldowns and throttles are shared by every run."""
    global _FREE_CHAIN
    if _FREE_CHAIN is None:
        from sales_pipeline.openai_compat import build_chain

        s = get_settings()
        keys = {"gemini": s.gemini_api_key, "groq": s.groq_api_key, "nvidia": s.nvidia_api_key, "mistral": s.mistral_api_key,
                "openrouter": s.openrouter_api_key}
        _FREE_CHAIN = build_chain(keys, chain=tuple(p.strip() for p in s.llm_chain.split(",") if p.strip()),
                                  overrides=s.llm_model_overrides, ollama_url=s.ollama_url,
                                  ollama_model=s.ollama_model) or False
    return _FREE_CHAIN or None


def llm_name() -> str:
    s = get_settings()
    provider = s.llm_provider or ("anthropic" if s.anthropic_api_key else "")
    if provider in ("anthropic", "heuristic"):
        return provider
    chain = free_chain()
    return chain.name if chain else "heuristic"


def get_llm() -> LLMBackend:
    s = get_settings()
    provider = s.llm_provider or ("anthropic" if s.anthropic_api_key else "free")
    if provider == "free":
        return free_chain() or HeuristicBackend()
    if provider == "anthropic":
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key or None, max_retries=3)
        return AnthropicBackend(
            model=s.llm_model,
            small_model=s.llm_small_model,
            effort=s.llm_effort,
            max_concurrency=s.llm_max_concurrency,
            client=client,
        )
    return HeuristicBackend()


class MongoCache:
    """LLM response cache persisted in MongoDB `llm_cache` so re-runs don't re-pay (GIG-28)."""

    def get(self, key: str) -> Any | None:
        row = mongo.db()[mongo.LLM_CACHE].find_one({"_id": key}, {"value": 1})
        return row["value"] if row else None

    def set(self, key: str, value: Any) -> None:
        mongo.db()[mongo.LLM_CACHE].replace_one({"_id": key}, {"_id": key, "value": value, "created_at": mongo.utcnow()}, upsert=True)
