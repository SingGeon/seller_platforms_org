"""Decision-maker contacts per company (app/contacts.py): list, look them up in real sources, add by hand,
mark "do not contact", record that a message was sent."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .. import contacts, mongo
from ..auth import current_seller
from ..models import Seller
from .deps import company_or_404

router = APIRouter(tags=["contacts"])

Level = Literal["c_level", "director", "manager", "other", "unknown"]


class ContactSource(BaseModel):
    source: str
    url: str = ""
    evidence: str = ""
    found_at: object | None = None


class ContactOut(BaseModel):
    id: int
    company_id: int
    name: str | None = None
    role: str | None = None
    level: Level = "unknown"
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    verified: bool = False
    sources: list[ContactSource]
    do_not_contact: bool = False
    added_by: str | None = None


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(None, max_length=40)
    linkedin: str | None = Field(None, max_length=300, pattern=r"^https://([a-z]+\.)?linkedin\.com/")
    note: str | None = Field(None, max_length=300, description="where the seller got it, e.g. 'phone call with reception'")


class ContactUpdate(BaseModel):
    do_not_contact: bool | None = None


class SentIn(BaseModel):
    channel: Literal["email", "linkedin", "phone"]


def _out(c: mongo.MDoc) -> ContactOut:
    return ContactOut(id=c.id, **{k: v for k, v in c.items() if k in ContactOut.model_fields and k != "id"})


def _contact_or_404(contact_id: int) -> mongo.MDoc:
    c = mongo.get(contacts.CONTACTS, contact_id)
    if c is None:
        raise HTTPException(404, "Contact not found")
    return c


@router.get("/companies/{company_id}/contacts", response_model=list[ContactOut],
            summary="Decision makers and published contact details, decision makers first")
def list_company_contacts(company_id: int):
    company_or_404(company_id)
    return [_out(c) for c in contacts.list_contacts(company_id)]


@router.post("/companies/{company_id}/contacts/discover", tags=["contacts"],
             summary="Look for contacts on the company's own site, in its news and (with a key) Hunter.io / Apollo.io")
async def discover_contacts(company_id: int):
    company = company_or_404(company_id)
    stats = await contacts.discover(company)
    return {"stats": stats, "contacts": [_out(c) for c in contacts.list_contacts(company_id)]}


@router.post("/companies/{company_id}/contacts", response_model=ContactOut, status_code=201,
             summary="Add a contact by hand (marked as added by this seller)")
def add_contact(company_id: int, body: ContactIn, seller: Seller = Depends(current_seller)):
    company_or_404(company_id)
    if not (body.email or body.phone or body.linkedin):
        raise HTTPException(422, "Add at least an e-mail, a phone number or a LinkedIn profile")
    evidence = f"Adăugat manual de {seller.full_name}" + (f": {body.note.strip()}" if body.note and body.note.strip() else "")
    contacts.save_found(company_id, [{
        "name": body.name.strip(), "role": (body.role or "").strip() or None, "level": contacts.role_level(body.role or "") or "other",
        "email": body.email.lower() if body.email else None, "phone": body.phone, "linkedin": body.linkedin,
        "source": "manual", "url": "", "evidence": evidence,
    }])
    row = next((c for c in contacts.list_contacts(company_id)
                if (body.email and c.email == body.email.lower()) or c.name == body.name.strip()), None)
    if row is None:
        raise HTTPException(500, "Contact was not saved")
    if not row.added_by:
        mongo.update(contacts.CONTACTS, row.id, {"added_by": seller.full_name})
        row.added_by = seller.full_name
    return _out(row)


@router.put("/contacts/{contact_id}", response_model=ContactOut, summary="Mark or unmark 'do not contact'")
def update_contact(contact_id: int, body: ContactUpdate, seller: Seller = Depends(current_seller)):
    c = _contact_or_404(contact_id)
    if body.do_not_contact is not None and body.do_not_contact != c.do_not_contact:
        mongo.update(contacts.CONTACTS, contact_id, {"do_not_contact": body.do_not_contact})
        c.do_not_contact = body.do_not_contact
        mongo.log_activity("contact_do_not_contact" if body.do_not_contact else "contact_allowed", seller,
                           company_id=c.company_id, target=c.name or c.email or c.phone)
    return _out(c)


@router.delete("/contacts/{contact_id}", status_code=204,
               summary="Delete a contact: an admin any, a seller only the ones they added by hand")
def delete_contact(contact_id: int, seller: Seller = Depends(current_seller)):
    c = _contact_or_404(contact_id)
    if seller.role != "admin" and c.added_by != seller.full_name:
        raise HTTPException(403, "Only an admin, or the seller who added it, can delete a contact")
    mongo.db()[contacts.CONTACTS].delete_one({"_id": contact_id})
    return Response(status_code=204)


@router.post("/contacts/{contact_id}/sent", status_code=204, summary="Record that a message was sent to this contact")
def message_sent(contact_id: int, body: SentIn, seller: Seller = Depends(current_seller)):
    c = _contact_or_404(contact_id)
    if c.do_not_contact:
        raise HTTPException(409, "This contact asked not to be contacted")
    mongo.log_activity("contact_message", seller, company_id=c.company_id, target=c.name or c.email, channel=body.channel)
    return Response(status_code=204)
