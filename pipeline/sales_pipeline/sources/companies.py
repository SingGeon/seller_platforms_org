"""Company-name normalisation and extraction from free text.

The same company shows up as "GitLab Inc.", "GitLab" and "GITLAB INC (GTLB)";
discovery resolves them to one lead by web domain first, then by normalised name.
"""
from __future__ import annotations

import re
import unicodedata

LEGAL_SUFFIXES = [
    "incorporated", "inc", "corporation", "corp", "company", "co", "limited", "ltd", "llc", "llp", "lp", "plc",
    "gmbh", "ag", "kg", "kgaa", "se", "sa", "s a", "sas", "sarl", "srl", "s r l", "spa", "s p a", "bv", "nv", "ab",
    "as", "a s", "asa", "oy", "oyj", "sp z o o", "sro", "s r o", "doo", "d o o", "kft", "zrt", "nyrt", "pte", "pty",
    "aktiengesellschaft", "gesellschaft mit beschrankter haftung", "societe anonyme", "sociedad anonima", "societa per azioni",
    "spolka akcyjna", "spolka z ograniczona odpowiedzialnoscia", "societate pe actiuni", "societate cu raspundere limitata",
    "naamloze vennootschap", "besloten vennootschap", "aktiebolag", "public limited company",
    "holding", "holdings", "group", "the",
]
_SUFFIX_RE = re.compile(r"(?:\s+(?:" + "|".join(re.escape(s) for s in sorted(LEGAL_SUFFIXES, key=len, reverse=True)) + r"))+$")


def normalize_company_name(name: str) -> str:
    """Lower-case, strip accents, punctuation, ticker/CIK suffixes and legal forms.

    >>> normalize_company_name("GITLAB INC.  (GTLB)  (CIK 0001653482)")
    'gitlab'
    """
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", " ", s)  # tickers, CIKs, "(formerly ...)"
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"^the\s+", "", s)
    prev = None
    while prev != s:
        prev = s
        s = _SUFFIX_RE.sub("", s).strip()
    return s


_DISPLAY_SUFFIX_RE = re.compile(
    r"(?:[\s,]+(?:" + "|".join(re.escape(x).replace(r"\ ", r"[\s.]*") for x in sorted(
        [x for x in LEGAL_SUFFIXES if x not in ("group", "the", "company", "co", "holding", "holdings")], key=len, reverse=True
    )) + r")\.?)+$",
    re.I,
)


def search_name(name: str) -> str:
    """Name as the press writes it: 'Banca Transilvania S.A.' -> 'Banca Transilvania' (case kept)."""
    s = re.sub(r"\s*\(.*?\)\s*", " ", name or "").strip()
    stripped = _DISPLAY_SUFFIX_RE.sub("", s).strip(" ,.")
    return stripped or s


def _plain(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", s).strip() + " "


def mentions(name: str, text: str) -> bool:
    """Does `text` mention the company (accent/punctuation-insensitive, legal form optional)?"""
    needle = _plain(search_name(name)).strip()
    return bool(needle) and f" {needle} " in _plain(text)


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = v.split("/")[0].split("?")[0].split(":")[0]
    v = v.removeprefix("www.")
    if "." not in v or " " in v:
        return None
    return v


def clean_display_name(name: str) -> str:
    """'ACME CORP  (ACME)  (CIK 0000123)' -> 'ACME CORP'"""
    s = re.sub(r"\s*\((?:CIK|[A-Z0-9.\-, ]{1,12})[^)]*\)", "", name or "")
    return re.sub(r"\s+", " ", s).strip(" ,;-|")


# Press-release headline: "<Company> Announces ...", "<Company> Appoints ...".
_PR_VERBS = (
    "announces|announced|launches|launched|appoints|appointed|names|named|reports|reported|acquires|acquired|"
    "partners|selects|selected|completes|completed|expands|unveils|introduces|signs|signed|raises|raised|"
    "secures|secured|joins|opens|deploys|chooses|confirms|discloses|hit by|suffers|notifies|agrees|enters|"
    "to acquire|to launch|welcomes|hires|taps|adopts|migrates"
)
_PR_RE = re.compile(r"^(?P<co>[A-Z0-9][\w&.,'’\- ]{1,70}?)\s+(?:" + _PR_VERBS + r")\b", re.I)


def company_from_headline(title: str) -> str | None:
    title = re.sub(r"\s+[-–|]\s+[^-–|]{2,60}$", "", title or "").strip()  # drop " - Publisher"
    m = _PR_RE.match(title)
    if not m:
        return None
    co = m.group("co").strip(" ,")
    words = co.split()
    if len(words) > 7 or co.lower() in {"it", "the company", "report", "study", "survey", "new", "why", "how"}:
        return None
    return co


def company_from_hn_post(text: str) -> str | None:
    """HN 'Who is hiring' convention: 'Company | Role | Location | ...'."""
    first = re.sub(r"<[^>]+>", " ", text or "").strip().split("\n")[0]
    if "|" not in first:
        return None
    co = first.split("|")[0].strip()
    co = re.sub(r"\s*\(.*?\)\s*", " ", co).strip()
    return co if 1 < len(co) <= 60 else None
