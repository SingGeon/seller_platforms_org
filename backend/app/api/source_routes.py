"""Data sources API (GIG-14): catalogue with limits, live sync status, manual syncs and discovery runs."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sales_pipeline.sources.bulk import COUNTRY_QID
from sales_pipeline.sources.catalog import BY_NAME, NOT_IMPLEMENTED, SOURCES

from .. import mongo
from ..bootstrap import bootstrap
from ..discovery import get_state, run_discovery, source_keys
from ..models import SourceState
from ..mongo import MDoc
from ..schemas import RunOut
from .deps import get_db

router = APIRouter(tags=["sources"])


class SourceOut(BaseModel):
    name: str
    label: str
    mode: str
    category: str
    refresh: str
    interval_minutes: int
    services: list[str]
    coverage: str
    limits: str
    fallback: str
    requires: list[str]
    missing_keys: list[str]
    enabled: bool
    configured: bool
    last_status: str = "never"
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    next_run_at: datetime | None = None
    last_error: str | None = None
    last_stats: dict = Field(default_factory=dict)
    total_items: int = 0
    total_new_companies: int = 0


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(None, ge=5, le=10080)
    reset_cursor: bool = False


class DiscoveryIn(BaseModel):
    sources: list[str] | None = Field(None, description="Discovery sources to sync; default = all configured")
    enrich_top_n: int | None = Field(None, ge=0, le=200, description="Fully enrich the N best new leads; default ENRICH_TOP_N")


def _out(spec, state: SourceState | None, keys: dict[str, str]) -> SourceOut:
    missing = spec.missing_keys(keys)
    return SourceOut(
        name=spec.name, label=spec.label, mode=spec.mode, category=spec.category, refresh=spec.refresh,
        interval_minutes=(state.interval_minutes if state and state.interval_minutes else spec.interval_minutes),
        services=spec.services, coverage=spec.coverage, limits=spec.limits, fallback=spec.fallback, requires=spec.requires,
        missing_keys=missing, enabled=state.enabled if state else True, configured=not missing,
        **({
            "last_status": state.last_status, "last_run_at": state.last_run_at, "last_success_at": state.last_success_at,
            "next_run_at": state.next_run_at, "last_error": state.last_error, "last_stats": state.last_stats or {},
            "total_items": state.total_items or 0, "total_new_companies": state.total_new_companies or 0,
        } if state else {}),
    )


@router.get("/sources", response_model=list[SourceOut])
def list_sources(mode: str | None = None, db: Session = Depends(get_db)):
    keys = source_keys()
    states = {s.name: s for s in db.scalars(select(SourceState))}
    return [_out(spec, states.get(spec.name), keys) for spec in SOURCES if not mode or spec.mode == mode]


@router.get("/sources/not-used")
def sources_not_used():
    return [{"source": n, "reason": why} for n, why in NOT_IMPLEMENTED]


@router.get("/sources/{name}", response_model=SourceOut)
def get_source(name: str, db: Session = Depends(get_db)):
    spec = BY_NAME.get(name) or _404(name)
    return _out(spec, db.get(SourceState, name), source_keys())


@router.put("/sources/{name}", response_model=SourceOut)
def update_source(name: str, body: SourceUpdate, db: Session = Depends(get_db)):
    spec = BY_NAME.get(name) or _404(name)
    state = get_state(db, name)
    if body.enabled is not None:
        state.enabled = body.enabled
    if body.interval_minutes is not None:
        state.interval_minutes = body.interval_minutes
        state.next_run_at = None
    if body.reset_cursor:
        state.cursor = {}
    db.commit()
    return _out(spec, state, source_keys())


def _404(name: str):
    raise HTTPException(404, f"Unknown source '{name}'")


def _start(request: Request, sources: list[str] | None, enrich_top_n: int | None) -> MDoc:
    active = mongo.active_run()
    if active is not None:
        raise HTTPException(409, f"Run {active.id} is still {active.status}")
    for n in sources or []:
        spec = BY_NAME.get(n) or _404(n)
        if spec.sync is None:
            raise HTTPException(422, f"'{n}' is an enrichment source; it runs inside enrichment runs (POST /runs)")
    seller = getattr(request.state, "seller", None)
    run = mongo.create_run(kind="discovery", params={"sources": sources, "enrich_top_n": enrich_top_n, "trigger": "api"},
                           seller_id=seller.id if seller else None)
    task = asyncio.create_task(
        run_discovery(request.app.state.session_factory, run.id, sources=sources, enrich_top_n=enrich_top_n,
                      llm=request.app.state.llm_override, client=request.app.state.http_override)
    )
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)
    return run


class BootstrapIn(BaseModel):
    countries: list[str] = Field(default_factory=lambda: ["RO", "MD", "DE", "AT", "PL", "NL", "GB"])
    target: int = Field(1000, ge=1, le=20000)
    gleif_fill: bool = False
    news: bool = True
    gdelt: bool = False
    enrich_top_n: int = Field(0, ge=0, le=500)


@router.post("/bootstrap/runs", response_model=RunOut, status_code=202, summary="Load a large real company universe (Wikidata/GLEIF + news + scoring)")
async def start_bootstrap(body: BootstrapIn, request: Request):
    countries = [c.strip().upper() for c in body.countries]
    unknown = [c for c in countries if c not in COUNTRY_QID]
    if unknown:
        raise HTTPException(422, f"Unsupported countries {unknown}; supported: {sorted(COUNTRY_QID)}")
    active = mongo.active_run()
    if active is not None:
        raise HTTPException(409, f"Run {active.id} is still {active.status}")
    seller = getattr(request.state, "seller", None)
    run = mongo.create_run(status="running", kind="bootstrap", params=body.model_dump(), started_at=datetime.now(timezone.utc),
                           seller_id=seller.id if seller else None)
    sf = request.app.state.session_factory
    run_id = run.id

    def say(msg: str) -> None:
        mongo.log_run(run_id, msg)

    async def go() -> None:
        try:
            stats = await bootstrap(
                sf, countries=countries, target=body.target, gleif_fill=body.gleif_fill, news=body.news, gdelt=body.gdelt,
                enrich_top_n=body.enrich_top_n, llm=request.app.state.llm_override, client=request.app.state.http_override, say=say, run_id=run_id,
            )
            status, error = "succeeded", None
        except Exception as exc:  # noqa: BLE001 - always end in a terminal state
            stats, status, error = {}, "failed", str(exc)[:2000]
        mongo.update(mongo.RUNS, run_id, {"status": status, "error": error, "stats": stats, "finished_at": datetime.now(timezone.utc)})

    task = asyncio.create_task(go())
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)
    return run


@router.post("/sources/{name}/sync", response_model=RunOut, status_code=202)
async def sync_one(name: str, request: Request):
    return _start(request, [name], 0)


@router.post("/discovery/runs", response_model=RunOut, status_code=202)
async def start_discovery(body: DiscoveryIn, request: Request):
    return _start(request, body.sources, body.enrich_top_n)
