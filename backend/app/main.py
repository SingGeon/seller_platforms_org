import asyncio
import contextlib
import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from . import mongo
from .api import config_routes, lead_routes, seller_routes, source_routes
from .auth import auth_guard
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
AUDIT_SKIP = {"/auth/login", "/auth/logout"}  # logged explicitly by the auth routes


def create_app(session_factory: sessionmaker | None = None, llm_override=None, http_override=None, auth_required: bool | None = None) -> FastAPI:
    if session_factory is None:
        from .db import SessionLocal

        session_factory = SessionLocal

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if get_settings().scheduler_enabled:
            from .scheduler import scheduler_loop

            task = asyncio.create_task(scheduler_loop(session_factory, llm_override))
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        lifespan=lifespan,
        title="Orange Signals API",
        version="0.1.0",
        description="AI-powered B2B sales intelligence for Orange Systems: configure ICP and signal questions, "
        "collect public data, extract evidence-backed signals, score and prioritise leads.",
    )
    app.state.session_factory = session_factory
    app.state.llm_override = llm_override  # tests inject a deterministic backend
    app.state.http_override = http_override  # tests inject a mocked HTTP client for discovery sources
    app.state.background_tasks = set()
    app.state.auth_required = get_settings().auth_required if auth_required is None else auth_required
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def audit(request: Request, call_next):
        """Every successful change goes to the MongoDB activity log with the seller from PostgreSQL."""
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        if request.method in AUDIT_METHODS and response.status_code < 400 and path not in AUDIT_SKIP:
            params = request.scope.get("path_params") or {}
            company_id = params.get("company_id")
            try:
                mongo.log_activity(
                    f"{request.method} {path}", getattr(request.state, "seller", None),
                    company_id=int(company_id) if company_id is not None else None,
                    params={k: str(v) for k, v in params.items()}, status=response.status_code,
                )
            except Exception:  # noqa: BLE001 - the audit log must never break a request
                logging.getLogger(__name__).exception("activity log failed")
        return response

    @app.get("/health", tags=["meta"])
    def health():
        with session_factory() as db:
            db.execute(text("select 1"))
        mongo.db().command("ping")
        s = get_settings()
        return {"status": "ok", "postgres": "ok", "mongodb": "ok", "llm": s.llm_provider or ("anthropic" if s.anthropic_api_key else "heuristic"),
                # the deployed commit (Render sets RENDER_GIT_COMMIT), to check that a push reached the cloud
                "commit": os.environ.get("RENDER_GIT_COMMIT", "")[:7] or None}

    guarded = [Depends(auth_guard)]
    app.include_router(config_routes.router, dependencies=guarded)
    app.include_router(lead_routes.router, dependencies=guarded)
    app.include_router(source_routes.router, dependencies=guarded)
    app.include_router(seller_routes.router)
    return app


app = create_app()
