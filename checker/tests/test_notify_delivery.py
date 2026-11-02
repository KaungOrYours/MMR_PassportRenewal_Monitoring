"""Tests for alert delivery being a separate, retrying stage.

The failure this guards against was seen in production: a single
undeliverable chat_id ("Bad Request: chat not found") raised out of the
whole renewal check, so every post after it went unprocessed -- and because
the MatchRecord had already been committed, the dedup check treated that
person as "already notified" and the alert was never retried. They were on
the list, the system knew it, and they were never told.
"""
import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg2.errors
import pytest
import requests
from sqlalchemy.exc import IntegrityError
from telethon.extensions import BinaryReader
from telethon.tl.functions import InvokeWithoutUpdatesRequest
from telethon.tl.functions.channels import GetMessagesRequest as GetChannelMessagesRequest
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import InputPeerChannel

from checker import crash_report, db, main, notify
from checker.crash_report import database_metadata, describe_exception
from checker.match import RenewalMatch
from checker.notify import TelegramAPIError, safe_error_text
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
            raise TelegramAPIError("Telegram API error (400): Bad Request: chat not found")
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
        TelegramAPIError("Telegram API error (400): Bad Request: chat not found")))
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


# --- Nothing personal, and no bot token, in the public Actions log ---------

FAKE_NAME = "THIHA ZAW MYINT"
FAKE_PASSPORT = "MK650912"
FAKE_MASKED = "MK65**12"
FAKE_CHAT_ID = "880011223"
FAKE_TOKEN = "123456:FAKE-token-for-tests"


def _assert_log_is_clean(caplog):
    """caplog.text includes formatted tracebacks, so a leak through
    log.exception or an exception chain is caught here too."""
    for secret in (FAKE_NAME, FAKE_PASSPORT, FAKE_MASKED, FAKE_CHAT_ID, FAKE_TOKEN):
        assert secret not in caplog.text


def _capture_logs(caplog):
    caplog.set_level(logging.INFO, logger="checker")


def test_delivered_log_names_the_watchlist_id_only(session, monkeypatch, caplog):
    snapshot = _seed(session)
    watch, _, _ = _add_person(session, snapshot, FAKE_NAME, FAKE_PASSPORT, FAKE_MASKED, FAKE_CHAT_ID)
    session.commit()
    monkeypatch.setattr(main, "send_message", lambda *a, **k: {"ok": True})
    _capture_logs(caplog)

    assert main.deliver_pending_alerts(session) == []

    assert f"to watchlist id {watch.id}" in caplog.text
    assert "Delivered 1 telegram_renewal match(es)" in caplog.text
    _assert_log_is_clean(caplog)


def test_failed_delivery_log_keeps_the_reason_and_the_report_keeps_the_name(session, monkeypatch, caplog):
    snapshot = _seed(session)
    watch, _, record = _add_person(session, snapshot, FAKE_NAME, FAKE_PASSPORT, FAKE_MASKED, FAKE_CHAT_ID)
    session.commit()

    def refuse(*a, **k):
        raise TelegramAPIError("Telegram API error (400): Bad Request: chat not found")

    monkeypatch.setattr(main, "send_message", refuse)
    _capture_logs(caplog)

    failures = main.deliver_pending_alerts(session)

    assert f"Alert to watchlist id {watch.id} failed, keeping it pending" in caplog.text
    assert "chat not found" in caplog.text
    _assert_log_is_clean(caplog)
    # the operator's private report still names the person, so they can act on it
    assert FAKE_NAME in notify.format_delivery_failures(failures)
    assert record.notified_at is None


def test_no_chat_id_log_names_the_watchlist_id_only(session, monkeypatch, caplog):
    snapshot = _seed(session)
    watch, _, _ = _add_person(session, snapshot, FAKE_NAME, FAKE_PASSPORT, FAKE_MASKED, None)
    session.commit()
    monkeypatch.setattr(main, "send_message", lambda *a, **k: {"ok": True})
    _capture_logs(caplog)

    main.deliver_pending_alerts(session)

    assert f"Watchlist id {watch.id} has no telegram_chat_id" in caplog.text
    _assert_log_is_clean(caplog)


