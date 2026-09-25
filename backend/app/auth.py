"""Seller accounts: PBKDF2 password hashes and opaque bearer tokens (only their SHA-256 is stored)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .api.deps import get_db
from .models import Seller, SellerSession

PBKDF2_ITERATIONS = 390_000
SESSION_DAYS = 14


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


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
    token = bearer_token(request)
    if not token:
        return None
    row = db.get(SellerSession, _token_hash(token))
    if row is None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc) or not row.seller.active:
        return None
    return row.seller


def current_seller(seller: Seller | None = Depends(optional_seller)) -> Seller:
    if seller is None:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Bearer"})
    return seller


def require_admin(seller: Seller = Depends(current_seller)) -> Seller:
    if seller.role != "admin":
        raise HTTPException(403, "Admin only")
    return seller
