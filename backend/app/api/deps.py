from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import mongo
from ..models import Service
from ..mongo import MDoc


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} not found")
    return obj


def mongo_or_404(collection: str, obj_id: int, label: str) -> MDoc:
    obj = mongo.get(collection, obj_id)
    if obj is None:
        raise HTTPException(404, f"{label} {obj_id} not found")
    return obj


def company_or_404(company_id: int) -> MDoc:
    return mongo_or_404(mongo.COMPANIES, company_id, "Company")


def resolve_service(db: Session, ref: str | int) -> Service:
    """Accept a service id or slug in query parameters (?service=apa or ?service=1)."""
    svc = None
    if isinstance(ref, int) or str(ref).isdigit():
        svc = db.get(Service, int(ref))
    if svc is None:
        svc = db.scalar(select(Service).where(Service.slug == str(ref)))
    if svc is None:
        raise HTTPException(404, f"Service '{ref}' not found")
    return svc
