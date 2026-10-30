"""Telegram notifications for the passport monitor."""
import html
import os

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 20


def _call(method: str, **params) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = TELEGRAM_API.format(token=token, method=method)
    resp = requests.post(url, data=params, timeout=TIMEOUT)
    if not resp.ok:
        # surface Telegram's actual reason (e.g. "Bad Request: chat not
        # found", "Forbidden: bot was blocked by the user") instead of a
        # generic "400 Client Error" that hides why it really failed
        try:
            description = resp.json().get("description", resp.text)
        except ValueError:
            description = resp.text
        raise RuntimeError(f"Telegram API error ({resp.status_code}): {description}")
    return resp.json()


def send_message(text: str, chat_id: str | None = None, parse_mode: str = "HTML") -> dict:
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    return _call("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode, disable_web_page_preview=True)


def get_chat(chat_id: str) -> dict:
    """Asks Telegram whether the bot can actually reach this chat. Raises the
    same RuntimeError send_message would, so an unreachable ID can be found
    before an alert is riding on it."""
    return _call("getChat", chat_id=chat_id)


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
    # watch_name is user-submitted at signup -- escape before interpolating
    # into a parse_mode="HTML" message so it can't break entity parsing
    # or inject tags into the alert.
    lines = [f"🛂 <b>Passport update for {html.escape(watch_name)}</b>"]
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
    lines = [f"\U0001F6C2 <b>Passport renewal appointment for {html.escape(watch_name)}</b>"]
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


def format_delivery_failures(failures: list[str]) -> str:
    """Operator-facing report. A match that was found but could not be
    delivered is the worst possible failure mode for this tool -- the person
    is on the list, the system knows it, and they were never told -- so it
    gets its own explicit message rather than only a line in the CI log."""
    lines = [
        "⚠️ <b>Could not deliver some alerts</b>",
        "These people have a recorded match but have not received it:",
    ]
    for failure in failures:
        lines.append(f"- {html.escape(failure)}")
    lines.append(
        "\nEach one stays pending and is retried on every run. "
        "<i>chat not found</i> normally means the stored Telegram ID is wrong, "
        "or the person never pressed Start in the bot -- correct the ID in /admin "
        "and the pending alert will go out on the next run."
    )
    return "\n".join(lines)
