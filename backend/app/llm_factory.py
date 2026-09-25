from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from sales_pipeline import AnthropicBackend, HeuristicBackend
from sales_pipeline.llm import LLMBackend

from .config import get_settings
from .models import LlmCache


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


class DbCache:
    """LLM response cache persisted in `llm_cache` so re-runs don't re-pay (GIG-28)."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def get(self, key: str) -> Any | None:
        with self._sf() as db:  # type: Session
            row = db.get(LlmCache, key)
            return row.value if row else None

    def set(self, key: str, value: Any) -> None:
        with self._sf() as db:
            db.merge(LlmCache(key=key, value=value))
            db.commit()
