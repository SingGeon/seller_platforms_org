import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from .api import config_routes, lead_routes
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(session_factory: sessionmaker | None = None, llm_override=None) -> FastAPI:
    if session_factory is None:
        from .db import SessionLocal

        session_factory = SessionLocal
    app = FastAPI(
        title="Orange Signals API",
        version="0.1.0",
        description="AI-powered B2B sales intelligence for Orange Systems: configure ICP and signal questions, "
        "collect public data, extract evidence-backed signals, score and prioritise leads.",
    )
    app.state.session_factory = session_factory
    app.state.llm_override = llm_override  # tests inject a deterministic backend
    app.state.background_tasks = set()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health():
        with session_factory() as db:
            db.execute(text("select 1"))
        s = get_settings()
        return {"status": "ok", "llm": s.llm_provider or ("anthropic" if s.anthropic_api_key else "heuristic")}

    app.include_router(config_routes.router)
    app.include_router(lead_routes.router)
    return app


app = create_app()
