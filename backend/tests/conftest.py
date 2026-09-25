import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["OFFLINE_COLLECT"] = "true"
os.environ["LLM_PROVIDER"] = "heuristic"
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app.db import Base
from app.main import create_app
from app.seed import seed_companies, seed_config, seed_sample_documents
from sales_pipeline import HeuristicBackend


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr("sales_pipeline.sources.base.RETRY_BASE_DELAY", 0.0)


@pytest.fixture()
def session_factory(tmp_path):
    # One connection per session, like PostgreSQL in production. A single shared in-memory
    # connection (StaticPool) lets a request thread's ROLLBACK undo a background run's writes.
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def seeded(session_factory):
    with session_factory() as db:
        seed_config(db)
        seed_companies(db)
        seed_sample_documents(db)
    return session_factory


@pytest.fixture()
def client(seeded):
    app = create_app(seeded, llm_override=HeuristicBackend())
    with TestClient(app) as c:
        yield c
