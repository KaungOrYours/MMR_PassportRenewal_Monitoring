"""Telegram notifications for the passport monitor."""
import os

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 20


def _call(method: str, **params) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = TELEGRAM_API.format(token=token, method=method)
    resp = requests.post(url, data=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def send_message(text: str, chat_id: str | None = None, parse_mode: str = "HTML") -> dict:
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    return _call("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode, disable_web_page_preview=True)


def send_document(file_path: str, caption: str = "", chat_id: str | None = None) -> dict:
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = TELEGRAM_API.format(token=token, method="sendDocument")
    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"document": f},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()


def format_match_alert(watch_name: str, matches: list) -> str:
    lines = [f"🛂 <b>Passport update for {watch_name}</b>"]
    for m in matches:
        badge = "✅ high confidence" if m.confidence == "high" else f"⚠️ medium confidence ({m.matched_on})"
        lines.append(
            f"\n<b>{m.row.name}</b>\n"
            f"ID: <code>{m.row.passport_no}</code>\n"
            f"Date: {m.row.approved_date or 'n/a'}\n"
            f"Page: {m.row.page_no}\n"
            f"{badge}"
        )
    return "\n".join(lines)


def format_heartbeat(row_count: int, page_count: int, mode: str, match_count: int) -> str:
    status = f"{match_count} match(es)" if match_count else "no matches"
    return (
        f"📋 New passport approval list published.\n"
        f"{row_count} entries across {page_count} page(s) ({mode} extraction).\n"
        f"{status} against your watchlist."
    )


def format_integrity_warning(issues: list) -> str:
    lines = ["⚠️ <b>Some rows could not be read reliably</b>", "The list below may be incomplete:"]
    for issue in issues:
        lines.append(f"- page {issue['page_no']}: {issue['detail']}")
    lines.append("\nIf you were expecting to appear on this list, check the PDF manually.")
    return "\n".join(lines)


def format_renewal_alert(watch_name: str, matches: list) -> str:
    lines = [f"\U0001F6C2 <b>Passport renewal appointment for {watch_name}</b>"]
    for m in matches:
        badge = "\u2705 high confidence" if m.confidence == "high" else f"\u26a0\ufe0f medium confidence ({m.matched_on})"
        lines.append(
            f"\n<b>{m.row.name}</b>\n"
            f"ID: <code>{m.row.masked_passport}</code>\n"
            f"Type change: {m.row.current_type or '?'} \u2192 {m.row.new_type or '?'}\n"
            f"<b>Appointment date: {m.row.appointment_date or 'n/a'}</b>\n"
            f"{badge}\n"
            f"\u26a0\ufe0f Go to the embassy in person on this date to complete the renewal."
        )
    return "\n".join(lines)


def format_renewal_heartbeat(row_count: int, photo_count: int, match_count: int) -> str:
    status = f"{match_count} match(es)" if match_count else "no matches"
    return (
        f"\U0001F4CB New renewal appointment list posted on the consular Telegram channel.\n"
        f"{row_count} entries across {photo_count} image(s).\n"
        f"{status} against your watchlist."
    )
