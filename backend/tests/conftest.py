import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ["OFFLINE_COLLECT"] = "true"
os.environ["LLM_PROVIDER"] = "heuristic"
os.environ.pop("ANTHROPIC_API_KEY", None)

import uuid

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401
from app import mongo
from app.db import Base
from app.main import create_app
from app.seed import seed_companies, seed_config, seed_sample_documents
from sales_pipeline import HeuristicBackend


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr("sales_pipeline.sources.base.RETRY_BASE_DELAY", 0.0)


@pytest.fixture(autouse=True)
def mongo_db():
    """A throwaway MongoDB database per test (companies, documents, signals, scores, runs)."""
    client = MongoClient(os.environ["MONGO_URI"], tz_aware=True, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except PyMongoError:
        pytest.skip("MongoDB is not reachable at MONGO_URI")
    name = f"leadradar_test_{uuid.uuid4().hex[:12]}"
    mongo.use(client[name])
    yield client[name]
    client.drop_database(name)
    client.close()


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
    seed_companies()
    seed_sample_documents()
    return session_factory


@pytest.fixture()
def client(seeded):
    app = create_app(seeded, llm_override=HeuristicBackend())
    with TestClient(app) as c:
        yield c
