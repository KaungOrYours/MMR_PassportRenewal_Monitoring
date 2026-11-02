"""Minimal in-process rate limiting -- no Redis/external store, which is
fine for this app's scale and matches how it's actually deployed: a single
Render web-service instance (the start command runs uvicorn with no
--workers), so an in-memory dict is shared by every request and never goes
stale across processes. Would need a shared store instead if this ever
moves to multiple instances/workers.

Applied to endpoints that are either unauthenticated (signup) or security-
sensitive (device/session bootstrap) and therefore worth slowing down for
an automated client, without meaningfully inconveniencing a human.
"""
import ipaddress
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque] = defaultdict(deque)
_windows: dict[str, int] = {}
MAX_KEYS = 20000
SWEEP_EVERY_SECONDS = 60
MAX_FORWARDED_HEADER_CHARS = 1000
_last_sweep = 0.0


def _trusted_hops() -> int:
    try:
        return max(1, int(os.environ.get("TRUSTED_PROXY_HOPS", "1")))
    except ValueError:
        return 1


def _client_ip(request: Request) -> str:
    """The address our own proxy chain saw, not one the caller wrote.

    Each proxy appends the address it received the request from, so the entries
    counted from the RIGHT are the trustworthy ones; everything to the left was
    supplied by the caller and can be anything. TRUSTED_PROXY_HOPS is how many
    proxies of ours sit in front of this app (default 1: take the last entry). If
    the header is missing, oversized, too short or not an IP, fall back to the
    socket peer."""
    fallback = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or len(forwarded) > MAX_FORWARDED_HEADER_CHARS:
        return fallback
    parts = [p.strip() for p in forwarded.split(",")]
    hops = _trusted_hops()
    if hops > len(parts):
        return fallback
    try:
        return str(ipaddress.ip_address(parts[-hops]))
    except ValueError:
        return fallback


def _sweep(now: float) -> None:
    """Drops keys whose hits have all expired, and the oldest keys beyond MAX_KEYS."""
    global _last_sweep
    _last_sweep = now
    for key in list(_hits):
        hits = _hits[key]
        if not hits or now - hits[-1] > _windows.get(key, 0):
            del _hits[key]
            _windows.pop(key, None)
    while len(_hits) > MAX_KEYS:
        oldest = next(iter(_hits))
        del _hits[oldest]
        _windows.pop(oldest, None)


def rate_limit(key_prefix: str, limit: int, window_seconds: int, message: str | None = None, shared: bool = False):
    """shared=True counts every visitor together: a backstop that holds even if
    visitors can't be told apart."""

    def dependency(request: Request) -> None:
        key = key_prefix if shared else f"{key_prefix}:{_client_ip(request)}"
        now = time.monotonic()
        if now - _last_sweep > SWEEP_EVERY_SECONDS:
            _sweep(now)
        hits = _hits[key]
        _windows[key] = window_seconds
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(429, message or "Too many requests -- try again later.")
        hits.append(now)
        if len(_hits) > MAX_KEYS:
            _sweep(now)

    return dependency
