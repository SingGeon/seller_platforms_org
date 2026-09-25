"""Background refresh (GIG-14 §10): every tick, sync the discovery sources whose
interval has elapsed, then analyse the companies they touched. Enrichment of new
leads is left to explicit discovery runs so the free tiers are not burned in the background."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .config import get_settings
from .discovery import due_sources, run_discovery
from .models import PipelineRun

log = logging.getLogger(__name__)


async def tick(sf: sessionmaker, llm=None) -> int | None:
    """Run one scheduler step; returns the discovery run id when something was due."""
    with sf() as db:
        if db.scalar(select(PipelineRun.id).where(PipelineRun.status.in_(["queued", "running"])).limit(1)):
            return None  # never overlap with a manual run
        due = due_sources(db)
        if not due:
            return None
        run = PipelineRun(status="queued", kind="discovery", params={"sources": due, "trigger": "scheduler", "enrich_top_n": 0})
        db.add(run)
        db.commit()
        run_id = run.id
    await run_discovery(sf, run_id, sources=due, enrich_top_n=0, llm=llm)
    return run_id


async def scheduler_loop(sf: sessionmaker, llm=None) -> None:
    interval = get_settings().scheduler_tick_seconds
    log.info("source scheduler started (tick %ss)", interval)
    while True:
        try:
            await tick(sf, llm)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval)
