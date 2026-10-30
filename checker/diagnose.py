"""Read-only diagnostics for "my name is on the list but I was never told".

Three questions this answers, which the scheduled run cannot:

1. ``inspect``       -- did OCR actually read a given post's images, and does
                        the parser see rows in them? Re-fetches a specific
                        post by message id, so it works on posts the run's
                        watermark has already passed.
2. ``verify-chats``  -- can the bot actually message each watchlist entry?
                        A stored Telegram ID can be correctly formatted
                        (5-15 digits, see backend/schemas.py) and still be
                        undeliverable, which surfaces only as "Bad Request:
                        chat not found" at send time.
3. ``pending``       -- which recorded matches have never been delivered
                        (MatchRecord.notified_at IS NULL).

Nothing here writes to the database or moves a watermark.

PII handling: this is run from a public repo's GitHub Actions, whose logs and
workflow inputs are world-readable. So stdout gets counts, structure and
redacted line *shapes* only -- every name, passport fragment and chat ID goes
to the operator's own Telegram chat instead. Pass a watchlist id rather than a
name for the same reason.

Usage:
    python -m checker.diagnose inspect --post 228
    python -m checker.diagnose inspect --recent 2 --watchlist-id 42
    python -m checker.diagnose verify-chats
    python -m checker.diagnose pending
"""
import argparse
import logging
import re
import sys

from . import db, telegram_source
from .extract import ocr_image_bytes
from .match import WatchlistEntry, match_renewal_row, names_plausibly_match
from .notify import get_chat, send_message
from .parse_renewal import MASKED_PASSPORT_RE, normalize_text, parse_renewal_page

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("diagnose")

MAX_TELEGRAM_CHARS = 3500


def _shape(line: str) -> str:
    """Structure of a line with its content removed: letters -> A, digits -> 9.

    Safe to print publicly, and enough to tell a table row ("99 AAAA AAAA
    AA 99**99 AA AA") from a notice/cover image at a glance."""
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", line))


def _report_to_operator(title: str, lines: list[str]) -> None:
    """Sends PII-bearing detail to the operator's own chat rather than stdout."""
    if not lines:
        return
    body = "\n".join(lines)
    if len(body) > MAX_TELEGRAM_CHARS:
        body = body[:MAX_TELEGRAM_CHARS] + "\n[...truncated]"
    try:
        send_message(f"🔎 <b>{title}</b>\n\n<pre>{body}</pre>")
        print(f"   (detail sent to the operator Telegram chat: {len(lines)} line(s))")
    except Exception as exc:
        log.error("Could not send the detail report to Telegram: %s", exc)


def _classify(text: str, rows: int, markers: int, passport_lines: int) -> str:
    """Why did this image yield no rows? The three causes need different fixes."""
    if rows:
        return "ok"
    if len(text.strip()) < 40:
        return "OCR RETURNED ALMOST NOTHING -- image unreadable at this psm (bad crop/rotation/resolution?)"
    if passport_lines:
        return (f"PARSER BUG -- OCR read {passport_lines} line(s) containing a masked-passport "
                "pattern, but _extract_row() rejected every one (name missing on the line?)")
    if markers:
        return ("NO PASSPORT PATTERN -- OCR read text and found an index marker but no 'AA 99**99' "
                "anywhere. Either a cover/notice image (not a table), or the mask format changed")
    return ("NO TABLE STRUCTURE -- OCR read text but found neither an index marker nor a passport "
            "pattern. Most likely a cover/notice image, i.e. the integrity 'gap' is a false alarm")


def _inspect_image(post_id: int, idx: int, photo: bytes, watch: WatchlistEntry | None) -> list[str]:
    detail: list[str] = []
    print(f"\n  image {idx}:")

    best = None
    for psm in (4, 6):
        text = ocr_image_bytes(photo, psm=psm)
        norm = normalize_text(text)
        parsed = parse_renewal_page(idx, text)
        passport_lines = sum(1 for ln in norm.splitlines() if MASKED_PASSPORT_RE.search(ln))
        print(f"    psm {psm}: {len(text):5d} chars, {len(norm.splitlines()):3d} lines, "
              f"rows={parsed.row_count:3d}, markers={parsed.index_marker_count:3d}, "
              f"passport-pattern lines={passport_lines}")
        print(f"            -> {_classify(text, parsed.row_count, parsed.index_marker_count, passport_lines)}")
        if best is None or parsed.row_count > best[1].row_count:
            best = (norm, parsed)

    norm, parsed = best
    if parsed.row_count == 0:
        print("    redacted line shapes (letters->A, digits->9):")
        for ln in [l for l in norm.splitlines() if l.strip()][:12]:
            print(f"      | {_shape(ln)[:90]}")

    if watch is not None:
        found = []
        for ln in norm.splitlines():
            ok, score = names_plausibly_match(watch.full_name, ln)
            if ok or (watch.passport_no and watch.passport_no[:2].upper() in ln.upper()
                      and MASKED_PASSPORT_RE.search(ln)):
                found.append(f"post {post_id} img {idx}: {ln.strip()}")
        parsed_hit = [r for r in parsed.rows if match_renewal_row(watch, r) is not None]
        print(f"    watchlist id {watch.id}: {len(found)} raw OCR line(s) look relevant, "
              f"{len(parsed_hit)} parsed row(s) actually match")
        detail += found
        detail += [f"post {post_id} img {idx} PARSED MATCH: {r.name} / {r.masked_passport} / {r.appointment_date}"
                   for r in parsed_hit]
    return detail


