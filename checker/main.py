"""Entry point: runs both checks the embassy publishes to --

1. the website's Lost & Seaman/Offshore approved-list PDF
2. the @mesg15 Telegram channel's PV/PJ passport-renewal appointment posts

Invoked on a schedule by .github/workflows/check.yml. Each check is
independent: a failure in one (e.g. Telegram API hiccup) does not block the
other, and each exits quietly (no DB writes, no notifications) when there is
nothing new since the last run.
"""
import hashlib
import logging
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db
from .extract import extract_pdf, ocr_image_bytes, reocr_page
from .fetch import fetch
from .match import WatchlistEntry, find_matches, find_renewal_matches
from .notify import (
    format_heartbeat, format_integrity_warning, format_match_alert,
    format_renewal_alert, format_renewal_heartbeat, send_document, send_message,
)
from .parse import parse_page
from .parse_renewal import parse_renewal_page
from . import telegram_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("checker")


def _latest_snapshot(session, source: str) -> db.Snapshot | None:
    return (
        session.query(db.Snapshot)
        .filter_by(source=source)
        .order_by(db.Snapshot.fetched_at.desc())
        .first()
    )


def _get_watchlist(session) -> tuple[list[db.Watchlist], list[WatchlistEntry]]:
    rows = session.query(db.Watchlist).filter_by(active=True).all()
    entries = [WatchlistEntry(id=w.id, full_name=w.full_name, passport_no=w.passport_no) for w in rows]
    return rows, entries


def run_embassy_pdf_check(session) -> None:
    prev = _latest_snapshot(session, "embassy_pdf")

    result = fetch(
        prev_etag=prev.etag if prev else None,
        prev_last_modified=prev.last_modified if prev else None,
        prev_sha256=prev.sha256 if prev else None,
    )

    if not result.changed:
        log.info("[embassy_pdf] No change since the last check.")
        return

    log.info("[embassy_pdf] New PDF content detected (sha256=%s). Processing...", result.sha256[:12])

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "approval.pdf"
        pdf_path.write_bytes(result.content)

        pages, mode = extract_pdf(pdf_path)

        all_rows = []
        issues = []
        for page in pages:
            parsed = parse_page(page.page_no, page.text)
            if parsed.has_gap and mode == "ocr":
                log.warning("[embassy_pdf] Integrity gap on page %d (rows=%d, markers=%d) -- retrying OCR",
                            page.page_no, parsed.row_count, parsed.index_marker_count)
                retry_text = reocr_page(pdf_path, page.page_no)
                retry_parsed = parse_page(page.page_no, retry_text)
                if retry_parsed.row_count > parsed.row_count:
                    parsed = retry_parsed

            if parsed.has_gap:
                detail = f"expected {parsed.index_marker_count} rows, recovered {parsed.row_count}"
                issues.append({"page_no": page.page_no, "kind": "row_count_mismatch", "detail": detail})
                log.error("[embassy_pdf] Unresolved integrity gap on page %d: %s", page.page_no, detail)

            all_rows.extend(parsed.rows)

        log.info("[embassy_pdf] Extracted %d rows across %d pages (mode=%s, %d integrity issue(s))",
                  len(all_rows), len(pages), mode, len(issues))

        snapshot = db.Snapshot(
            source="embassy_pdf", etag=result.etag, last_modified=result.last_modified, sha256=result.sha256,
            page_count=len(pages), mode=mode, row_count=len(all_rows),
        )
        session.add(snapshot)
        session.flush()

        entry_rows = []
        for row in all_rows:
            entry = db.Entry(
                snapshot_id=snapshot.id, page_no=row.page_no, name=row.name,
                passport_no=row.passport_no, id_kind=row.id_kind,
                approved_date=row.approved_date, remark=row.remark,
            )
            session.add(entry)
            entry_rows.append((entry, row))
        session.flush()

        for issue in issues:
            session.add(db.ExtractionIssue(snapshot_id=snapshot.id, **issue))

        watchlist_rows, watchlist = _get_watchlist(session)
        parsed_rows = [row for _entry, row in entry_rows]

        matches = find_matches(watchlist, parsed_rows)
        log.info("[embassy_pdf] Found %d match(es) against %d watchlist entries", len(matches), len(watchlist))

        matches_by_watchlist: dict[int, list] = {}
        for m in matches:
            entry_db_obj = next(e for e, row in entry_rows if row is m.row)
            existing = session.query(db.MatchRecord).filter_by(
                watchlist_id=m.watchlist_id,
                passport_canonical=m.row.passport_no,
            ).first()
            if existing:
                continue  # already notified for this person+ID previously

            session.add(db.MatchRecord(
                watchlist_id=m.watchlist_id, entry_id=entry_db_obj.id, snapshot_id=snapshot.id,
                source="embassy_pdf", passport_canonical=m.row.passport_no, confidence=m.confidence,
                matched_on=m.matched_on, score=m.score,
            ))
            matches_by_watchlist.setdefault(m.watchlist_id, []).append(m)

        session.commit()

        watch_by_id = {w.id: w for w in watchlist_rows}
        for wl_id, wl_matches in matches_by_watchlist.items():
            watch = watch_by_id[wl_id]
            send_message(format_match_alert(watch.full_name, wl_matches), chat_id=watch.telegram_chat_id)
            log.info("[embassy_pdf] Notified for watchlist entry %s (%d new match(es))", watch.full_name, len(wl_matches))

        send_message(format_heartbeat(len(all_rows), len(pages), mode, sum(len(v) for v in matches_by_watchlist.values())))
        send_document(str(pdf_path), caption="Latest passport approval list")

        if issues:
            send_message(format_integrity_warning(issues))


