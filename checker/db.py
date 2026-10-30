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
    telegram_chat_id = Column(String, nullable=True)  # alerts go here if set, else the operator's default chat
    note = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    lookup_token = Column(String, nullable=True, unique=True)  # lets the person who signed up check their own status, no login
    terms_accepted_at = Column(DateTime(timezone=True), nullable=True)  # durable consent record, not just a UI checkbox
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


def delete_watchlist_entry(session, entry: "Watchlist") -> None:
    """Deletes a Watchlist row safely. watchlist_id on MatchRecord has no
    ondelete=CASCADE (and no ORM cascade relationship either), so deleting
    the parent row directly would violate the foreign key constraint for
    anyone who already has a recorded match -- callers must not just
    session.delete(entry) on its own."""
    session.query(MatchRecord).filter_by(watchlist_id=entry.id).delete()
    session.delete(entry)


class WebAuthnCredential(Base):
    """A registered Passkey (Face ID/Touch ID-backed). Each device the
    admin enrolls gets its own row -- there is no username/password, the
    device's Secure Enclave key pair IS the credential."""
    __tablename__ = "webauthn_credentials"

    id = Column(Integer, primary_key=True)
    credential_id = Column(String, nullable=False, unique=True)  # base64url
    public_key = Column(String, nullable=False)  # base64url COSE key
    sign_count = Column(Integer, nullable=False, default=0)
    device_label = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AdminSession(Base):
    """Issued after a successful Passkey authentication; the browser holds
    this as an HttpOnly cookie."""
    __tablename__ = "admin_sessions"

    token = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)


class WebAuthnChallenge(Base):
    """Short-lived storage for the challenge issued by a /begin call, looked
    up again by the matching /complete call. Self-contained row per
    ceremony rather than relying on an in-memory dict (stateless across
    requests/dynos)."""
    __tablename__ = "webauthn_challenges"

    token = Column(String, primary_key=True)
    challenge = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # "registration" | "authentication"
    expires_at = Column(DateTime(timezone=True), nullable=False)


class EnrollmentCode(Base):
    """One-time code generated by an already-logged-in session, entered on
    a second device to authorize registering it as a new credential --
    avoids ever reusing API_SECRET beyond the very first device."""
    __tablename__ = "enrollment_codes"

    code = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, default=False)


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
    ("watchlist", "telegram_chat_id", "VARCHAR"),
    ("watchlist", "lookup_token", "VARCHAR"),
    ("watchlist", "terms_accepted_at", "TIMESTAMPTZ"),
    ("matches", "notified_at", "TIMESTAMPTZ"),
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
