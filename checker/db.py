"""Minimal SQLAlchemy models + session helper for the checker's own writes.

The backend API (backend/) owns the richer CRUD surface over this same
schema; this module only needs enough to read the watchlist and persist a
check run's results, so it stays dependency-light for the GitHub Actions
runner.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    full_name = Column(String, nullable=False)
    passport_no = Column(String, nullable=True)
    note = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source = Column(String, nullable=False, default="embassy_pdf")  # "embassy_pdf" | "telegram_renewal"
    external_ref = Column(String, nullable=True)  # e.g. highest Telegram message id in this post, for dedup
    etag = Column(String, nullable=True)
    last_modified = Column(String, nullable=True)
    sha256 = Column(String, nullable=False, unique=True)
    page_count = Column(Integer, nullable=False)
    mode = Column(String, nullable=False)  # "text" | "ocr"
    row_count = Column(Integer, nullable=False)

    entries = relationship("Entry", back_populates="snapshot", cascade="all, delete-orphan")
    issues = relationship("ExtractionIssue", back_populates="snapshot", cascade="all, delete-orphan")


class Entry(Base):
    __tablename__ = "entries"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False)
    page_no = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    passport_no = Column(String, nullable=False)
    id_kind = Column(String, nullable=False)  # "passport" | "other" | "masked_passport"
    approved_date = Column(String, nullable=True)
    remark = Column(Text, nullable=True)

    snapshot = relationship("Snapshot", back_populates="entries")


class ExtractionIssue(Base):
    __tablename__ = "extraction_issues"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False)
    page_no = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)
    detail = Column(Text, nullable=True)

    snapshot = relationship("Snapshot", back_populates="issues")


class MatchRecord(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("watchlist_id", "passport_canonical", name="uq_watchlist_passport"),)

    id = Column(Integer, primary_key=True)
    watchlist_id = Column(Integer, ForeignKey("watchlist.id"), nullable=False)
    entry_id = Column(Integer, ForeignKey("entries.id"), nullable=False)
    snapshot_id = Column(Integer, ForeignKey("snapshots.id"), nullable=False)
    source = Column(String, nullable=False, default="embassy_pdf")  # "embassy_pdf" | "telegram_renewal"
    passport_canonical = Column(String, nullable=False)
    confidence = Column(String, nullable=False)  # "high" | "medium"
    matched_on = Column(String, nullable=False)
    score = Column(Integer, nullable=False)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def get_engine(database_url: str | None = None):
    url = database_url or os.environ["NEON_DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


# columns added after the initial deploy -- create_all() only creates
# missing TABLES, not missing columns on existing ones, so a live DB needs
# these added explicitly. No Alembic for a schema this small; this is a
# plain additive ADD COLUMN, safe to run every startup.
_ADDITIVE_COLUMNS = [
    ("snapshots", "source", "VARCHAR DEFAULT 'embassy_pdf'"),
    ("snapshots", "external_ref", "VARCHAR"),
    ("matches", "source", "VARCHAR DEFAULT 'embassy_pdf'"),
]


def _migrate_additive_columns(engine) -> None:
    is_sqlite = engine.dialect.name == "sqlite"
    with engine.begin() as conn:
        for table, column, coltype in _ADDITIVE_COLUMNS:
            if is_sqlite:
                existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                if column in existing:
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            else:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")


def get_session(database_url: str | None = None):
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    _migrate_additive_columns(engine)
    return sessionmaker(bind=engine)()
