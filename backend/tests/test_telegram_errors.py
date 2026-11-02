"""The bot token must never reach a public API response or the backend's logs.

A requests exception's message contains the request URL, and so the token. The
signup endpoint returns telegram_error to whoever called it, and that endpoint
is public, so this is a disclosure to anyone at all, not only a logging issue.

Run with backend/requirements.txt and pytest installed: pytest backend/tests/
"""
import asyncio
import logging

import pytest
import requests

from backend import main as backend_main
from backend import telegram_webhook
from backend.schemas import WatchlistIn
from checker import db as models
from checker import notify

FAKE_TOKEN = "123456:FAKE-token-for-tests"
FAKE_SECRET = "fake-webhook-secret"


@pytest.fixture
def session():
    s = models.get_session("sqlite:///:memory:")
    yield s
    s.close()


@pytest.fixture
def telegram_unreachable(monkeypatch):
    """Real notify.py and a real requests call to a closed local port."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setattr(notify, "TELEGRAM_API", "http://127.0.0.1:9/bot{token}/{method}")
    with pytest.raises(requests.RequestException) as raised:
        notify.send_message("hello", chat_id="1")
    assert FAKE_TOKEN in str(raised.value)    # the premise: this message would leak it


def test_try_send_returns_only_the_exception_type_on_a_network_failure(telegram_unreachable, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    sent, error = backend_main._try_send("hello", chat_id="1")

    assert (sent, error) == (False, "ConnectionError")
    assert "Failed to send Telegram message: ConnectionError" in caplog.text
    assert FAKE_TOKEN not in caplog.text


def test_try_send_keeps_telegrams_reason(monkeypatch):
    def refuse(*a, **k):
        raise notify.TelegramAPIError("Telegram API error (400): Bad Request: chat not found")

    monkeypatch.setattr(backend_main, "send_message", refuse)

    assert backend_main._try_send("hello", chat_id="1") == (
        False, "Telegram API error (400): Bad Request: chat not found")


def test_public_signup_response_does_not_contain_the_token(telegram_unreachable, session, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    out = backend_main.create_watchlist(
        WatchlistIn(full_name="THIHA ZAW MYINT", telegram_chat_id="880011223", terms_accepted=True),
        session=session,
    )

    assert out.telegram_sent is False
    assert out.telegram_error == "ConnectionError"
    assert FAKE_TOKEN not in out.model_dump_json()
    assert FAKE_TOKEN not in caplog.text


def _webhook_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("BACKEND_PUBLIC_URL", "https://backend.example.invalid")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", FAKE_SECRET)


def _setwebhook_response(status, body, reason="Unauthorized"):
    resp = requests.Response()
    resp.status_code = status
    resp.reason = reason
    resp.url = f"https://api.telegram.org/bot{FAKE_TOKEN}/setWebhook"
    resp._content = body
    return resp


def test_webhook_registration_refused_logs_telegrams_reason_only(monkeypatch, caplog):
    _webhook_env(monkeypatch)
    resp = _setwebhook_response(401, b'{"ok": false, "description": "Unauthorized"}')
    monkeypatch.setattr(backend_main.requests, "post", lambda *a, **k: resp)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    backend_main._register_telegram_webhook()

    assert "Failed to register Telegram webhook: Telegram API error (401): Unauthorized" in caplog.text
    assert FAKE_TOKEN not in caplog.text


def test_webhook_registration_network_failure_logs_the_type_only(monkeypatch, caplog):
    _webhook_env(monkeypatch)

    def fail(*a, **k):
        raise requests.ConnectionError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/setWebhook")

    monkeypatch.setattr(backend_main.requests, "post", fail)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    backend_main._register_telegram_webhook()

    assert "Failed to register Telegram webhook: ConnectionError" in caplog.text
    assert "Traceback" not in caplog.text
    assert FAKE_TOKEN not in caplog.text


def test_webhook_registration_success_log_is_harmless(monkeypatch, caplog):
    _webhook_env(monkeypatch)
    resp = _setwebhook_response(200, b'{"ok": true, "result": true, "description": "Webhook was set"}', "OK")
    monkeypatch.setattr(backend_main.requests, "post", lambda *a, **k: resp)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    backend_main._register_telegram_webhook()

    assert "Webhook was set" in caplog.text
    assert FAKE_TOKEN not in caplog.text
    assert FAKE_SECRET not in caplog.text


def test_webhook_reply_failure_does_not_put_the_token_in_the_log(telegram_unreachable, session, monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", FAKE_SECRET)
    caplog.clear()
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    class FakeRequest:
        async def json(self):
            return {"message": {"chat": {"id": 880011223}, "text": "/start"}}

    result = asyncio.run(telegram_webhook.telegram_webhook(
        FakeRequest(), x_telegram_bot_api_secret_token=FAKE_SECRET, db=session))

    assert result == {"ok": True}
    assert "Failed to reply to Telegram webhook message: ConnectionError" in caplog.text
    assert "Traceback" not in caplog.text
    assert FAKE_TOKEN not in caplog.text
