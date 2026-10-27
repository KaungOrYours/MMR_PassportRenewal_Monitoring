"""Telegram webhook: auto-replies the instant someone taps "Start chat with
our bot" from the signup page, instead of requiring them to separately find
their chat ID via a third-party bot and remember to also start ours.

A bot can only message a user who has messaged it first (hard Telegram
platform rule) -- this closes that gap by making "start the bot" the very
first, one-tap step of the signup flow, and replying immediately with
either their chat ID (new user, to paste into the form) or their existing
status (returning user), so starting the bot alone is useful either way.
"""
import html
import logging
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from checker import db as models
from checker.notify import send_message

from .auth import get_db, webhook_secret

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
log = logging.getLogger("uvicorn.error")


def _frontend_base() -> str:
    return os.environ.get("FRONTEND_ORIGIN", "").split(",")[0].strip()


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected_secret = webhook_secret()
    if not expected_secret or not secrets.compare_digest(x_telegram_bot_api_secret_token or "", expected_secret):
        raise HTTPException(401, "Invalid webhook secret")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}  # not a message we care about (e.g. a reaction)

    chat_id = str(message.get("chat", {}).get("id", ""))
    if not chat_id:
        return {"ok": True}

    existing = db.query(models.Watchlist).filter_by(telegram_chat_id=chat_id).first()

    try:
        if existing is not None:
            base = _frontend_base()
            link = f"{base}/status/{existing.lookup_token}" if base and existing.lookup_token else None
            text = (
                f"👋 Welcome back, {html.escape(existing.full_name)} — you're already registered."
                + (f"\n\nCheck your status anytime: {link}" if link else "")
            )
        else:
            text = (
                "👋 Thanks for starting a chat with the MMR Passport Renewal Monitor bot.\n\n"
                f"Your Telegram ID is:\n<code>{chat_id}</code>\n\n"
                "Copy this into the \"Your Telegram ID\" field on the signup form to finish registering."
            )
        send_message(text, chat_id=chat_id)
    except Exception:
        log.exception("Failed to reply to Telegram webhook message")

    return {"ok": True}