@pytest.fixture
def telegram_unreachable(monkeypatch):
    """Sends through the real notify.py and a real requests call to a closed
    local port, so the exception is the one requests really raises, with the
    token in the URL it reports."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", FAKE_CHAT_ID)
    monkeypatch.setattr(notify, "TELEGRAM_API", "http://127.0.0.1:9/bot{token}/{method}")


def test_network_failure_does_not_put_the_token_in_the_log(session, caplog, telegram_unreachable):
    with pytest.raises(requests.RequestException) as raised:
        notify.send_message("hello")
    assert FAKE_TOKEN in str(raised.value)    # the premise: this message would leak it

    snapshot = _seed(session)
    watch, _, _ = _add_person(session, snapshot, FAKE_NAME, FAKE_PASSPORT, FAKE_MASKED, FAKE_CHAT_ID)
    session.commit()
    _capture_logs(caplog)

    failures = main.deliver_pending_alerts(session)

    assert f"Alert to watchlist id {watch.id} failed" in caplog.text
    assert "ConnectionError" in caplog.text
    _assert_log_is_clean(caplog)
    # the token stays out of the operator's Telegram report as well
    assert FAKE_TOKEN not in failures[0]
    assert FAKE_NAME in failures[0]


def test_operator_message_failures_do_not_put_the_token_in_the_log(caplog, telegram_unreachable, tmp_path):
    _capture_logs(caplog)
    pdf = tmp_path / "approval.pdf"
    pdf.write_bytes(b"%PDF-")

    main._try_send("hello", label="heartbeat")
    main._try_send_document(str(pdf))

    assert "Could not send heartbeat: ConnectionError" in caplog.text
    assert "Could not send document" in caplog.text
    _assert_log_is_clean(caplog)


def test_rejected_document_reports_telegrams_reason_without_the_url(monkeypatch, tmp_path):
    """send_document used raise_for_status(), whose message is the full URL."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", FAKE_CHAT_ID)

    resp = requests.Response()
    resp.status_code = 413
    resp.reason = "Request Entity Too Large"
    resp.url = f"https://api.telegram.org/bot{FAKE_TOKEN}/sendDocument"
    resp._content = b'{"ok": false, "description": "Request Entity Too Large"}'
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: resp)

    pdf = tmp_path / "approval.pdf"
    pdf.write_bytes(b"%PDF-")
    with pytest.raises(TelegramAPIError) as raised:
        notify.send_document(str(pdf))

    assert "Request Entity Too Large" in safe_error_text(raised.value)
    assert FAKE_TOKEN not in str(raised.value)


def test_safe_error_text_keeps_only_what_is_safe(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)

    assert safe_error_text(TelegramAPIError("Telegram API error (400): Bad Request: chat not found")) \
        == "Telegram API error (400): Bad Request: chat not found"
    # anything that is not Telegram's own answer is reduced to its type
    assert safe_error_text(RuntimeError(f"{FAKE_NAME} {FAKE_TOKEN}")) == "RuntimeError"
    assert safe_error_text(requests.ConnectionError(f"/bot{FAKE_TOKEN}/sendMessage")) == "ConnectionError"
    assert FAKE_TOKEN not in safe_error_text(TelegramAPIError(f"upstream said {FAKE_TOKEN}"))


@pytest.mark.parametrize("description", [
    # Telegram's parse errors quote part of the message they rejected
    'can\'t parse entities: Unsupported start tag "thiha" at byte offset 9',
    # a balanced-quote pattern is defeated when the quoted text has quotes of its own
    'tag "fake"thiha"tail"',
    '"" thiha',
    # an unbalanced quote has nothing to pair with
    'tag "thiha at byte offset 9',
    'tag "x" "thiha',
])
def test_safe_error_text_keeps_nothing_after_the_first_quote(description):
    text = safe_error_text(TelegramAPIError(f"Telegram API error (400): {description}"))

    assert "thiha" not in text
    assert '"' not in text
    assert text.startswith("Telegram API error (400):")


def test_safe_error_text_redacts_the_token_before_cutting(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)

    # a token before the quote must not survive the cut
    assert safe_error_text(TelegramAPIError(f'bot{FAKE_TOKEN} rejected "x"')) == "bot[redacted] rejected"
    # a token holding a quote must be redacted whole, not cut in half and kept
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", 'to"ken')
    assert safe_error_text(TelegramAPIError('a to"ken b')) == "a [redacted] b"


