"""Full identifiers from the embassy PDF must not be stored, in any column.

All numbers and names here are made up. Lines go through the real parser, because
the parser decides which column a second identifier lands in.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from checker import db, main, mask_stored_passports, notify
from checker.masking import mask_identifier, scrub_identifiers
from checker.parse import parse_page

FULL = "MK650912"
MASKED = "MK6***12"
NAME = "THIHA ZAW MYINT"
LINE = f"1. {NAME} {FULL} 28-10-2026"
SECOND_FULL = "YY222222"
SHORT_CODE = "ZZZ3333"
NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


@pytest.fixture
def session():
    s = db.get_session("sqlite:///:memory:")
    yield s
    s.close()


@pytest.mark.parametrize("value, expected", [
    (FULL, MASKED),
    ("mk 650912", MASKED),
    ("SIRB-10245", "SI***45"),
    ("AB-12", "***"),
    ("CDC3363", "***"),
    ("M835131", "M8***31"),
    ("MF40**22", "MF40**22"),
    (MASKED, MASKED),
])
def test_mask_identifier(value, expected):
    assert mask_identifier(value) == expected


@pytest.mark.parametrize("value, most_visible", [
    ("A1B2C3D4E5", 4), ("12345678", 4), ("X-1", 0), ("PASSPORT-NUMBER", 4), ("SIRB-10245", 4), ("MK650912", 5),
])
def test_identifiers_lose_most_of_their_characters(value, most_visible):
    assert len(mask_identifier(value).replace("*", "")) <= most_visible


@pytest.mark.parametrize("text, expected", [
    (f"new {SECOND_FULL}", "new YY2***22"),
    (f"AUNG KO {SHORT_CODE}", "AUNG KO ***"),
    ("AUNG KO SIRB-10245", "AUNG KO SI***45"),
    ("MOE NYUNT 00", "MOE NYUNT 00"),
    (f"new {MASKED}", f"new {MASKED}"),
    ("", ""),
    (None, None),
])
def test_scrub_identifiers(text, expected):
    assert scrub_identifiers(text) == expected


def _run_pdf_check(session, monkeypatch, *lines, sha="sha-1"):
    monkeypatch.setattr(main, "fetch", lambda **_: SimpleNamespace(
        changed=True, sha256=sha, etag=None, last_modified=None, content=b"pdf",
    ))
    monkeypatch.setattr(main, "extract_pdf", lambda _path: (
        [SimpleNamespace(page_no=1, text="\n".join(lines or [LINE]))], "text",
    ))
    monkeypatch.setattr(main, "_try_send", lambda *_, **__: None)
    monkeypatch.setattr(main, "_try_send_document", lambda *_, **__: None)
    main.run_embassy_pdf_check(session)


def _watch(session, passport=FULL, name=NAME):
    watch = db.Watchlist(full_name=name, passport_no=passport, telegram_chat_id="880011223", active=True)
    session.add(watch)
    session.commit()
    return watch


def _every_stored_value(session):
    for model in (db.Entry, db.MatchRecord):
        for row in session.query(model):
            for column in model.__table__.columns:
                value = getattr(row, column.name)
                if isinstance(value, str):
                    yield value


def _assert_nothing_full_stored(session, *full_values):
    stored = list(_every_stored_value(session))
    for full in full_values:
        assert not [value for value in stored if full in value]


@pytest.mark.parametrize("line, full_values", [
    (LINE, [FULL]),
    (f"1. {NAME} {FULL} 28-10-2026 new {SECOND_FULL}", [FULL, SECOND_FULL]),
    (f"1. {NAME} {FULL} {SECOND_FULL}", [FULL, SECOND_FULL]),
    (f"1. {NAME} {SHORT_CODE} {FULL} 28-10-2026", [FULL, SHORT_CODE]),
    (f"1. {NAME} SIRB-10245 {FULL} 28-10-2026", [FULL, "SIRB-10245"]),
    (f"1. {NAME} SIRB-10245/24-12-2014 28-10-2026", ["SIRB-10245", "24-12-2014"]),
])
def test_no_column_keeps_a_full_identifier(session, monkeypatch, line, full_values):
    _watch(session)
    _run_pdf_check(session, monkeypatch, line)
    assert session.query(db.Entry).count() == 1
    _assert_nothing_full_stored(session, *full_values)


def test_a_seaman_books_issue_date_is_not_taken_as_the_approval_date():
    row = parse_page(1, "1. AUNG KO SIRB-10245/24-12-2014 28-10-2026 note").rows[0]
    assert row.passport_no == "SIRB-10245"
    assert row.approved_date == "28-10-2026"
    assert row.remark == "note"


def test_the_full_number_matches_and_only_the_mask_is_stored(session, monkeypatch):
    watch = _watch(session)
    _run_pdf_check(session, monkeypatch)
    assert session.query(db.Entry).one().passport_no == MASKED
    match = session.query(db.MatchRecord).one()
    assert (match.passport_canonical, match.watchlist_id) == (MASKED, watch.id)


def test_a_passport_with_the_same_mask_does_not_match(session, monkeypatch):
    _watch(session, passport="MK600012")
    _run_pdf_check(session, monkeypatch)
    assert session.query(db.MatchRecord).count() == 0


def test_the_same_passport_on_a_later_list_is_not_recorded_twice(session, monkeypatch):
    _watch(session)
    _run_pdf_check(session, monkeypatch, sha="sha-1")
    _run_pdf_check(session, monkeypatch, sha="sha-2")
    assert session.query(db.Entry).count() == 2
    assert session.query(db.MatchRecord).count() == 1


def test_the_delivered_alert_shows_only_the_masked_number(session, monkeypatch):
    _watch(session)
    _run_pdf_check(session, monkeypatch)

    sent = []
    monkeypatch.setattr(main, "send_message", lambda text, chat_id=None: sent.append(text))
    assert main.deliver_pending_alerts(session) == []

    assert len(sent) == 1
    assert MASKED in sent[0]
    assert FULL not in sent[0]
    assert session.query(db.MatchRecord).one().notified_at is not None


def _old_rows(session, notified_at=None):
    """Rows as the previous code stored them, with full numbers."""
    watch = _watch(session)
    snapshot = db.Snapshot(source="embassy_pdf", sha256="old", page_count=1, mode="text", row_count=2)
    session.add(snapshot)
    session.flush()
    full = db.Entry(snapshot_id=snapshot.id, page_no=1, name=f"{NAME} {SHORT_CODE}", passport_no=FULL,
                    id_kind="passport", remark=f"new {SECOND_FULL}")
    renewal = db.Entry(snapshot_id=snapshot.id, page_no=1, name="AYE AYE", passport_no="MF40**22",
                       id_kind="masked_passport")
    session.add_all([full, renewal])
    session.flush()
    session.add(db.MatchRecord(
        watchlist_id=watch.id, entry_id=full.id, snapshot_id=snapshot.id, passport_canonical=FULL,
        confidence="high", matched_on="passport", score=100, notified_at=notified_at,
    ))
    session.commit()
    return watch, snapshot, full, renewal


def test_an_old_record_stops_a_second_alert_before_the_cleanup(session, monkeypatch):
    _old_rows(session, notified_at=NOW)
    _run_pdf_check(session, monkeypatch, sha="new")
    match = session.query(db.MatchRecord).one()
    assert match.notified_at is not None


@pytest.fixture
def cleanup(session, monkeypatch):
    monkeypatch.setattr(mask_stored_passports.db, "get_session", lambda *_: session)
    return mask_stored_passports


def test_cleanup_changes_nothing_without_apply(session, cleanup, capsys):
    _, _, full, _ = _old_rows(session)
    assert cleanup.main([]) == 0
    session.expire_all()
    assert full.passport_no == FULL
    assert full.remark == f"new {SECOND_FULL}"
    assert session.query(db.MatchRecord).one().passport_canonical == FULL
    assert FULL not in capsys.readouterr().out


def test_cleanup_masks_every_column_and_a_second_run_plans_nothing(session, cleanup, capsys):
    _, _, full, renewal = _old_rows(session)
    assert cleanup.main(["--apply"]) == 0
    assert FULL not in capsys.readouterr().out

    session.expire_all()
    assert (full.passport_no, full.name, full.remark) == (MASKED, f"{NAME} ***", "new YY2***22")
    assert renewal.passport_no == "MF40**22"
    assert session.query(db.MatchRecord).one().passport_canonical == MASKED
    _assert_nothing_full_stored(session, FULL, SECOND_FULL, SHORT_CODE)

    p = cleanup.plan(session)
    assert (p.entries, p.matches, p.merged_away, p.delivered_from_merge) == ([], [], [], [])


@pytest.mark.parametrize("old_notified, new_notified, expect_delivered", [
    (NOW, None, True), (None, NOW, True), (None, None, False), (NOW, NOW, True),
])
def test_cleanup_merges_matches_that_become_identical(session, cleanup, old_notified, new_notified, expect_delivered):
    watch, snapshot, full, _ = _old_rows(session, notified_at=old_notified)
    session.add(db.MatchRecord(
        watchlist_id=watch.id, entry_id=full.id, snapshot_id=snapshot.id, passport_canonical=MASKED,
        confidence="high", matched_on="passport", score=100, notified_at=new_notified,
    ))
    session.commit()

    assert cleanup.main(["--apply"]) == 0
    match = session.query(db.MatchRecord).one()
    assert match.passport_canonical == MASKED
    assert (match.notified_at is not None) is expect_delivered


def test_a_failed_cleanup_changes_nothing(session, cleanup, monkeypatch):
    _, _, full, _ = _old_rows(session)
    p = cleanup.plan(session)

    def fail():
        raise RuntimeError("commit failed")
    monkeypatch.setattr(session, "commit", fail)
    with pytest.raises(RuntimeError):
        cleanup.apply_plan(session, p)
    session.rollback()
    session.expire_all()
    assert full.passport_no == FULL
    assert session.query(db.MatchRecord).one().passport_canonical == FULL


def test_alert_formatter_shows_a_masked_row():
    match = SimpleNamespace(
        row=SimpleNamespace(name=NAME, passport_no=MASKED, approved_date="28-10-2026", page_no=1),
        confidence="high", matched_on="passport",
    )
    assert MASKED in notify.format_match_alert(NAME, [match])
