"""Common `Document` model shared by every collector (GIG-23).

Every source (news, company website, job boards, Crunchbase) is normalised into
this shape before it is stored in `raw_documents` or fed to the AI pipeline.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

SourceType = Literal["news", "web", "jobs", "crunchbase", "manual"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_url(url: str) -> str:
    url = url.strip()
    url = re.sub(r"#.*$", "", url)
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid)=[^&]*", "", url)
    return url.rstrip("/").lower()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class Document(BaseModel):
    source_type: SourceType
    url: str
    title: str = ""
    text: str = ""
    published_at: datetime | None = None
    source: str = ""  # publisher / board / site name
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        basis = normalize_url(self.url) + "\n" + clean_text(self.title) + "\n" + clean_text(self.text)[:5000]
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    @property
    def date_str(self) -> str:
        return self.published_at.date().isoformat() if self.published_at else "unknown"


def dedupe(docs: list[Document], title_threshold: int = 90) -> list[Document]:
    """Drop duplicates by normalised URL, then by near-identical titles.

    The same press release is often syndicated by dozens of outlets, so title
    similarity catches what URL comparison misses.
    """
    seen_urls: set[str] = set()
    kept: list[Document] = []
    for doc in docs:
        key = normalize_url(doc.url)
        if key in seen_urls:
            continue
        title = clean_text(doc.title).lower()
        if title and len(title) > 20 and any(
            k.source_type == doc.source_type
            and fuzz.ratio(title, clean_text(k.title).lower()) >= title_threshold
            for k in kept
        ):
            continue
        seen_urls.add(key)
        kept.append(doc)
    return kept


def docs_hash(docs: list[Document]) -> str:
    """Stable hash over a set of documents, used as an LLM cache key (GIG-28)."""
    h = hashlib.sha256()
    for digest in sorted(d.content_hash for d in docs):
        h.update(digest.encode())
    return h.hexdigest()
