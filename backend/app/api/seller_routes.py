"""Seller accounts (login, admin user management) and the CRM state of each lead
(pipeline stage, owner, notes), all in PostgreSQL; plus the MongoDB activity log and the
cross-database integrity check."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pymongo import DESCENDING
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import integrity, mongo
from ..auth import bearer_token, check_password, current_seller, issue_token, require_admin, revoke_token
from ..models import LeadAssignment, Seller
from ..schemas import AssignmentIn, AssignmentOut, LoginIn, NoteIn, SellerCreate, SellerOut, SellerUpdate, TokenOut
from .deps import company_or_404, get_db, get_or_404

router = APIRouter()


# ------------------------------------------------------------------ auth
@router.get("/auth/status", tags=["auth"], summary="Is login required, and does the first (admin) account still need to be created?")
def auth_status(request: Request, db: Session = Depends(get_db)):
    return {"auth_required": request.app.state.auth_required, "has_sellers": (db.scalar(select(func.count(Seller.id))) or 0) > 0}


@router.post("/auth/login", response_model=TokenOut, tags=["auth"])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    seller = db.scalar(select(Seller).where(func.lower(Seller.email) == email))
    reason = "unknown_email" if seller is None else "inactive" if not seller.active else None
    if reason is None and not check_password(db, seller, body.password):
        reason = "wrong_password"
    if reason:
        # Failed attempts go to the activity log (never the password); the caller only learns "wrong email or password".
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        mongo.log_activity("login_failed", seller, email=email[:200], reason=reason,
                           ip=forwarded or (request.client.host if request.client else None))
        raise HTTPException(401, "Wrong email or password")
    token, expires = issue_token(db, seller)
    mongo.log_activity("login", seller)
    return TokenOut(access_token=token, expires_at=expires, seller=SellerOut.model_validate(seller))


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(request: Request, db: Session = Depends(get_db), seller: Seller = Depends(current_seller)):
    revoke_token(db, bearer_token(request) or "")
    mongo.log_activity("logout", seller)
    return Response(status_code=204)


@router.get("/auth/me", response_model=SellerOut, tags=["auth"])
def me(seller: Seller = Depends(current_seller)):
    return seller


# ------------------------------------------------------------------ sellers
ADMIN_IN_DB = "Admin accounts are managed directly in the database (python -m app.admin), not through the API"


@router.post("/sellers", response_model=SellerOut, status_code=201, tags=["sellers"],
             summary="Create a seller account (admin only). Admin accounts are created in the database, never here")
def create_seller(body: SellerCreate, db: Session = Depends(get_db), _: Seller = Depends(require_admin)):
    if body.role != "seller":
        raise HTTPException(403, ADMIN_IN_DB)
    email = body.email.strip().lower()
    if db.scalar(select(Seller.id).where(func.lower(Seller.email) == email)) is not None:
        raise HTTPException(409, "An account with this email already exists")
    seller = Seller(email=email, full_name=body.full_name.strip(), password=body.password, role="seller")
    db.add(seller)
    db.commit()
    return seller


@router.get("/sellers", response_model=list[SellerOut], tags=["sellers"])
def list_sellers(db: Session = Depends(get_db), _: Seller = Depends(current_seller)):
    return list(db.scalars(select(Seller).order_by(Seller.full_name)))


@router.put("/sellers/{seller_id}", response_model=SellerOut, tags=["sellers"],
            summary="Update a seller: yourself (name, password), or an admin on a seller account (also active). Roles never change here")
def update_seller(seller_id: int, body: SellerUpdate, db: Session = Depends(get_db), caller: Seller = Depends(current_seller)):
    seller = get_or_404(db, Seller, seller_id)
    if body.role is not None and body.role != seller.role:
        raise HTTPException(403, ADMIN_IN_DB)
    own = caller.id == seller_id
    if own and body.active is not None and body.active != seller.active:
        raise HTTPException(403, "You cannot activate or deactivate your own account")
    if not own:
        if caller.role != "admin":
            raise HTTPException(403, "You can only change your own name and password")
        if seller.role == "admin":
            raise HTTPException(403, ADMIN_IN_DB)
    if body.full_name is not None:
        seller.full_name = body.full_name.strip()
    if body.password is not None:
        seller.password = body.password
    if body.role is not None:
        seller.role = body.role
    if body.active is not None:
        seller.active = body.active
    db.commit()
    return seller


@router.delete("/sellers/{seller_id}", status_code=204, tags=["sellers"])
def delete_seller(seller_id: int, db: Session = Depends(get_db), admin: Seller = Depends(require_admin)):
    if seller_id == admin.id:
        raise HTTPException(422, "You cannot delete your own account")
    seller = get_or_404(db, Seller, seller_id)
    if seller.role == "admin":
        raise HTTPException(403, ADMIN_IN_DB)
    db.delete(seller)
    db.commit()
    # Mongo keeps the seller's name in the log; only the id reference is cleared.
    mongo.db()[mongo.SIGNALS].update_many({"seller_id": seller_id}, {"$set": {"seller_id": None}})
    return Response(status_code=204)


# ------------------------------------------------------------------ lead CRM state
def _assignment_out(a: LeadAssignment) -> AssignmentOut:
    return AssignmentOut(
        company_id=a.company_id, seller_id=a.seller_id, owner=a.seller.full_name if a.seller else None,
        stage=a.stage, notes=a.notes or [], updated_at=a.updated_at,
    )


def _get_or_new(db: Session, company_id: int) -> LeadAssignment:
    a = db.get(LeadAssignment, company_id)
    if a is None:
        a = LeadAssignment(company_id=company_id, stage="nou", notes=[])
        db.add(a)
    return a


@router.get("/assignments", response_model=list[AssignmentOut], tags=["crm"], summary="Stage, owner and notes of every lead")
def list_assignments(seller_id: int | None = None, db: Session = Depends(get_db), _: Seller = Depends(current_seller)):
    stmt = select(LeadAssignment)
    if seller_id is not None:
        stmt = stmt.where(LeadAssignment.seller_id == seller_id)
    return [_assignment_out(a) for a in db.scalars(stmt)]


@router.get("/companies/{company_id}/assignment", response_model=AssignmentOut, tags=["crm"])
def get_assignment(company_id: int, db: Session = Depends(get_db), _: Seller = Depends(current_seller)):
    company_or_404(company_id)
    a = db.get(LeadAssignment, company_id)
    return _assignment_out(a) if a else AssignmentOut(company_id=company_id, stage="nou")


@router.put("/companies/{company_id}/assignment", response_model=AssignmentOut, tags=["crm"],
            summary="Move a lead to a stage and/or set its owner: an admin assigns anyone, a seller only takes a free lead or gives back their own")
def update_assignment(company_id: int, body: AssignmentIn, db: Session = Depends(get_db), caller: Seller = Depends(current_seller)):
    company_or_404(company_id)
    a = _get_or_new(db, company_id)
    if caller.role != "admin":
        if body.unassign and a.seller_id not in (None, caller.id):
            raise HTTPException(403, "You can only give back a lead you own")
        if not body.unassign and body.seller_id is not None:
            if body.seller_id != caller.id:
                raise HTTPException(403, "Only an admin can assign a lead to someone else")
            if a.seller_id not in (None, caller.id):
                raise HTTPException(403, "This lead already has an owner")
    if body.stage is not None:
        a.stage = body.stage
    if body.unassign:
        a.seller_id = None
    elif body.seller_id is not None:
        get_or_404(db, Seller, body.seller_id)
        a.seller_id = body.seller_id
    a.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return _assignment_out(a)


@router.post("/companies/{company_id}/notes", response_model=AssignmentOut, status_code=201, tags=["crm"])
def add_note(company_id: int, body: NoteIn, db: Session = Depends(get_db), seller: Seller = Depends(current_seller)):
    company_or_404(company_id)
    a = _get_or_new(db, company_id)
    note = {"t": datetime.now(timezone.utc).isoformat(), "seller_id": seller.id, "author": seller.full_name, "text": body.text.strip()}
    a.notes = [*(a.notes or []), note]
    a.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(a)
    return _assignment_out(a)


# ------------------------------------------------------------------ activity log (MongoDB) and cross-database integrity
@router.get("/activity", tags=["crm"], summary="Who did what, newest first (MongoDB activity_log; seller ids from PostgreSQL)")
def activity(company_id: int | None = None, seller_id: int | None = None, limit: int = 100, _: Seller = Depends(current_seller)):
    q: dict = {}
    if company_id is not None:
        q["company_id"] = company_id
    if seller_id is not None:
        q["seller_id"] = seller_id
    rows = mongo.db()[mongo.ACTIVITY].find(q, {"_id": 0}).sort("t", DESCENDING).limit(min(limit, 1000))
    return list(rows)


@router.get("/admin/integrity", tags=["admin"], summary="Cross-database check: references between PostgreSQL and MongoDB")
def integrity_check(db: Session = Depends(get_db), _: Seller = Depends(require_admin)):
    return integrity.public(integrity.check(db))


@router.post("/admin/integrity/repair", tags=["admin"], summary="Remove orphans left in either database")
def integrity_repair(db: Session = Depends(get_db), admin: Seller = Depends(require_admin)):
    result = integrity.repair(db)
    mongo.log_activity("integrity_repair", admin, removed=result["removed"])
    return result
