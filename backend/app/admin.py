"""Admin accounts live only in the database: the API never creates, promotes, deactivates or deletes them.

    python -m app.admin create --email admin@orange.md --name "Admin Orange"   # asks for the password
    python -m app.admin password --email admin@orange.md                         # reset an admin's password
    python -m app.admin deactivate --email admin@orange.md                       # (activate to undo)
    python -m app.admin list

The password is read without echo (or from stdin with --password-stdin) and stored only as a PBKDF2 hash.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import hash_password
from .models import Seller, SellerSession

MIN_PASSWORD = 8


def create_admin(db: Session, email: str, full_name: str, password: str) -> Seller:
    """Create an admin, or turn an existing account with this email into an admin with the new password."""
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must have at least {MIN_PASSWORD} characters")
    email = email.strip().lower()
    seller = db.scalar(select(Seller).where(func.lower(Seller.email) == email))
    if seller is None:
        seller = Seller(email=email, full_name=full_name.strip(), password_hash=hash_password(password), role="admin", active=True)
        db.add(seller)
    else:
        seller.full_name = full_name.strip() or seller.full_name
        seller.password_hash = hash_password(password)
        seller.role = "admin"
        seller.active = True
    db.commit()
    return seller


def _admin(db: Session, email: str) -> Seller:
    seller = db.scalar(select(Seller).where(func.lower(Seller.email) == email.strip().lower(), Seller.role == "admin"))
    if seller is None:
        raise SystemExit(f"no admin account with email {email}")
    return seller


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("passwords do not match")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="create an admin (or promote an existing account)")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--password-stdin", action="store_true")
    p = sub.add_parser("password", help="set a new password for an admin")
    p.add_argument("--email", required=True)
    p.add_argument("--password-stdin", action="store_true")
    for name in ("activate", "deactivate"):
        sub.add_parser(name, help=f"{name} an admin account").add_argument("--email", required=True)
    sub.add_parser("list", help="list admin accounts")
    args = parser.parse_args()

    from .db import SessionLocal

    with SessionLocal() as db:
        if args.cmd == "create":
            try:
                admin = create_admin(db, args.email, args.name, _read_password(args.password_stdin))
            except ValueError as exc:
                raise SystemExit(str(exc))
            print(f"admin ready: #{admin.id} {admin.email}")
        elif args.cmd == "password":
            admin = _admin(db, args.email)
            password = _read_password(args.password_stdin)
            if len(password) < MIN_PASSWORD:
                raise SystemExit(f"password must have at least {MIN_PASSWORD} characters")
            admin.password_hash = hash_password(password)
            for s in db.scalars(select(SellerSession).where(SellerSession.seller_id == admin.id)):
                db.delete(s)  # log out everywhere
            db.commit()
            print(f"password changed for {admin.email}")
        elif args.cmd in ("activate", "deactivate"):
            admin = _admin(db, args.email)
            admin.active = args.cmd == "activate"
            db.commit()
            print(f"{admin.email}: {'active' if admin.active else 'deactivated'}")
        else:
            for a in db.scalars(select(Seller).where(Seller.role == "admin").order_by(Seller.id)):
                print(f"#{a.id}  {a.email}  {a.full_name}  {'active' if a.active else 'inactive'}")


if __name__ == "__main__":
    main()
