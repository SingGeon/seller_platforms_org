"""Seller accounts: passwords stored in plain text (team decision, see README "Seller accounts") and opaque
bearer tokens (only their SHA-256 is stored)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .api.deps import get_db
from .models import Seller, SellerSession

SESSION_DAYS = 14
LEGACY_PREFIX = "pbkdf2_sha256$"  # accounts created before passwords were stored in plain text


def _legacy_match(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest)


def check_password(db: Session, seller: Seller, password: str) -> bool:
    """Compare with the stored password. A legacy PBKDF2 value is accepted once and replaced by the plain text."""
    stored = seller.password or ""
    if stored.startswith(LEGACY_PREFIX):
        if not _legacy_match(password, stored):
            return False
        seller.password = password
        db.commit()
        return True
    return hmac.compare_digest(stored.encode(), password.encode())


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db: Session, seller: Seller) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.add(SellerSession(token_hash=_token_hash(token), seller_id=seller.id, expires_at=expires))
    seller.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return token, expires


def revoke_token(db: Session, token: str) -> None:
    row = db.get(SellerSession, _token_hash(token))
    if row is not None:
        db.delete(row)
        db.commit()


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def optional_seller(request: Request, db: Session = Depends(get_db)) -> Seller | None:
    """The logged-in seller (or None); also kept on request.state for the activity log."""
    token = bearer_token(request)
    row = db.get(SellerSession, _token_hash(token)) if token else None
    seller = None
    if row is not None:
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if expires >= datetime.now(timezone.utc) and row.seller.active:
            seller = row.seller
    request.state.seller = seller
    return seller


def auth_guard(request: Request, seller: Seller | None = Depends(optional_seller)) -> None:
    """Router-level guard: every data/config endpoint needs a login unless auth is switched off."""
    if request.app.state.auth_required and seller is None:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Bearer"})


def current_seller(seller: Seller | None = Depends(optional_seller)) -> Seller:
    if seller is None:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Bearer"})
    return seller


def require_admin(seller: Seller = Depends(current_seller)) -> Seller:
    if seller.role != "admin":
        raise HTTPException(403, "Admin only")
    return seller