def test_engine_errors_do_not_print_the_bound_values():
    """SQLAlchemy prints a failing statement's parameters into its message
    unless told not to, and run() logs those errors."""
    s = db.get_session("sqlite:///:memory:")
    try:
        s.add(db.Watchlist(full_name=FAKE_NAME, passport_no=FAKE_PASSPORT, lookup_token="same", active=True))
        s.add(db.Watchlist(full_name=FAKE_NAME, passport_no=FAKE_PASSPORT, lookup_token="same", active=True))
        with pytest.raises(IntegrityError) as raised:
            s.commit()
    finally:
        s.close()

    assert FAKE_NAME not in str(raised.value)
    assert FAKE_PASSPORT not in str(raised.value)


def test_a_crashed_check_does_not_log_the_row_the_database_quoted(session, monkeypatch, caplog):
    """Postgres quotes the row in the error text itself ("Failing row contains
    (...)"), which hide_parameters cannot reach."""
    def crash(_session):
        raise IntegrityError(
            "INSERT INTO entries ...", {},
            Exception(f"DETAIL: Failing row contains (1, {FAKE_NAME}, {FAKE_PASSPORT})"),
        )

    monkeypatch.setattr(main.db, "get_session", lambda: session)
    monkeypatch.setattr(main, "run_embassy_pdf_check", crash)
    monkeypatch.setattr(main, "run_telegram_renewal_check", lambda _session: None)
    _capture_logs(caplog)

    assert main.run() == 1

    assert "[embassy_pdf] Check failed: IntegrityError" in caplog.text
    assert "test_notify_delivery.py" in caplog.text    # still says where it broke
    _assert_log_is_clean(caplog)


def _run_with_embassy_crash(session, monkeypatch, crash):
    monkeypatch.setattr(main.db, "get_session", lambda: session)
    monkeypatch.setattr(main, "run_embassy_pdf_check", crash)
    monkeypatch.setattr(main, "run_telegram_renewal_check", lambda _session: None)
    return main.run()


def test_a_crash_that_is_not_a_database_error_logs_types_and_location_only(session, monkeypatch, caplog):
    def crash(_session):
        raise ValueError(f"Could not read {FAKE_NAME}")

    _capture_logs(caplog)

    assert _run_with_embassy_crash(session, monkeypatch, crash) == 1

    assert "[embassy_pdf] Check failed: ValueError at checker/tests/test_notify_delivery.py:" in caplog.text
    assert "Traceback" not in caplog.text
    _assert_log_is_clean(caplog)


def test_a_database_error_chained_under_another_exception_stays_out_of_the_log(session, monkeypatch, caplog):
    """The real shape: the DB error is raised inside `with TemporaryDirectory()`,
    and the cleanup raises OSError on the way out, so the top-level exception
    isn't a database error at all and the row is only in its __context__."""
    def crash(_session):
        try:
            raise IntegrityError(
                "INSERT INTO entries ...", {"name": FAKE_NAME},
                Exception(f"DETAIL: Failing row contains (1, {FAKE_NAME}, {FAKE_PASSPORT})"),
            )
        except IntegrityError:
            raise OSError(f"could not remove /tmp/{FAKE_NAME}")

    _capture_logs(caplog)

    assert _run_with_embassy_crash(session, monkeypatch, crash) == 1

    assert "OSError <- IntegrityError" in caplog.text
    assert "Traceback" not in caplog.text
    _assert_log_is_clean(caplog)


def test_a_real_sqlalchemy_chain_is_described_by_its_types(session, monkeypatch, caplog):
    def crash(s):
        s.add(db.Watchlist(full_name=FAKE_NAME, passport_no=FAKE_PASSPORT, lookup_token="same", active=True))
        s.add(db.Watchlist(full_name=FAKE_NAME, passport_no=FAKE_PASSPORT, lookup_token="same", active=True))
        s.commit()

    _capture_logs(caplog)

    assert _run_with_embassy_crash(session, monkeypatch, crash) == 1

    assert "IntegrityError <- IntegrityError at checker/tests/test_notify_delivery.py:" in caplog.text
    _assert_log_is_clean(caplog)


def test_telethons_decrypted_bytes_stay_out_of_the_log(session, monkeypatch, caplog):
    from telethon.errors import TypeNotFoundError

    secret_bytes = FAKE_NAME.encode()
    error = TypeNotFoundError(0x12345678, secret_bytes)
    assert FAKE_NAME in str(error)            # the premise: its message embeds them

    def crash(_session):
        raise error

    _capture_logs(caplog)

    assert _run_with_embassy_crash(session, monkeypatch, crash) == 1

    assert "TypeNotFoundError at" in caplog.text
    _assert_log_is_clean(caplog)


