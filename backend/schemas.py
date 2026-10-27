from datetime import datetime

from pydantic import BaseModel


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
