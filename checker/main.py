"""Entry point: one run of fetch -> extract -> parse -> match -> notify.

Invoked on a schedule by .github/workflows/check.yml. Exits quietly (no DB
writes, no notifications) when the PDF has not changed since the last run.
"""
import logging
import sys
import tempfile
from pathlib import Path

from . import db
from .extract import extract_pdf, reocr_page
from .fetch import fetch
from .match import WatchlistEntry, find_matches
from .notify import format_heartbeat, format_integrity_warning, format_match_alert, send_document, send_message
from .parse import parse_page

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("checker")


def _latest_snapshot(session) -> db.Snapshot | None:
    return session.query(db.Snapshot).order_by(db.Snapshot.fetched_at.desc()).first()


def run() -> int:
    session = db.get_session()
    prev = _latest_snapshot(session)

    result = fetch(
        prev_etag=prev.etag if prev else None,
        prev_last_modified=prev.last_modified if prev else None,
        prev_sha256=prev.sha256 if prev else None,
    )

    if not result.changed:
        log.info("No change in the approval list since the last check.")
        return 0

    log.info("New PDF content detected (sha256=%s). Processing...", result.sha256[:12])

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "approval.pdf"
        pdf_path.write_bytes(result.content)

        pages, mode = extract_pdf(pdf_path)

        all_rows = []
        issues = []
        for page in pages:
            parsed = parse_page(page.page_no, page.text)
            if parsed.has_gap and mode == "ocr":
                log.warning("Integrity gap on page %d (rows=%d, markers=%d) -- retrying OCR",
                            page.page_no, parsed.row_count, parsed.index_marker_count)
                retry_text = reocr_page(pdf_path, page.page_no)
                retry_parsed = parse_page(page.page_no, retry_text)
                if retry_parsed.row_count > parsed.row_count:
                    parsed = retry_parsed

            if parsed.has_gap:
                detail = f"expected {parsed.index_marker_count} rows, recovered {parsed.row_count}"
                issues.append({"page_no": page.page_no, "kind": "row_count_mismatch", "detail": detail})
                log.error("Unresolved integrity gap on page %d: %s", page.page_no, detail)

            all_rows.extend(parsed.rows)

        log.info("Extracted %d rows across %d pages (mode=%s, %d integrity issue(s))",
                  len(all_rows), len(pages), mode, len(issues))

        snapshot = db.Snapshot(
            etag=result.etag, last_modified=result.last_modified, sha256=result.sha256,
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

        watchlist_rows = session.query(db.Watchlist).filter_by(active=True).all()
        watchlist = [WatchlistEntry(id=w.id, full_name=w.full_name, passport_no=w.passport_no) for w in watchlist_rows]
        by_entry_id = {id(row): entry for entry, row in entry_rows}
        parsed_rows = [row for _entry, row in entry_rows]

        matches = find_matches(watchlist, parsed_rows)
        log.info("Found %d match(es) against %d watchlist entries", len(matches), len(watchlist))

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
                passport_canonical=m.row.passport_no, confidence=m.confidence,
                matched_on=m.matched_on, score=m.score,
            ))
            matches_by_watchlist.setdefault(m.watchlist_id, []).append(m)

        session.commit()

        watch_by_id = {w.id: w for w in watchlist_rows}
        for wl_id, wl_matches in matches_by_watchlist.items():
            watch_name = watch_by_id[wl_id].full_name
            send_message(format_match_alert(watch_name, wl_matches))
            log.info("Notified for watchlist entry %s (%d new match(es))", watch_name, len(wl_matches))

        send_message(format_heartbeat(len(all_rows), len(pages), mode, sum(len(v) for v in matches_by_watchlist.values())))
        send_document(str(pdf_path), caption="Latest passport approval list")

        if issues:
            send_message(format_integrity_warning(issues))

    return 0


if __name__ == "__main__":
    sys.exit(run())
