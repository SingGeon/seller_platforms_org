from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://orange:orange@localhost:5432/orange_signals"

    # LLM: "anthropic" | "heuristic" | "" (auto: anthropic when ANTHROPIC_API_KEY is set)
    llm_provider: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5"
    llm_small_model: str = "claude-haiku-4-5"
    llm_effort: str = "medium"
    llm_max_concurrency: int = 8

    newsapi_key: str = ""
    serpapi_key: str = ""
    hubspot_token: str = ""

    crawl_max_pages: int = 12
    crawl_delay_seconds: float = 1.0
    use_playwright: bool = False
    run_company_concurrency: int = 5
    # Skip network collectors entirely and score from documents already stored (demo / offline).
    offline_collect: bool = False

    cors_origins: str = "http://localhost:5173,http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
