"""Tests for alert delivery being a separate, retrying stage.

The failure this guards against was seen in production: a single
undeliverable chat_id ("Bad Request: chat not found") raised out of the
whole renewal check, so every post after it went unprocessed -- and because
the MatchRecord had already been committed, the dedup check treated that
person as "already notified" and the alert was never retried. They were on
the list, the system knew it, and they were never told.
"""
from datetime import datetime, timezone

import pytest

from checker import db, main
from checker.match import RenewalMatch
from checker.parse_renewal import RenewalRow


@pytest.fixture
def session():
    s = db.get_session("sqlite:///:memory:")
    yield s
    s.close()


def _seed(session, *, snapshot_ref="200"):
    snapshot = db.Snapshot(
        source="telegram_renewal", external_ref=snapshot_ref, sha256=f"hash-{snapshot_ref}",
        page_count=1, mode="ocr", row_count=2,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _add_person(session, snapshot, name, passport, masked, chat_id):
    watch = db.Watchlist(full_name=name, passport_no=passport, telegram_chat_id=chat_id, active=True)
    session.add(watch)
    entry = db.Entry(
        snapshot_id=snapshot.id, page_no=1, name=name, passport_no=masked,
        id_kind="masked_passport", approved_date="28-10-2026", remark="PV -> PJ",
    )
    session.add(entry)
    session.flush()
    record = db.MatchRecord(
        watchlist_id=watch.id, entry_id=entry.id, snapshot_id=snapshot.id,
        source="telegram_renewal", passport_canonical=masked,
        confidence="high", matched_on="name+passport", score=100,
    )
    session.add(record)
    session.flush()
    return watch, entry, record


def test_one_undeliverable_chat_does_not_block_the_others(session, monkeypatch):
    snapshot = _seed(session)
    _good, _, good_record = _add_person(
        session, snapshot, "NYAN LIN HTET", "MG771148", "MG77**48", "111111111")
    _bad, _, bad_record = _add_person(
        session, snapshot, "ZIN KYU HNIN", "MF591144", "MF59**44", "999999999")
    session.commit()

    sent = []

    def fake_send(text, chat_id=None, parse_mode="HTML"):
        if chat_id == "999999999":
            raise RuntimeError("Telegram API error (400): Bad Request: chat not found")
        sent.append(chat_id)
        return {"ok": True}

    monkeypatch.setattr(main, "send_message", fake_send)

    failures = main.deliver_pending_alerts(session)

    assert sent == ["111111111"]                 # the reachable person still got theirs
    assert len(failures) == 1
    assert "ZIN KYU HNIN" in failures[0]
    assert "chat not found" in failures[0]

    assert good_record.notified_at is not None   # delivered -> stamped, won't re-send
    assert bad_record.notified_at is None        # undelivered -> still pending


def test_a_failed_alert_is_retried_on_a_later_run(session, monkeypatch):
    snapshot = _seed(session)
    _watch, _entry, record = _add_person(
        session, snapshot, "ZIN KYU HNIN", "MF591144", "MF59**44", "999999999")
    session.commit()

    monkeypatch.setattr(main, "send_message", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("Telegram API error (400): Bad Request: chat not found")))
    assert len(main.deliver_pending_alerts(session)) == 1
    assert record.notified_at is None

    # operator corrects the stored Telegram ID; the next run delivers it
    sent = []
    monkeypatch.setattr(main, "send_message",
                        lambda text, chat_id=None, parse_mode="HTML": sent.append((chat_id, text)))

    failures = main.deliver_pending_alerts(session)

    assert failures == []
    assert len(sent) == 1
    assert "ZIN KYU HNIN" in sent[0][1]
    assert "MF59**44" in sent[0][1]           # rebuilt from the stored row, no re-OCR
    assert "28-10-2026" in sent[0][1]
    assert record.notified_at is not None

    # and it is not sent a third time
    assert main.deliver_pending_alerts(session) == []
    assert len(sent) == 1


def test_entry_without_its_own_chat_id_falls_back_to_the_operator(session, monkeypatch):
    """Watchlist.telegram_chat_id documents this fallback: an admin-created
    entry predating the Telegram field is relayed via the operator's chat
    rather than dropped."""
    snapshot = _seed(session)
    _watch, _entry, record = _add_person(
        session, snapshot, "AYE THET WIN", "MG281173", "MG28**73", None)
    session.commit()

    sent = []
    monkeypatch.setattr(main, "send_message",
                        lambda text, chat_id=None, parse_mode="HTML": sent.append(chat_id))

    failures = main.deliver_pending_alerts(session)

    assert failures == []
    assert sent == [None]              # None -> notify.send_message uses TELEGRAM_CHAT_ID
    assert record.notified_at is not None


def test_recorded_but_undelivered_match_counts_as_still_pending(session):
    """_record_matches must not treat an existing MatchRecord as settled when
    its alert never went out -- that was the bug that lost the alert for good."""
    snapshot = _seed(session)
    watch, _entry, record = _add_person(
        session, snapshot, "NYAN LIN HTET", "MG771148", "MG77**48", "111111111")
    session.commit()

    row = RenewalRow(
        page_no=1, index_no=1, name="NYAN LIN HTET", masked_passport="MG77**48",
        current_type="PV", new_type="PJ", appointment_date="28-10-2026", raw_line="",
    )
    match = RenewalMatch(watchlist_id=watch.id, row=row, confidence="high",
                         matched_on="name+passport", score=100)

    pending = main._record_matches(
        session, [match], [], snapshot, "telegram_renewal", lambda r: r.masked_passport)
    assert pending == 1                                           # still owed an alert
    assert session.query(db.MatchRecord).count() == 1             # but no duplicate row

    record.notified_at = datetime.now(timezone.utc)
    session.commit()

    pending = main._record_matches(
        session, [match], [], snapshot, "telegram_renewal", lambda r: r.masked_passport)
    assert pending == 0                                           # already delivered
    assert session.query(db.MatchRecord).count() == 1


def test_shape_redaction_leaks_no_letters_or_digits():
    """diagnose.py prints line shapes into a PUBLIC repo's Actions log, so the
    redaction has to be total -- structure only, no content."""
    from checker.diagnose import _shape

    shaped = _shape("61   NYAN LIN HTET          MG 77**48      PV        PJ")
    assert shaped == "99   AAAA AAA AAAA          AA 99**99      AA        AA"
    assert not any(c.isalnum() and c not in "A9" for c in shaped)


def test_classify_names_the_three_distinct_zero_row_causes():
    from checker.diagnose import _classify

    long_table_text = "x" * 200
    assert _classify(long_table_text, rows=5, markers=5, passport_lines=5) == "ok"
    assert "image unreadable" in _classify("", 0, 0, 0)
    assert "PARSER BUG" in _classify(long_table_text, 0, 5, 5)
    assert "NO PASSPORT PATTERN" in _classify(long_table_text, 0, 1, 0)
    assert "NO TABLE STRUCTURE" in _classify(long_table_text, 0, 0, 0)
