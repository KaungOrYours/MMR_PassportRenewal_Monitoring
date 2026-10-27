"""Conditional fetch of the embassy passport-approval PDF."""
import hashlib
from dataclasses import dataclass

import requests

PDF_URL = "http://www.myanmarembassy.sg/downloads/consular/PassportLost&SeamanOffshoreApprovedList.pdf"
USER_AGENT = "Mozilla/5.0 (compatible; PassportMonitor/1.0; +https://github.com/KaungOrYours)"
TIMEOUT = 30


@dataclass
class FetchResult:
    changed: bool
    content: bytes | None
    etag: str | None
    last_modified: str | None
    sha256: str | None


def fetch(prev_etag: str | None = None, prev_last_modified: str | None = None, prev_sha256: str | None = None) -> FetchResult:
    """Conditionally GET the PDF. Returns changed=False on 304 or identical content hash."""
    headers = {"User-Agent": USER_AGENT}
    if prev_etag:
        headers["If-None-Match"] = prev_etag
    if prev_last_modified:
        headers["If-Modified-Since"] = prev_last_modified

    resp = requests.get(PDF_URL, headers=headers, timeout=TIMEOUT)

    if resp.status_code == 304:
        return FetchResult(False, None, prev_etag, prev_last_modified, prev_sha256)

    resp.raise_for_status()
    content = resp.content

    if not content.startswith(b"%PDF"):
        raise ValueError(f"Response does not look like a PDF (first bytes: {content[:16]!r})")

    sha256 = hashlib.sha256(content).hexdigest()
    if sha256 == prev_sha256:
        return FetchResult(False, None, resp.headers.get("ETag"), resp.headers.get("Last-Modified"), sha256)

    return FetchResult(
        True,
        content,
        resp.headers.get("ETag"),
        resp.headers.get("Last-Modified"),
        sha256,
    )
