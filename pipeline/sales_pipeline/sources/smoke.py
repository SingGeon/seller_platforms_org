"""Live smoke test for every source. Run on a machine with internet access:

    python -m sales_pipeline.sources.smoke                 # all sources
    python -m sales_pipeline.sources.smoke ted hibp        # selected sources
    COUNTRIES=RO,MD python -m sales_pipeline.sources.smoke google_news_topics

Keys are read from the environment (ADZUNA_APP_ID, ADZUNA_APP_KEY, NEWSDATA_KEY,
CURRENTS_KEY, SEC_USER_AGENT="Name email@example.com", ...). Sources whose keys
are missing are reported as SKIP. Nothing is written anywhere.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

from ..collectors.jobs import fetch_ashby, fetch_greenhouse
from ..schemas import CompanyInfo
from .base import SourceContext
from .catalog import SOURCES
from .cyber import load_kev
from ..collectors.news import fetch_google_news
from .bulk import gleif_companies, wikidata_companies
from .registry import gleif_profile, wikidata_profile

KEY_ENV = ["adzuna_app_id", "adzuna_app_key", "newsdata_key", "currents_key", "serpapi_key", "themuse_key"]


async def main(names: list[str]) -> int:
    keys = {k: os.getenv(k.upper(), "") for k in KEY_ENV}
    sec_ua = os.getenv("SEC_USER_AGENT", "")
    keys["sec_user_agent"] = sec_ua
    countries = [c.strip().upper() for c in os.getenv("COUNTRIES", "").split(",") if c.strip()]
    failures = 0
    async with httpx.AsyncClient(timeout=45, follow_redirects=True, headers={"User-Agent": "OrangeSignals/0.1 smoke-test"}) as client:
        ctx = SourceContext(client=client, keys=keys, countries=countries, since=datetime.now(timezone.utc) - timedelta(days=7),
                            keywords={"apa": ["rpa", "automation"], "cyber": ["security"]}, max_items=20, sec_user_agent=sec_ua or None)
        for spec in SOURCES:
            if spec.sync is None or (names and spec.name not in names):
                continue
            missing = spec.missing_keys(keys)
            if missing:
                print(f"SKIP {spec.name:22} missing {', '.join(m.upper() for m in missing)}")
                continue
            t0 = time.monotonic()
            try:
                res = await spec.sync(ctx, {})
                sample = "; ".join(f"{i.company_name} [{i.signal}]" for i in res.items[:3])
                print(f"OK   {spec.name:22} fetched={res.fetched:<5} items={len(res.items):<4} unresolved={len(res.unresolved):<3} {time.monotonic() - t0:5.1f}s  {sample[:110]}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"ERR  {spec.name:22} {type(exc).__name__}: {str(exc)[:150]}")
        if not names or "enrichment" in names:
            checks = {
                "wikidata": wikidata_profile(client, "DHL Group", "group.dhl.com"),
                "gleif": gleif_profile(client, "Deutsche Lufthansa", "DE"),
                "cisa_kev": load_kev(client),
                "greenhouse": fetch_greenhouse(client, CompanyInfo(name="GitLab"), "gitlab"),
                "ashby": fetch_ashby(client, CompanyInfo(name="Ramp"), "ramp"),
                "bulk_wikidata_RO": wikidata_companies(client, "RO", 25),
                "bulk_gleif_MD": gleif_companies(client, "MD", 25),
                "google_news_RO": fetch_google_news(client, CompanyInfo(name="Banca Transilvania", country="RO"), ["automatizare", "digitalizare", "AI"]),
            }
            for name, coro in checks.items():
                try:
                    res = await coro
                    if isinstance(res, list):
                        first = res[0] if res else None
                        label = getattr(first, "name", None) or getattr(first, "title", None) or (first.get("cveID") if isinstance(first, dict) else "")
                        detail = f"{len(res)} records; first: {label}"
                    else:
                        detail = res.model_dump(exclude_none=True) if res else "no match"
                    print(f"OK   {name:22} {str(detail)[:140]}")
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"ERR  {name:22} {type(exc).__name__}: {str(exc)[:150]}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main(sys.argv[1:])) else 0)