RENEWAL_BACKFILL_DAYS = 30


def run_telegram_renewal_check(session) -> None:
    prev = _latest_snapshot(session, "telegram_renewal")

    if prev is None or prev.mode == "bootstrap":
        # first real run (or a leftover no-op bootstrap row from before this
        # was date-bounded): catch up on recent history rather than only
        # alerting on posts from here forward. Bounded by date, not the
        # channel's entire history, since old appointment dates are no
        # longer relevant and this channel is very active.
        since_date = datetime.now(timezone.utc) - timedelta(days=RENEWAL_BACKFILL_DAYS)
        log.info("[telegram_renewal] First run -- backfilling posts since %s", since_date.date())
        posts = telegram_source.fetch_posts_since(since_date)
    else:
        since_id = int(prev.external_ref or 0)
        posts = telegram_source.fetch_new_posts(since_id)

    if not posts:
        log.info("[telegram_renewal] No new posts found.")
        return

    log.info("[telegram_renewal] %d post(s) to process", len(posts))

    for post in posts:
        all_rows = []
        issues = []
        for i, photo in enumerate(post.photos, start=1):
            text = ocr_image_bytes(photo, psm=4)
            parsed = parse_renewal_page(i, text)

            if parsed.has_gap:
                log.warning("[telegram_renewal] Integrity gap on post %d image %d (rows=%d, markers=%d) -- retrying OCR",
                            post.post_id, i, parsed.row_count, parsed.index_marker_count)
                retry_text = ocr_image_bytes(photo, psm=6)
                retry_parsed = parse_renewal_page(i, retry_text)
                if retry_parsed.row_count > parsed.row_count:
                    parsed = retry_parsed

            if parsed.has_gap:
                detail = f"expected {parsed.index_marker_count} rows, recovered {parsed.row_count}"
                issues.append({"page_no": i, "kind": "row_count_mismatch", "detail": detail})
                log.error("[telegram_renewal] Unresolved integrity gap on post %d image %d: %s", post.post_id, i, detail)

            all_rows.extend(parsed.rows)

        log.info("[telegram_renewal] Post %d: extracted %d rows across %d image(s), %d integrity issue(s)",
                  post.post_id, len(all_rows), len(post.photos), len(issues))

        content_hash = hashlib.sha256(b"".join(post.photos)).hexdigest()
        snapshot = db.Snapshot(
            source="telegram_renewal", external_ref=str(post.post_id), sha256=content_hash,
            page_count=len(post.photos), mode="ocr", row_count=len(all_rows),
        )
        session.add(snapshot)
        session.flush()

        entry_rows = []
        for row in all_rows:
            entry = db.Entry(
                snapshot_id=snapshot.id, page_no=row.page_no, name=row.name,
                passport_no=row.masked_passport, id_kind="masked_passport",
                approved_date=row.appointment_date, remark=f"{row.current_type or '?'} -> {row.new_type or '?'}",
            )
            session.add(entry)
            entry_rows.append((entry, row))
        session.flush()

        for issue in issues:
            session.add(db.ExtractionIssue(snapshot_id=snapshot.id, **issue))

        watchlist_rows, watchlist = _get_watchlist(session)
        parsed_rows = [row for _entry, row in entry_rows]

        matches = find_renewal_matches(watchlist, parsed_rows)
        log.info("[telegram_renewal] Post %d: found %d match(es) against %d watchlist entries",
                  post.post_id, len(matches), len(watchlist))

        matches_by_watchlist: dict[int, list] = {}
        for m in matches:
            entry_db_obj = next(e for e, row in entry_rows if row is m.row)
            existing = session.query(db.MatchRecord).filter_by(
                watchlist_id=m.watchlist_id,
                passport_canonical=m.row.masked_passport,
            ).first()
            if existing:
                continue

            session.add(db.MatchRecord(
                watchlist_id=m.watchlist_id, entry_id=entry_db_obj.id, snapshot_id=snapshot.id,
                source="telegram_renewal", passport_canonical=m.row.masked_passport, confidence=m.confidence,
                matched_on=m.matched_on, score=m.score,
            ))
            matches_by_watchlist.setdefault(m.watchlist_id, []).append(m)

        session.commit()

        watch_by_id = {w.id: w for w in watchlist_rows}
        for wl_id, wl_matches in matches_by_watchlist.items():
            watch = watch_by_id[wl_id]
            send_message(format_renewal_alert(watch.full_name, wl_matches), chat_id=watch.telegram_chat_id)
            log.info("[telegram_renewal] Notified for watchlist entry %s (%d new match(es))", watch.full_name, len(wl_matches))

        send_message(format_renewal_heartbeat(len(all_rows), len(post.photos),
                                               sum(len(v) for v in matches_by_watchlist.values())))

        if issues:
            send_message(format_integrity_warning(issues))


def run() -> int:
    session = db.get_session()
    exit_code = 0

    try:
        run_embassy_pdf_check(session)
    except Exception:
        log.exception("[embassy_pdf] Check failed")
        session.rollback()
        exit_code = 1

    try:
        run_telegram_renewal_check(session)
    except Exception:
        log.exception("[telegram_renewal] Check failed")
        session.rollback()
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(run())
