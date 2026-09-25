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
    # Discovery sources (GIG-14). Every key is optional; a source without its key is skipped.
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    newsdata_key: str = ""
    currents_key: str = ""
    themuse_key: str = ""
    # SEC requires "Name email@domain" as User-Agent; SEC sources stay off until it is set.
    sec_user_agent: str = ""

    # Markets for discovery when no ICP lists countries ("change the country" = edit the ICP).
    discovery_countries: str = "RO,MD"
    discovery_max_items_per_source: int = 200
    # After discovery, run full enrichment (website, ATS, registries) for the N best new leads.
    enrich_top_n: int = 20
    # SerpAPI's free tier is ~100-250 searches/month: only the N highest-scored companies use it.
    serpapi_top_n: int = 10
    # Background refresh of discovery sources on their catalogue interval.
    scheduler_enabled: bool = False
    scheduler_tick_seconds: int = 60

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
