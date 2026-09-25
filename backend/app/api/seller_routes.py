"""Seller accounts (login, admin user management) and the CRM state of each lead
(pipeline stage, owner, notes). All of it lives in PostgreSQL."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import bearer_token, current_seller, hash_password, issue_token, optional_seller, require_admin, revoke_token, verify_password
from ..models import LeadAssignment, Seller
from ..schemas import AssignmentIn, AssignmentOut, LoginIn, NoteIn, SellerCreate, SellerOut, SellerUpdate, TokenOut
from .deps import company_or_404, get_db, get_or_404

router = APIRouter()


# ------------------------------------------------------------------ auth
@router.post("/auth/login", response_model=TokenOut, tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    seller = db.scalar(select(Seller).where(func.lower(Seller.email) == body.email.strip().lower()))
    if seller is None or not seller.active or not verify_password(body.password, seller.password_hash):
        raise HTTPException(401, "Wrong email or password")
    token, expires = issue_token(db, seller)
    return TokenOut(access_token=token, expires_at=expires, seller=SellerOut.model_validate(seller))


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(request: Request, db: Session = Depends(get_db), _: Seller = Depends(current_seller)):
    revoke_token(db, bearer_token(request) or "")
    return Response(status_code=204)


@router.get("/auth/me", response_model=SellerOut, tags=["auth"])
def me(seller: Seller = Depends(current_seller)):
    return seller


# ------------------------------------------------------------------ sellers
@router.post("/sellers", response_model=SellerOut, status_code=201, tags=["sellers"],
             summary="Create a seller account (admin only; the very first account is created freely and becomes admin)")
def create_seller(body: SellerCreate, db: Session = Depends(get_db), caller: Seller | None = Depends(optional_seller)):
    first = db.scalar(select(func.count(Seller.id))) == 0
    if not first and (caller is None or caller.role != "admin"):
        raise HTTPException(403, "Only an admin can create seller accounts")
    email = body.email.strip().lower()
    if db.scalar(select(Seller.id).where(func.lower(Seller.email) == email)) is not None:
        raise HTTPException(409, "An account with this email already exists")
    seller = Seller(email=email, full_name=body.full_name.strip(), password_hash=hash_password(body.password), role="admin" if first else body.role)
    db.add(seller)
    db.commit()
    return seller


@router.get("/sellers", response_model=list[SellerOut], tags=["sellers"])
def list_sellers(db: Session = Depends(get_db), _: Seller = Depends(current_seller)):
    return list(db.scalars(select(Seller).order_by(Seller.full_name)))


@router.put("/sellers/{seller_id}", response_model=SellerOut, tags=["sellers"], summary="Update a seller (admin, or yourself for name/password)")
def update_seller(seller_id: int, body: SellerUpdate, db: Session = Depends(get_db), caller: Seller = Depends(current_seller)):
    seller = get_or_404(db, Seller, seller_id)
    is_admin = caller.role == "admin"
    if not is_admin and (caller.id != seller_id or body.role is not None or body.active is not None):
        raise HTTPException(403, "You can only change your own name and password")
    if body.full_name is not None:
        seller.full_name = body.full_name.strip()
    if body.password is not None:
        seller.password_hash = hash_password(body.password)
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
    db.delete(get_or_404(db, Seller, seller_id))
    db.commit()
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


@router.put("/companies/{company_id}/assignment", response_model=AssignmentOut, tags=["crm"], summary="Move a lead to a stage and/or assign an owner")
def update_assignment(company_id: int, body: AssignmentIn, db: Session = Depends(get_db), _: Seller = Depends(current_seller)):
    company_or_404(company_id)
    a = _get_or_new(db, company_id)
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
