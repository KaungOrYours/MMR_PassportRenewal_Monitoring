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
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Render's edge proxy sets X-Forwarded-For; request.client.host alone
    # would just be the proxy's own address for every request.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key_prefix: str, limit: int, window_seconds: int):
    def dependency(request: Request) -> None:
        key = f"{key_prefix}:{_client_ip(request)}"
        now = time.monotonic()
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(429, "Too many requests -- try again later.")
        hits.append(now)

    return dependency
