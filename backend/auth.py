"""Session-based admin auth backed by WebAuthn Passkeys.

There is no username/password and no standing API key for the web GUI --
a registered device's Face ID/Touch ID key pair IS the credential. See
webauthn_routes.py for the registration/login ceremonies.

Sessions are a bearer token (Authorization: Bearer <token>), not a cookie:
the frontend (vercel.app) and backend (onrender.com) are different
registrable domains, and Safari's Intelligent Tracking Prevention silently
drops cross-site cookies even with SameSite=None; Secure set correctly --
confirmed live (the dashboard rendered as "logged in" immediately after
registration, then every subsequent request 401'd because the cookie never
actually made it into Safari's cookie jar). A bearer token sent explicitly
by the frontend's JS sidesteps third-party-cookie blocking entirely.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from checker import db as models

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


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer "):].strip() or None


def get_session_row(authorization: str | None, db: Session) -> models.AdminSession | None:
    token = _extract_bearer(authorization)
    if not token:
        return None
    row = db.get(models.AdminSession, token)
    if row is None or not not_expired(row.expires_at):
        return None
    return row


def require_session(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    if get_session_row(authorization, db) is None:
        raise HTTPException(401, "Not logged in")
