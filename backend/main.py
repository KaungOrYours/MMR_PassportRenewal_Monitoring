import os

import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session

from checker import db as models

from .auth import require_api_key
from .schemas import (
    EntryOut, MatchOut, SnapshotOut, WatchlistIn, WatchlistOut, WatchlistUpdate,
)

app = FastAPI(title="MMR Passport Renewal Monitor API")

origins = os.environ.get("FRONTEND_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    session = models.get_session()
    try:
        yield session
    finally:
        session.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/watchlist", response_model=list[WatchlistOut], dependencies=[Depends(require_api_key)])
def list_watchlist(session: Session = Depends(get_db)):
    return session.query(models.Watchlist).order_by(models.Watchlist.created_at.desc()).all()


@app.post("/api/watchlist", response_model=WatchlistOut, dependencies=[Depends(require_api_key)])
def create_watchlist(payload: WatchlistIn, session: Session = Depends(get_db)):
    entry = models.Watchlist(full_name=payload.full_name, passport_no=payload.passport_no, note=payload.note)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@app.patch("/api/watchlist/{entry_id}", response_model=WatchlistOut, dependencies=[Depends(require_api_key)])
def update_watchlist(entry_id: int, payload: WatchlistUpdate, session: Session = Depends(get_db)):
    entry = session.get(models.Watchlist, entry_id)
    if entry is None:
        raise HTTPException(404, "Not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    session.commit()
    session.refresh(entry)
    return entry


@app.delete("/api/watchlist/{entry_id}", status_code=204, dependencies=[Depends(require_api_key)])
def delete_watchlist(entry_id: int, session: Session = Depends(get_db)):
    entry = session.get(models.Watchlist, entry_id)
    if entry is None:
        raise HTTPException(404, "Not found")
    session.delete(entry)
    session.commit()


@app.get("/api/matches", response_model=list[MatchOut], dependencies=[Depends(require_api_key)])
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


@app.get("/api/snapshots", response_model=list[SnapshotOut], dependencies=[Depends(require_api_key)])
def list_snapshots(session: Session = Depends(get_db)):
    return session.query(models.Snapshot).order_by(models.Snapshot.fetched_at.desc()).all()


@app.get("/api/snapshots/{snapshot_id}/entries", response_model=list[EntryOut], dependencies=[Depends(require_api_key)])
def snapshot_entries(snapshot_id: int, q: str = Query(default=""), session: Session = Depends(get_db)):
    query = session.query(models.Entry).filter_by(snapshot_id=snapshot_id)
    if q:
        like = f"%{q.upper()}%"
        query = query.filter(or_(models.Entry.name.ilike(like), models.Entry.passport_no.ilike(like)))
    return query.order_by(models.Entry.page_no, models.Entry.id).all()


@app.post("/api/check-now", dependencies=[Depends(require_api_key)])
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
