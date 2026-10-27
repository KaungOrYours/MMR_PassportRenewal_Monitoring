"""Session-based admin auth backed by WebAuthn Passkeys.

There is no username/password and no standing API key for the web GUI --
a registered device's Face ID/Touch ID key pair IS the credential. See
webauthn_routes.py for the registration/login ceremonies; this module is
just the session cookie issuance/verification every other route depends on.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from checker import db as models

SESSION_COOKIE = "admin_session"
SESSION_TTL_DAYS = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def not_expired(expires_at: datetime) -> bool:
    """SQLite (used in local/dev testing) doesn't round-trip tzinfo the way
    Postgres does, so a value read back can come out naive even though it
    was stored timezone-aware -- normalize before comparing."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > utcnow()


def get_db():
    session = models.get_session()
    try:
        yield session
    finally:
        session.close()


def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Gates ONLY the very first device's bootstrap registration -- see
    webauthn_routes.register_begin. Every other route uses require_session;
    this key is never used again once one credential exists."""
    expected = os.environ.get("API_SECRET", "")
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def create_session(db: Session) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(days=SESSION_TTL_DAYS)
    db.add(models.AdminSession(token=token, expires_at=expires_at))
    db.commit()
    return token, expires_at


def require_session(
    admin_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> None:
    if not admin_session:
        raise HTTPException(401, "Not logged in")
    row = db.get(models.AdminSession, admin_session)
    if row is None or not not_expired(row.expires_at):
        raise HTTPException(401, "Session expired or invalid")
