import logging
import os
import secrets

import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session

from checker import db as models
from checker.notify import send_message

from .auth import get_db, require_session
from .schemas import (
    EntryOut, EntrySearchResult, ExtractionIssueOut, MatchOut, PublicMatchOut, PublicStats, PublicStatusOut,
    SnapshotOut, WatchlistIn, WatchlistOut, WatchlistUpdate, mask_name, mask_passport, mask_telegram_id,
)
from .webauthn_routes import router as webauthn_router

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="MMR Passport Renewal Monitor API")

# explicit origin (not "*") so a browser can't be tricked into sending the
# bearer token from an unexpected page; sessions are a header, not a
# cookie, so allow_credentials is not needed
origins = [o.strip() for o in os.environ.get("FRONTEND_ORIGIN", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webauthn_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _to_watchlist_out(
    entry: models.Watchlist, telegram_sent: bool | None = None, telegram_error: str | None = None,
) -> WatchlistOut:
    # the server must not hand back full passport/Telegram numbers --
    # UI-only masking is meaningless once a real login gate exists, but
    # keeping it server-side too costs nothing and limits what a stolen
    # session cookie alone would expose
    return WatchlistOut(
        id=entry.id, full_name=entry.full_name, passport_no=mask_passport(entry.passport_no),
        telegram_chat_id=mask_telegram_id(entry.telegram_chat_id),
        note=entry.note, active=entry.active, lookup_token=entry.lookup_token, created_at=entry.created_at,
        telegram_sent=telegram_sent, telegram_error=telegram_error,
    )


def _try_send(text: str, chat_id: str) -> tuple[bool, str | None]:
    """Best-effort Telegram send -- a bad chat id or missing bot config must
    never block the signup itself, but the caller still needs to know
    whether it actually worked so the frontend can tell the user."""
    try:
        send_message(text, chat_id=chat_id)
        return True, None
    except Exception as e:
        log.exception("Failed to send Telegram message")
        return False, str(e)


@app.get("/api/watchlist", response_model=list[WatchlistOut], dependencies=[Depends(require_session)])
def list_watchlist(session: Session = Depends(get_db)):
    rows = session.query(models.Watchlist).order_by(models.Watchlist.created_at.desc()).all()
    return [_to_watchlist_out(w) for w in rows]


def _status_url(token: str) -> str:
    base = os.environ.get("FRONTEND_ORIGIN", "").split(",")[0].strip()
    return f"{base}/status/{token}" if base else f"/status/{token}"


@app.post("/api/watchlist", response_model=WatchlistOut)
def create_watchlist(payload: WatchlistIn, session: Session = Depends(get_db)):
    # intentionally public, no session required -- this is the self-service
    # signup anyone with the link can use to add themselves and get
    # notified; only VIEWING/managing the list requires the admin login

    # re-submitting the same details (e.g. revisiting the site) retrieves
    # the existing registration instead of creating a duplicate -- matches
    # on telegram id or passport number, whichever was provided
    existing = None
    if payload.telegram_chat_id:
        existing = session.query(models.Watchlist).filter_by(telegram_chat_id=payload.telegram_chat_id).first()
    if existing is None and payload.passport_no:
        existing = session.query(models.Watchlist).filter_by(passport_no=payload.passport_no).first()

    if existing is not None:
        if not existing.lookup_token:
            existing.lookup_token = secrets.token_urlsafe(16)
        # fill in anything the existing record was missing (e.g. an
        # admin-created entry that predates the Telegram ID field) rather
        # than silently ignoring newly-submitted details
        if payload.telegram_chat_id and not existing.telegram_chat_id:
            existing.telegram_chat_id = payload.telegram_chat_id
        if payload.passport_no and not existing.passport_no:
            existing.passport_no = payload.passport_no
        if payload.note and not existing.note:
            existing.note = payload.note
        session.commit()
        session.refresh(existing)

        telegram_sent = telegram_error = None
        if existing.telegram_chat_id:
            telegram_sent, telegram_error = _try_send(
                f"👋 Welcome back, {existing.full_name} — you're already registered.\n\n"
                f"Check your status anytime: {_status_url(existing.lookup_token)}",
                chat_id=existing.telegram_chat_id,
            )
        return _to_watchlist_out(existing, telegram_sent, telegram_error)

    token = secrets.token_urlsafe(16)
    entry = models.Watchlist(
        full_name=payload.full_name, passport_no=payload.passport_no,
        telegram_chat_id=payload.telegram_chat_id, note=payload.note, lookup_token=token,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)

    telegram_sent = telegram_error = None
    if payload.telegram_chat_id:
        telegram_sent, telegram_error = _try_send(
            f"👋 Hi {payload.full_name}, you're now registered with the MMR Passport Renewal Monitor.\n\n"
            f"You are not on the embassy's list yet. The moment your name and passport number appear on "
            f"either the approval list or a renewal appointment post, we'll notify you right here in this "
            f"chat.\n\nCheck your status anytime: {_status_url(token)}",
            chat_id=payload.telegram_chat_id,
        )

    return _to_watchlist_out(entry, telegram_sent, telegram_error)


@app.get("/api/public/stats", response_model=PublicStats)
def public_stats(session: Session = Depends(get_db)):
    total = session.query(models.Watchlist).count()
    return PublicStats(total_users=total)


@app.get("/api/public/matches", response_model=list[PublicMatchOut])
def public_matches(session: Session = Depends(get_db)):
    """Same data as /api/matches, but for anonymous visitors: both names
    masked, no internal matching-score details."""
    rows = session.query(models.MatchRecord).order_by(models.MatchRecord.created_at.desc()).all()
    out = []
    for m in rows:
        entry = session.get(models.Entry, m.entry_id)
        watch = session.get(models.Watchlist, m.watchlist_id)
        if entry is None:
            continue
        out.append(PublicMatchOut(
            watchlist_name_masked=mask_name(watch.full_name) if watch else "(removed)",
            entry_name_masked=mask_name(entry.name),
            passport_no=mask_passport(entry.passport_no),
            approved_date=entry.approved_date,
            source=m.source,
            created_at=m.created_at,
        ))
    return out


@app.get("/api/watchlist/status/{token}", response_model=PublicStatusOut)
def watchlist_status(token: str, session: Session = Depends(get_db)):
    """Public, no login -- the lookup_token itself is the credential. Lets
    someone who signed up check only their own status, nothing about
    anyone else on the list."""
    entry = session.query(models.Watchlist).filter_by(lookup_token=token).first()
    if entry is None:
        raise HTTPException(404, "Not found")

    if not entry.active:
        status = "paused"
    else:
        status = "pending"

    match = (
        session.query(models.MatchRecord)
        .filter_by(watchlist_id=entry.id)
        .order_by(models.MatchRecord.created_at.desc())
        .first()
    )
    matched_entry = session.get(models.Entry, match.entry_id) if match else None

    if entry.active and matched_entry is not None:
        status = "matched"

    return PublicStatusOut(
        full_name=entry.full_name, passport_no=mask_passport(entry.passport_no), active=entry.active,
        status=status,
        appointment_date=matched_entry.approved_date if matched_entry else None,
        matched_name_on_list=matched_entry.name if matched_entry else None,
        matched_source=match.source if match else None,
    )


@app.patch("/api/watchlist/{entry_id}", response_model=WatchlistOut, dependencies=[Depends(require_session)])
def update_watchlist(entry_id: int, payload: WatchlistUpdate, session: Session = Depends(get_db)):
    entry = session.get(models.Watchlist, entry_id)
    if entry is None:
        raise HTTPException(404, "Not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    session.commit()
    session.refresh(entry)
    return _to_watchlist_out(entry)


@app.delete("/api/watchlist/{entry_id}", status_code=204, dependencies=[Depends(require_session)])
def delete_watchlist(entry_id: int, session: Session = Depends(get_db)):
    entry = session.get(models.Watchlist, entry_id)
    if entry is None:
        raise HTTPException(404, "Not found")
    session.delete(entry)
    session.commit()


@app.get("/api/matches", response_model=list[MatchOut], dependencies=[Depends(require_session)])
def list_matches(session: Session = Depends(get_db)):
    rows = session.query(models.MatchRecord).order_by(models.MatchRecord.created_at.desc()).all()
    out = []
    for m in rows:
        entry = session.get(models.Entry, m.entry_id)
        watch = session.get(models.Watchlist, m.watchlist_id)
        out.append(MatchOut(
            id=m.id, watchlist_id=m.watchlist_id, watchlist_name=watch.full_name if watch else "(deleted)",
            entry=EntryOut.model_validate(entry), snapshot_id=m.snapshot_id, source=m.source,
            confidence=m.confidence, matched_on=m.matched_on, score=m.score, created_at=m.created_at,
        ))
    return out


@app.delete("/api/matches/{match_id}", status_code=204, dependencies=[Depends(require_session)])
def dismiss_match(match_id: int, session: Session = Depends(get_db)):
    match = session.get(models.MatchRecord, match_id)
    if match is None:
        raise HTTPException(404, "Not found")
    session.delete(match)
    session.commit()


@app.get("/api/snapshots", response_model=list[SnapshotOut])
def list_snapshots(session: Session = Depends(get_db)):
    return session.query(models.Snapshot).order_by(models.Snapshot.fetched_at.desc()).all()


@app.get("/api/extraction-issues", response_model=list[ExtractionIssueOut], dependencies=[Depends(require_session)])
def list_extraction_issues(session: Session = Depends(get_db)):
    return session.query(models.ExtractionIssue).order_by(models.ExtractionIssue.id.desc()).all()


@app.get("/api/snapshots/{snapshot_id}/entries", response_model=list[EntryOut])
def snapshot_entries(snapshot_id: int, q: str = Query(default=""), session: Session = Depends(get_db)):
    query = session.query(models.Entry).filter_by(snapshot_id=snapshot_id)
    if q:
        like = f"%{q.upper()}%"
        query = query.filter(or_(models.Entry.name.ilike(like), models.Entry.passport_no.ilike(like)))
    return query.order_by(models.Entry.page_no, models.Entry.id).all()


@app.get("/api/entries/search", response_model=list[EntrySearchResult])
def search_entries(q: str = Query(min_length=2), limit: int = Query(default=200, le=500), session: Session = Depends(get_db)):
    """Searches every entry ever recorded, across all snapshots/sources."""
    like = f"%{q.upper()}%"
    rows = (
        session.query(models.Entry, models.Snapshot)
        .join(models.Snapshot, models.Entry.snapshot_id == models.Snapshot.id)
        .filter(or_(models.Entry.name.ilike(like), models.Entry.passport_no.ilike(like)))
        .order_by(models.Snapshot.fetched_at.desc())
        .limit(limit)
        .all()
    )
    return [
        EntrySearchResult(
            id=e.id, page_no=e.page_no, name=e.name, passport_no=e.passport_no, id_kind=e.id_kind,
            approved_date=e.approved_date, remark=e.remark,
            snapshot_id=s.id, source=s.source, fetched_at=s.fetched_at,
        )
        for e, s in rows
    ]


@app.post("/api/check-now", dependencies=[Depends(require_session)])
def check_now():
    token = os.environ.get("GH_DISPATCH_TOKEN")
    repo = os.environ.get("GH_REPO", "KaungOrYours/MMR_PassportRenewal_Monitoring")
    if not token:
        raise HTTPException(500, "GH_DISPATCH_TOKEN not configured on the server")

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/check.yml/dispatches",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"ref": "main"},
        timeout=15,
    )
    if resp.status_code != 204:
        raise HTTPException(502, f"GitHub dispatch failed: {resp.status_code} {resp.text}")
    return {"status": "dispatched"}
