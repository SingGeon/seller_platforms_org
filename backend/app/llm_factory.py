from typing import Any

from sales_pipeline import AnthropicBackend, HeuristicBackend
from sales_pipeline.llm import LLMBackend

from .config import get_settings
from . import mongo


def get_llm() -> LLMBackend:
    s = get_settings()
    provider = s.llm_provider or ("anthropic" if s.anthropic_api_key else "heuristic")
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
