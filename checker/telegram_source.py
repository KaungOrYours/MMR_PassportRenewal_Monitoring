"""Fetch posts from the @mesg15 "Consular Services for Myanmar Citizen
in Singapore" Telegram channel, where the embassy actually publishes the
PV/PJ passport-renewal appointment lists (the website only has the
separate Lost & Seaman list -- see fetch.py/extract.py for that one).

Uses Telethon's MTProto client (not the Bot API) because it's the only way
to fetch a public channel's photos at their original resolution without
needing admin rights on a channel we don't own. Requires a logged-in
session; see generate_session.py for the one-time interactive login.
"""
import os
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto

CHANNEL = "mesg15"


@dataclass
class RenewalPost:
    post_id: int  # max message id in the group -- used as the dedup watermark
    message_ids: list[int]
    date: str
    caption: str
    photos: list[bytes]  # original-resolution JPEG bytes, in post order


def _client() -> TelegramClient:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ["TELEGRAM_SESSION_STRING"]
    return TelegramClient(StringSession(session), api_id, api_hash)


def _group_into_posts(client: TelegramClient, messages: list) -> list[RenewalPost]:
    """Groups a chronologically-ordered message list into posts (collapsing
    multi-photo albums sharing a grouped_id into one RenewalPost each) and
    downloads each photo at its original resolution."""
    groups: dict[int, list] = {}
    standalone = []
    for msg in messages:
        if not isinstance(msg.media, MessageMediaPhoto):
            continue
        if msg.grouped_id is not None:
            groups.setdefault(msg.grouped_id, []).append(msg)
        else:
            standalone.append([msg])

    posts = []
    for group in list(groups.values()) + standalone:
        group.sort(key=lambda m: m.id)
        caption = next((m.message for m in group if m.message), "") or ""
        photos = []
        for m in group:
            buf = BytesIO()
            client.download_media(m, file=buf)
            photos.append(buf.getvalue())
        posts.append(RenewalPost(
            post_id=max(m.id for m in group),
            message_ids=[m.id for m in group],
            date=group[0].date.isoformat(),
            caption=caption,
            photos=photos,
        ))

    posts.sort(key=lambda p: p.post_id)
    return posts


def fetch_new_posts(since_message_id: int, limit: int = 200) -> list[RenewalPost]:
    """Returns photo posts newer than since_message_id, oldest first."""
    with _client() as client:
        messages = list(client.iter_messages(CHANNEL, min_id=since_message_id, limit=limit))
        messages.reverse()  # iter_messages is newest-first; we want chronological
        return _group_into_posts(client, messages)


def fetch_posts_since(since_date: datetime, limit: int = 1000) -> list[RenewalPost]:
    """Returns photo posts at or after since_date, oldest first. Used for the
    one-time backfill on first run, bounded by date rather than pulling the
    channel's entire history (which could be years of now-irrelevant,
    already-past-appointment posts on a channel this active)."""
    with _client() as client:
        messages = list(client.iter_messages(CHANNEL, offset_date=since_date, reverse=True, limit=limit))
        # defensive: guarantee the date floor regardless of the exact
        # inclusive/exclusive behavior of offset_date+reverse
        messages = [m for m in messages if m.date >= since_date]
        return _group_into_posts(client, messages)


def fetch_post_group(message_id: int, window: int = 30) -> list[RenewalPost]:
    """Re-fetches one specific post by message id, including the rest of its
    album. Used by the diagnostics CLI to re-examine a post the scheduled run
    has already moved its watermark past (fetch_new_posts can never see it
    again). The album's sibling messages sit on consecutive ids either side of
    the one given, so a small id window around it is enough to rebuild the
    whole group.
    """
    with _client() as client:
        ids = list(range(max(1, message_id - window), message_id + window + 1))
        messages = [m for m in client.get_messages(CHANNEL, ids=ids) if m is not None]
        target = next((m for m in messages if m.id == message_id), None)
        if target is None:
            return []
        if target.grouped_id is None:
            group = [target]
        else:
            group = [m for m in messages if m.grouped_id == target.grouped_id]
        return _group_into_posts(client, group)


def fetch_recent_posts(count: int = 3) -> list[RenewalPost]:
    """The most recent `count` photo posts, oldest first, regardless of the
    stored watermark. Diagnostics only -- the scheduled run must keep using
    fetch_new_posts so it never re-processes a post."""
    with _client() as client:
        messages = list(client.iter_messages(CHANNEL, limit=count * 15))
        messages.reverse()
        posts = _group_into_posts(client, messages)
        return posts[-count:]
