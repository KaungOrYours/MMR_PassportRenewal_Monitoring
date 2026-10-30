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
from types import SimpleNamespace

from . import db
from .extract import extract_pdf, ocr_image_bytes, reocr_page
from .fetch import fetch
from .match import WatchlistEntry, find_matches, find_renewal_matches
from .notify import (
    format_delivery_failures, format_heartbeat, format_integrity_warning,
    format_match_alert, format_renewal_alert, format_renewal_heartbeat,
    send_document, send_message,
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


def _try_send(text: str, label: str) -> None:
    """Operator-facing messages (heartbeat, integrity warning, failure report)
    must never abort a run: they report on the job, they are not the job."""
    try:
        send_message(text)
    except Exception:
        log.exception("[notify] Could not send %s", label)


def _try_send_document(file_path: str, caption: str = "") -> None:
    try:
        send_document(file_path, caption=caption)
    except Exception:
        log.exception("[notify] Could not send document %s", file_path)


def _record_matches(session, matches, entry_rows, snapshot, source, passport_of) -> int:
    """Writes a MatchRecord for every new match, leaving notified_at NULL.

    Delivery is deliberately NOT done here (see deliver_pending_alerts): the
    record being committed is what makes the dedup check below skip this
    person next time, so sending from inside this loop meant a failed send
    left a committed "match" that was never delivered and never retried.

    Returns the number of matches awaiting delivery, for the heartbeat.
    """
    pending = 0
    for m in matches:
        passport = passport_of(m.row)
        existing = session.query(db.MatchRecord).filter_by(
            watchlist_id=m.watchlist_id,
            passport_canonical=passport,
        ).first()
        if existing is not None:
            # recorded before; only counts as outstanding if the alert for it
            # never actually got through
            if existing.notified_at is None:
                pending += 1
            continue

        entry_db_obj = next(e for e, row in entry_rows if row is m.row)
        session.add(db.MatchRecord(
            watchlist_id=m.watchlist_id, entry_id=entry_db_obj.id, snapshot_id=snapshot.id,
            source=source, passport_canonical=passport, confidence=m.confidence,
            matched_on=m.matched_on, score=m.score,
        ))
        pending += 1
    return pending


def _match_view(record: "db.MatchRecord", entry: "db.Entry"):
    """Rebuilds the minimal shape notify.py's formatters read (``m.row.*``,
    ``m.confidence``, ``m.matched_on``) from the stored rows, so an alert can
    be re-sent on a later run without re-OCRing the original image."""
    current_type = new_type = None
    if entry.remark and "->" in entry.remark:
        left, _, right = entry.remark.partition("->")
        current_type = left.strip() or None
        new_type = right.strip() or None
        current_type = None if current_type == "?" else current_type
        new_type = None if new_type == "?" else new_type

    row = SimpleNamespace(
        name=entry.name,
        page_no=entry.page_no,
        passport_no=entry.passport_no,
        masked_passport=entry.passport_no,
        approved_date=entry.approved_date,
        appointment_date=entry.approved_date,
        current_type=current_type,
        new_type=new_type,
    )
    return SimpleNamespace(row=row, confidence=record.confidence, matched_on=record.matched_on)


def deliver_pending_alerts(session) -> list[str]:
    """Sends an alert for every recorded match not yet successfully delivered,
    stamping notified_at only once Telegram has accepted the message.

    Runs as its own stage, after both checks, for two reasons learned the hard
    way: (1) one undeliverable chat_id ("chat not found" for a stale ID, or a
    user who blocked the bot) used to raise straight out of the check and
    abandon every post after it; (2) because the MatchRecord was already
    committed, the dedup check read it as "already notified," so that person's
    alert was lost permanently rather than retried. Failures are now
    per-recipient, non-fatal, and retried on every subsequent run -- including
    runs where neither source published anything new.
    """
    pending = (
        session.query(db.MatchRecord, db.Entry, db.Watchlist)
        .join(db.Entry, db.MatchRecord.entry_id == db.Entry.id)
        .join(db.Watchlist, db.MatchRecord.watchlist_id == db.Watchlist.id)
        .filter(db.MatchRecord.notified_at.is_(None))
        .filter(db.Watchlist.active.is_(True))
        .order_by(db.MatchRecord.id)
        .all()
    )
    if not pending:
        return []

    grouped: dict[tuple[int, str], list] = {}
    watch_by_id: dict[int, db.Watchlist] = {}
    for record, entry, watch in pending:
        grouped.setdefault((watch.id, record.source or "embassy_pdf"), []).append((record, entry))
        watch_by_id[watch.id] = watch

    log.info("[notify] %d match(es) awaiting delivery across %d recipient(s)",
             len(pending), len(watch_by_id))

    failures: list[str] = []
    for (wl_id, source), items in grouped.items():
        watch = watch_by_id[wl_id]
        views = [_match_view(record, entry) for record, entry in items]
        if source == "telegram_renewal":
            text = format_renewal_alert(watch.full_name, views)
        else:
            text = format_match_alert(watch.full_name, views)

        # an entry with no chat_id of its own (admin-created, predating the
        # Telegram field) falls back to the operator's chat to relay by hand
        # -- see Watchlist.telegram_chat_id. Public signup always sets one.
        if not watch.telegram_chat_id:
            log.warning("[notify] %s has no telegram_chat_id; sending to the operator chat to relay",
                        watch.full_name)

        try:
            send_message(text, chat_id=watch.telegram_chat_id or None)
        except Exception as exc:
            failures.append(f"{watch.full_name}: {exc}")
            log.error("[notify] Alert to %s failed, keeping it pending for the next run: %s",
                      watch.full_name, exc)
            continue

        now = datetime.now(timezone.utc)
        for record, _entry in items:
            record.notified_at = now
        session.commit()
        log.info("[notify] Delivered %d %s match(es) to %s", len(views), source, watch.full_name)

    return failures


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
            # row_count == 0 is only suspicious in OCR mode -- a text-layer
            # PDF page can legitimately have no table rows (e.g. a trailing
            # blank/signature page), and that's not an OCR failure to catch.
            zero_rows_ocr = mode == "ocr" and parsed.row_count == 0 and parsed.index_marker_count == 0
            if (parsed.has_gap or zero_rows_ocr) and mode == "ocr":
                log.warning("[embassy_pdf] Integrity gap on page %d (rows=%d, markers=%d) -- retrying OCR",
                            page.page_no, parsed.row_count, parsed.index_marker_count)
                retry_text = reocr_page(pdf_path, page.page_no)
                retry_parsed = parse_page(page.page_no, retry_text)
                if retry_parsed.row_count > parsed.row_count:
                    parsed = retry_parsed
                zero_rows_ocr = mode == "ocr" and parsed.row_count == 0 and parsed.index_marker_count == 0

            if parsed.has_gap or zero_rows_ocr:
                if zero_rows_ocr:
                    kind = "zero_rows_extracted"
                    detail = "0 rows and 0 index markers detected -- likely total OCR failure, not an empty page"
                else:
                    kind = "row_count_mismatch"
                    detail = f"expected {parsed.index_marker_count} rows, recovered {parsed.row_count}"
                issues.append({"page_no": page.page_no, "kind": kind, "detail": detail})
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

        _watchlist_rows, watchlist = _get_watchlist(session)
        parsed_rows = [row for _entry, row in entry_rows]

        matches = find_matches(watchlist, parsed_rows)
        log.info("[embassy_pdf] Found %d match(es) against %d watchlist entries", len(matches), len(watchlist))

        pending_count = _record_matches(
            session, matches, entry_rows, snapshot, "embassy_pdf", lambda row: row.passport_no,
        )
        session.commit()

        _try_send(format_heartbeat(len(all_rows), len(pages), mode, pending_count), label="heartbeat")
        _try_send_document(str(pdf_path), caption="Latest passport approval list")

        if issues:
            _try_send(format_integrity_warning(issues), label="integrity warning")


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
                log.warning("[telegram_renewal] Integrity gap on post %d image %d (rows=%d, markers=%d, "
                            "missing row numbers=%s) -- retrying OCR",
                            post.post_id, i, parsed.row_count, parsed.index_marker_count,
                            parsed.missing_indexes or "none")
                # NOT --psm 6: measured against real @mesg15 photos it returns
                # near-empty output (~120 chars vs ~920 at psm 4) and recovered
                # zero rows every time, so it could only ever make things worse.
                # 11 (sparse text) and 3 (full auto) both recover these tables.
                for retry_psm in (11, 3):
                    retry_parsed = parse_renewal_page(i, ocr_image_bytes(photo, psm=retry_psm))
                    if retry_parsed.row_count > parsed.row_count:
                        parsed = retry_parsed
                    if not parsed.has_gap:
                        break

            if parsed.has_gap:
                if parsed.row_count == 0 and parsed.index_marker_count == 0:
                    kind = "zero_rows_extracted"
                    detail = "0 rows and 0 index markers detected -- likely total OCR failure, not an empty page"
                elif parsed.missing_indexes:
                    kind = "missing_row_numbers"
                    detail = (f"row number(s) {parsed.missing_indexes} absent from the sequence "
                              f"{parsed.index_numbers[0]}-{parsed.index_numbers[-1]} on this image")
                else:
                    kind = "row_count_mismatch"
                    detail = f"expected {parsed.index_marker_count} rows, recovered {parsed.row_count}"
                issues.append({"page_no": i, "kind": kind, "detail": detail})
                log.error("[telegram_renewal] Unresolved integrity gap on post %d image %d: %s", post.post_id, i, detail)

            all_rows.extend(parsed.rows)

        # A post's images continue one numbered list (1..N across all of them),
        # so a hole in the sequence spanning an image boundary is a lost row
        # that no single image's own check could see.
        post_indexes = sorted({r.index_no for r in all_rows if r.index_no is not None})
        if len(post_indexes) >= 2:
            present = set(post_indexes)
            missing = [n for n in range(post_indexes[0], post_indexes[-1] + 1) if n not in present]

            # The first image of a @mesg15 post is a notice/cover page, not a
            # table -- it legitimately yields 0 rows, and flagging that on
            # every single post is how a genuine warning ends up ignored. If
            # the post's rows number 1..N with no holes then nothing was lost,
            # whatever any individual image's own row count looked like, so the
            # zero-row flag on the cover is provably a false alarm here. Note
            # this only ever *removes* a warning when the numbering proves the
            # data is complete -- it can never hide a real shortfall.
            if not missing and post_indexes[0] == 1:
                cover = [iss for iss in issues if iss["kind"] == "zero_rows_extracted"]
                if cover:
                    issues = [iss for iss in issues if iss["kind"] != "zero_rows_extracted"]
                    log.info("[telegram_renewal] Post %d: image(s) %s have no rows, but the post's row "
                             "numbering is complete (1-%d) -- treating them as notice/cover pages",
                             post.post_id, [iss["page_no"] for iss in cover], post_indexes[-1])

            if missing:
                issues.append({
                    "page_no": 0,  # 0 == whole post, not one image
                    "kind": "missing_row_numbers",
                    "detail": (f"row number(s) {missing} absent from the post's sequence "
                               f"{post_indexes[0]}-{post_indexes[-1]}"),
                })
                log.error("[telegram_renewal] Post %d: row number(s) %s missing from the sequence %d-%d",
                          post.post_id, missing, post_indexes[0], post_indexes[-1])

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

        _watchlist_rows, watchlist = _get_watchlist(session)
        parsed_rows = [row for _entry, row in entry_rows]

        matches = find_renewal_matches(watchlist, parsed_rows)
        log.info("[telegram_renewal] Post %d: found %d match(es) against %d watchlist entries",
                  post.post_id, len(matches), len(watchlist))

        pending_count = _record_matches(
            session, matches, entry_rows, snapshot, "telegram_renewal", lambda row: row.masked_passport,
        )
        session.commit()

        _try_send(format_renewal_heartbeat(len(all_rows), len(post.photos), pending_count),
                  label="renewal heartbeat")

        if issues:
            _try_send(format_integrity_warning(issues), label="integrity warning")


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

    # Deliberately outside both checks, and run even when neither published
    # anything new, so an alert that failed to send on an earlier run still
    # gets retried instead of sitting in the DB marked as matched forever.
    try:
        failures = deliver_pending_alerts(session)
        if failures:
            exit_code = 1
            _try_send(format_delivery_failures(failures), label="delivery failure report")
    except Exception:
        log.exception("[notify] Pending-alert delivery failed")
        session.rollback()
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(run())
