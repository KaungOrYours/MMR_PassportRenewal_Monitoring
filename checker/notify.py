"""Telegram notifications for the passport monitor."""
import html
import os

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 20

_MAX_ERROR_CHARS = 200


class TelegramAPIError(RuntimeError):
    """Telegram answered and refused the request. Its message holds Telegram's
    own description, never the request URL (which contains the bot token)."""


def raise_for_telegram_error(resp: requests.Response) -> None:
    if resp.ok:
        return
    # surface Telegram's actual reason (e.g. "Bad Request: chat not found",
    # "Forbidden: bot was blocked by the user") instead of requests' own
    # "400 Client Error ... for url: ...", which hides why it really failed
    # and prints the bot token along with the URL
    try:
        description = resp.json().get("description") or resp.reason
    except ValueError:
        description = resp.reason
    raise TelegramAPIError(f"Telegram API error ({resp.status_code}): {description}")


def safe_error_text(exc: BaseException) -> str:
    """What may be logged about a failed Telegram call. This repo's Actions
    logs are public.

    Only a TelegramAPIError keeps its text. Anything else is reduced to its
    type, because a requests exception's message includes the request URL and
    so the bot token. Telegram's description is cut at its first double quote
    too: a parse error can quote part of the rejected message ('Unsupported
    start tag "..."'), and that message holds names and OCR text. Nothing after
    the quote can be trusted, since the quoted text may contain quotes itself.
    """
    if not isinstance(exc, TelegramAPIError):
        return type(exc).__name__
    text = str(exc)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        text = text.replace(token, "[redacted]")
    return text.split('"', 1)[0].rstrip()[:_MAX_ERROR_CHARS]


def _call(method: str, **params) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = TELEGRAM_API.format(token=token, method=method)
    resp = requests.post(url, data=params, timeout=TIMEOUT)
    raise_for_telegram_error(resp)
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
    raise_for_telegram_error(resp)
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