def test_exception_chain_with_a_cycle_terminates():
    first, second = ValueError("a"), KeyError("b")
    first.__context__, second.__context__ = second, first

    assert describe_exception(first).startswith("ValueError <- KeyError at")


# --- Crash visibility: schema metadata in the log, a notice to the operator --

class _FakeDriverError(Exception):
    pgcode = "23505"
    diag = SimpleNamespace(
        table_name="matches", constraint_name="uq_watchlist_passport",
        message_detail=f"Key (passport_canonical)=({FAKE_MASKED}) already exists.",
    )


def _db_crash(_session):
    raise IntegrityError("INSERT INTO matches ...", {}, _FakeDriverError(f"duplicate {FAKE_MASKED}"))


def test_psycopg2_has_the_diagnostic_attributes_the_log_reads():
    """_FakeDriverError stands in for it, as no Postgres runs in these tests."""
    error = psycopg2.errors.UniqueViolation()
    assert error.pgcode is None
    assert error.diag.table_name is None
    assert error.diag.constraint_name is None
    assert database_metadata(error) == ""


def test_a_database_crash_logs_schema_metadata_only(session, monkeypatch, caplog):
    _capture_logs(caplog)

    assert _run_with_embassy_crash(session, monkeypatch, _db_crash) == 1

    assert "sqlstate 23505, table matches, constraint uq_watchlist_passport" in caplog.text
    _assert_log_is_clean(caplog)


def test_a_crash_sends_the_operator_a_one_line_notice(session, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_message", lambda text, **k: sent.append(text))

    assert _run_with_embassy_crash(session, monkeypatch, _db_crash) == 1

    assert len(sent) == 1
    assert "\n" not in sent[0]
    assert "[embassy_pdf] Check failed" in sent[0]
    assert "IntegrityError at checker/tests/test_notify_delivery.py:" in sent[0]
    # stage, types and location only: not even the schema metadata
    for secret in (FAKE_MASKED, "uq_watchlist_passport", "23505"):
        assert secret not in sent[0]


def test_a_failed_crash_notice_keeps_the_exit_code_and_the_later_stages(session, monkeypatch, caplog, telegram_unreachable):
    later_stage_ran = []
    monkeypatch.setattr(main.db, "get_session", lambda: session)
    monkeypatch.setattr(main, "run_embassy_pdf_check", _db_crash)
    monkeypatch.setattr(main, "run_telegram_renewal_check", lambda _session: later_stage_ran.append(True))
    _capture_logs(caplog)

    assert main.run() == 1

    assert later_stage_ran == [True]
    assert "Could not send crash notice: ConnectionError" in caplog.text
    _assert_log_is_clean(caplog)


def test_a_clean_run_sends_no_crash_notice(session, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_message", lambda text, **k: sent.append(text))
    monkeypatch.setattr(main.db, "get_session", lambda: session)
    monkeypatch.setattr(main, "run_embassy_pdf_check", lambda _session: None)
    monkeypatch.setattr(main, "run_telegram_renewal_check", lambda _session: None)

    assert main.run() == 0
    assert sent == []


# --- Uncaught exceptions: the entry points' excepthook ----------------------

@pytest.mark.parametrize("entry_point", [["checker.main"], ["checker.diagnose", "pending"]])
def test_entry_point_database_outage_prints_no_host_or_user(entry_point):
    """A real process and a real driver error from a host that can't exist."""
    result = subprocess.run(
        [sys.executable, "-m", *entry_point],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ,
             "NEON_DATABASE_URL": "postgresql://fakeuser:fakepass@fake-db-host.invalid/fakedb?connect_timeout=5"},
        capture_output=True, text=True, timeout=120,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "Fatal: OperationalError" in output
    assert "at checker/db.py:" in output
    assert "Traceback" not in output
    for secret in ("fakeuser", "fakepass", "fake-db-host", "fakedb"):
        assert secret not in output


def test_excepthook_survives_being_unable_to_describe_the_exception(monkeypatch, capsys):
    def broken(_exc):
        raise ValueError("boom")

    monkeypatch.setattr(crash_report, "describe_exception", broken)

    crash_report._safe_excepthook(KeyError, KeyError(FAKE_NAME), None)

    assert capsys.readouterr().err == "Fatal: KeyError; detail withheld from this public log\n"


# --- Telethon ---------------------------------------------------------------

@pytest.mark.parametrize("module", ["checker.main", "checker.diagnose"])
def test_each_entry_point_silences_telethon_logging_on_its_own(module):
    """A fresh process, because the logger level is global and importing one
    module in this test run would hide the other one lacking the line."""
    check = (
        f"import logging, {module}\n"
        "for name in ('telethon', 'telethon.network.mtprotosender', 'telethon.client.updates'):\n"
        "    assert not logging.getLogger(name).isEnabledFor(logging.ERROR), name\n"
    )
    subprocess.run([sys.executable, "-c", check], cwd=Path(__file__).resolve().parents[2], check=True, timeout=60)


@pytest.fixture
def read_only_client(monkeypatch):
    """The real _client() with a sender that answers from memory, so Telethon's
    own iter_messages/get_messages code runs without a network."""
    from telethon.tl import types
    from telethon.tl.types.messages import Messages

    from checker import telegram_source

    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "fake")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "")
    client = telegram_source._client()
    sent = []

    def send(request, ordered=False):
        sent.append(request)
        reply = Messages(
            messages=[types.Message(
                id=7, peer_id=types.PeerChannel(1), date=datetime(2026, 1, 1, tzinfo=timezone.utc), message="post",
            )],
            topics=[], chats=[], users=[],
        )
        future = asyncio.get_running_loop().create_future()
        # the wire format, as the real sender would decode it
        with BinaryReader(bytes(reply)) as reader:
            future.set_result(request.read_result(reader))
        return future

    monkeypatch.setattr(client._sender, "send", send)
    return client, sent