def cmd_inspect(args) -> int:
    watch = None
    if args.watchlist_id:
        session = db.get_session()
        row = session.query(db.Watchlist).filter_by(id=args.watchlist_id).first()
        if row is None:
            print(f"No watchlist entry with id {args.watchlist_id}")
            return 1
        watch = WatchlistEntry(id=row.id, full_name=row.full_name, passport_no=row.passport_no)
        print(f"Searching for watchlist id {row.id} (name/passport withheld from this log)")

    if args.post:
        posts = []
        for post_id in args.post:
            group = telegram_source.fetch_post_group(post_id)
            if not group:
                print(f"Post {post_id} not found (deleted, or not a photo post)")
            posts.extend(group)
    else:
        posts = telegram_source.fetch_recent_posts(args.recent)

    if not posts:
        print("Nothing to inspect.")
        return 1

    detail: list[str] = []
    for post in posts:
        print(f"\n=== post {post.post_id} ({post.date}) -- {len(post.photos)} image(s), "
              f"message ids {post.message_ids} ===")
        for idx, photo in enumerate(post.photos, start=1):
            detail += _inspect_image(post.post_id, idx, photo, watch)

    if watch is not None:
        if detail:
            _report_to_operator(f"Inspect: watchlist id {watch.id}", detail)
        else:
            print(f"\nwatchlist id {watch.id} was NOT found in any inspected image's OCR text.")
    return 0


def cmd_verify_chats(args) -> int:
    session = db.get_session()
    rows = session.query(db.Watchlist).filter_by(active=True).all()
    no_id, reachable, unreachable = 0, 0, []

    for row in rows:
        if not row.telegram_chat_id:
            no_id += 1
            continue
        try:
            get_chat(row.telegram_chat_id)
            reachable += 1
        except Exception as exc:
            unreachable.append(f"id {row.id}  {row.full_name}  chat_id={row.telegram_chat_id}  -> {exc}")

    print(f"{len(rows)} active entries: {reachable} reachable, {len(unreachable)} UNREACHABLE, "
          f"{no_id} with no Telegram ID (these fall back to the operator chat)")
    if unreachable:
        print("Unreachable entries will never receive an alert until their ID is corrected in /admin.")
        _report_to_operator("Unreachable Telegram IDs", unreachable)
    return 1 if unreachable else 0


def cmd_pending(args) -> int:
    session = db.get_session()
    pending = (
        session.query(db.MatchRecord, db.Entry, db.Watchlist)
        .join(db.Entry, db.MatchRecord.entry_id == db.Entry.id)
        .join(db.Watchlist, db.MatchRecord.watchlist_id == db.Watchlist.id)
        .filter(db.MatchRecord.notified_at.is_(None))
        .order_by(db.MatchRecord.id)
        .all()
    )
    print(f"{len(pending)} recorded match(es) have never been delivered.")
    if pending:
        print("The next scheduled run retries all of them (see main.deliver_pending_alerts).")
        _report_to_operator("Undelivered matches", [
            f"match {r.id}  wl {w.id} {w.full_name}  {e.passport_no}  {r.source}  "
            f"chat_id={w.telegram_chat_id or '(none)'}  active={w.active}"
            for r, e, w in pending
        ])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="re-OCR a post's images and report what the parser sees")
    p_inspect.add_argument("--post", type=int, action="append",
                           help="Telegram message id of a post (repeatable)")
    p_inspect.add_argument("--recent", type=int, default=1,
                           help="inspect the N most recent photo posts instead")
    p_inspect.add_argument("--watchlist-id", type=int,
                           help="also search for this watchlist entry (by id, so no name is logged)")
    p_inspect.set_defaults(func=cmd_inspect)

    p_chats = sub.add_parser("verify-chats", help="check every watchlist Telegram ID is actually reachable")
    p_chats.set_defaults(func=cmd_verify_chats)

    p_pending = sub.add_parser("pending", help="list matches recorded but never delivered")
    p_pending.set_defaults(func=cmd_pending)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
