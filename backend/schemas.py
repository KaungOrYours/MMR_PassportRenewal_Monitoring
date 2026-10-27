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


class WatchlistIn(BaseModel):
    full_name: str
    passport_no: str | None = None
    note: str | None = None


class WatchlistUpdate(BaseModel):
    full_name: str | None = None
    passport_no: str | None = None
    note: str | None = None
    active: bool | None = None


class WatchlistOut(BaseModel):
    id: int
    full_name: str
    passport_no: str | None
    note: str | None
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


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