def test_client_reads_history_without_updates(read_only_client):
    client, sent = read_only_client
    channel = InputPeerChannel(1, 1)

    assert [m.id for m in client.iter_messages(channel, limit=1)] == [7]
    assert isinstance(sent[-1], InvokeWithoutUpdatesRequest)
    assert isinstance(sent[-1].query, GetHistoryRequest)


def test_client_gets_messages_by_id_without_updates(read_only_client):
    client, sent = read_only_client
    channel = InputPeerChannel(1, 1)

    assert [m.id for m in client.get_messages(channel, ids=[7])] == [7]
    assert isinstance(sent[-1], InvokeWithoutUpdatesRequest)
    assert isinstance(sent[-1].query, GetChannelMessagesRequest)


def test_diagnose_report_failure_does_not_put_the_token_in_the_log(caplog, telegram_unreachable):
    from checker import diagnose

    caplog.set_level(logging.INFO, logger="diagnose")

    diagnose._report_to_operator("Undelivered matches", [f"{FAKE_NAME} {FAKE_PASSPORT}"])

    assert "Could not send the detail report to Telegram: ConnectionError" in caplog.text
    _assert_log_is_clean(caplog)


def test_diagnose_report_escapes_html_so_a_stray_bracket_cant_sink_it(monkeypatch):
    from checker import diagnose

    sent = []
    monkeypatch.setattr(diagnose, "send_message", sent.append)

    diagnose._report_to_operator("Undelivered matches", ["post 1 img 1: |<THIHA & ZAW"])

    assert "|&lt;THIHA &amp; ZAW</pre>" in sent[0]


def test_diagnose_report_escapes_after_truncating(monkeypatch):
    """Escaping first could let the cut land inside "&lt;" and leave a broken
    entity, which Telegram rejects just like a bare bracket."""
    from checker import diagnose

    sent = []
    monkeypatch.setattr(diagnose, "send_message", sent.append)

    diagnose._report_to_operator("Undelivered matches", ["<" * (diagnose.MAX_TELEGRAM_CHARS + 50)])

    body = sent[0].split("<pre>")[1].split("</pre>")[0]
    assert body == "&lt;" * diagnose.MAX_TELEGRAM_CHARS + "\n[...truncated]"


def test_shape_redaction_also_covers_non_latin_text():
    from checker.diagnose import _shape

    shaped = _shape("၀၇ မောင် THÉ 12")
    assert shaped.isascii()
    assert set(shaped) <= set("A9 ")
