import re
from datetime import datetime

from pydantic import BaseModel


def mask_passport(passport: str | None) -> str | None:
    """Server-side masking so the raw API response never carries the full
    number -- the key gating this API is embedded in the public frontend
    bundle, so UI-only masking would be purely cosmetic."""
    if not passport:
        return passport
    compact = re.sub(r"\s+", "", passport).upper()
    m = re.match(r"^([A-Z]{1,3})(\d{4,7})$", compact)
    if not m:
        return compact
    letters, digits = m.groups()
    if len(digits) < 4:
        return f"{letters}{digits}"
    return f"{letters}{digits[:1]}***{digits[-2:]}"


def mask_telegram_id(chat_id: str | None) -> str | None:
    """Same reasoning as mask_passport -- never return the full ID from the
    raw API, only the last 3 digits for the owner to recognize which
    registration is theirs."""
    if not chat_id:
        return chat_id
    compact = chat_id.strip()
    if len(compact) <= 3:
        return compact
    return f"***{compact[-3:]}"


def mask_name(name: str) -> str:
    """Privacy mask for the public Alerts view -- keeps roughly the first
    half of each word, replaces the rest with X, preserving word count and
    length (e.g. "KAUNG HTET" -> "KAUXX HTXX"). The underlying embassy list
    entry is public info either way; this masks the fact that THIS
    specific person is a user of our notification service."""
    if not name:
        return name
    words = name.upper().split()
    masked = []
    for w in words:
        if len(w) <= 2:
            masked.append(w)
            continue
        keep = -(-len(w) // 2)  # ceil(len/2)
        masked.append(w[:keep] + "X" * (len(w) - keep))
    return " ".join(masked)


class WatchlistIn(BaseModel):
    full_name: str
    passport_no: str | None = None
    telegram_chat_id: str | None = None
    note: str | None = None


class WatchlistUpdate(BaseModel):
    full_name: str | None = None
    passport_no: str | None = None
    telegram_chat_id: str | None = None
    note: str | None = None
    active: bool | None = None


class WatchlistOut(BaseModel):
    id: int
    full_name: str
    passport_no: str | None
    telegram_chat_id: str | None
    note: str | None
    active: bool
    lookup_token: str | None
    created_at: datetime
    # only populated by POST /api/watchlist, so the signup form can tell the
    # user whether their confirmation message actually sent -- None on
    # every other response (GET/PATCH), where it's not relevant
    telegram_sent: bool | None = None
    telegram_error: str | None = None

    class Config:
        from_attributes = True


class PublicStatusOut(BaseModel):
    """What the person who signed up sees when checking their own status --
    deliberately thin: no telegram_chat_id, no note, nothing about anyone
    else. The lookup_token itself is the only credential needed."""
    full_name: str
    passport_no: str | None
    active: bool
    status: str  # "pending" | "matched" | "paused"
    appointment_date: str | None = None
    matched_name_on_list: str | None = None
    matched_source: str | None = None


class EntryOut(BaseModel):
    id: int
    page_no: int
    name: str
    passport_no: str
    id_kind: str
    approved_date: str | None
    remark: str | None

    class Config:
        from_attributes = True


class SnapshotOut(BaseModel):
    id: int
    fetched_at: datetime
    source: str
    page_count: int
    mode: str
    row_count: int

    class Config:
        from_attributes = True


class EntrySearchResult(BaseModel):
    id: int
    page_no: int
    name: str
    passport_no: str
    id_kind: str
    approved_date: str | None
    remark: str | None
    snapshot_id: int
    source: str
    fetched_at: datetime


class ExtractionIssueOut(BaseModel):
    id: int
    snapshot_id: int
    page_no: int
    kind: str
    detail: str | None

    class Config:
        from_attributes = True


class MatchOut(BaseModel):
    id: int
    watchlist_id: int
    watchlist_name: str
    entry: EntryOut
    snapshot_id: int
    source: str
    confidence: str
    matched_on: str
    score: int
    created_at: datetime


class PublicMatchOut(BaseModel):
    """Alerts view for anonymous visitors: both names masked (the person is
    one of our users, not just someone on the embassy's public list), the
    passport already masked, and no internal matching details."""
    watchlist_name_masked: str
    entry_name_masked: str
    passport_no: str | None
    approved_date: str | None
    source: str
    created_at: datetime


class PublicStats(BaseModel):
    total_users: int
