"""The public Lists search: masked output only, no browsing, rate limited.

Every name and number below is invented.

Run with backend/requirements.txt, pytest and httpx installed: pytest backend/tests/
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend import ratelimit
from backend.auth import get_db
from backend.main import app
from checker import db as models

FULL = "ZZ123456"
MASKED = "ZZ1***56"


@pytest.fixture
def session(tmp_path):
    # a file, not :memory:, because TestClient runs sync routes on another thread
    s = models.get_session(f"sqlite:///{tmp_path / 'test.db'}")
    snap = models.Snapshot(
        fetched_at=datetime(2026, 11, 1, tzinfo=timezone.utc), source="embassy_pdf", sha256="x",
        page_count=1, mode="text", row_count=0,
    )
    s.add(snap)
    s.flush()
    s.snapshot = snap
    yield s
    s.close()


@pytest.fixture
def client(session):
    ratelimit._hits.clear()
    ratelimit._windows.clear()
    app.dependency_overrides[get_db] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
    ratelimit._hits.clear()
    ratelimit._windows.clear()


def add(session, name, passport_no, remark=None, id_kind="passport"):
    session.add(models.Entry(
        snapshot_id=session.snapshot.id, page_no=1, name=name, passport_no=passport_no,
        id_kind=id_kind, approved_date=None, remark=remark,
    ))
    session.commit()


def search(client, q, **headers):
    return client.get("/api/entries/search", params={"q": q}, headers=headers)


def rows(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["results"]


@pytest.mark.parametrize("stored", [FULL, MASKED])
@pytest.mark.parametrize("typed", [FULL, "zz 123 456", f" {FULL} "])
def test_full_number_finds_the_row_before_and_after_the_cleanup_and_shows_only_the_mask(
        client, session, stored, typed):
    add(session, "ALPHA TESTER", stored)

    resp = search(client, typed)

    assert [r["passport_no"] for r in rows(resp)] == [MASKED]
    assert FULL not in resp.text


def test_a_typed_mask_is_not_searched(client, session):
    add(session, "ALPHA TESTER", MASKED)
    add(session, "ALPHA TESTER", "MF40**22", id_kind="masked_passport")

    for typed in (MASKED, "MF40**22", "ZZ1***"):
        resp = search(client, typed)
        assert resp.status_code == 400 or rows(resp) == []


def test_output_mask_is_idempotent_and_hides_other_stored_shapes(client, session):
    add(session, "BETA TESTER NAME", "SIRB-10245/24-12-2014", id_kind="other")
    add(session, "BETA TESTER NAME", "MF40**22", id_kind="masked_passport")

    got = {r["passport_no"] for r in rows(search(client, "beta tester"))}

    assert got == {"SI***14", "MF40**22"}


def test_full_number_in_old_name_or_remark_is_masked_too(client, session):
    add(session, f"GAMMA TESTER {FULL}", MASKED, remark=f"see {FULL}")

    resp = search(client, "gamma tester")

    assert FULL not in resp.text
    assert MASKED in resp.text


def test_a_passport_fragment_does_not_match(client, session):
    add(session, "DELTA TESTER", FULL)

    assert rows(search(client, "ZZ12")) == []
    assert search(client, "ZZ1234").status_code == 400
    assert search(client, "123456").status_code == 400    # digits are not a name


def test_percent_and_underscore_are_literal(client, session):
    add(session, "EPSILON ONE", MASKED)
    add(session, "ZETA 100% SURE", MASKED)
    add(session, "ETA_UNDER", MASKED)

    assert rows(search(client, "%%%%")) == []
    assert rows(search(client, "E_A_")) == []
    assert [r["name"] for r in rows(search(client, "100% S"))] == ["ZETA 100% SURE"]
    assert [r["name"] for r in rows(search(client, "ETA_U"))] == ["ETA_UNDER"]


def test_name_search_is_case_insensitive_and_needs_the_whole_substring(client, session):
    add(session, "KAUNG HTET KYAW", MASKED)

    assert len(rows(search(client, "kaung htet"))) == 1
    assert rows(search(client, "kaung kyaw")) == []


@pytest.mark.parametrize("q", ["ab", "a  b", "abc", "a b c", "  abc  "])
def test_short_names_are_rejected(client, q):
    # the pattern is the words joined, so spaces can't pad a 3-letter term
    assert search(client, q).status_code in (400, 422)


def test_names_with_long_digit_runs_are_rejected(client):
    assert search(client, "AB 1234").status_code == 400
    assert search(client, "AB 123").status_code == 200


@pytest.mark.parametrize("q", ["abcd\x00", "ab\x00cd", "abcd\n", "ab\tcd", "ab\x7fcd", "ab\x85cd"])
def test_control_characters_are_a_400_not_a_500(client, q):
    assert search(client, q).status_code == 400


def test_too_many_matches_returns_no_rows_and_a_flag(client, session):
    for i in range(51):
        add(session, f"THETA {i}", MASKED)
    for i in range(50):
        add(session, f"OMEGA {i}", MASKED)

    over = search(client, "theta").json()
    assert over == {"results": [], "too_many": True}
    exact = search(client, "omega").json()
    assert exact["too_many"] is False and len(exact["results"]) == 50


def test_the_browse_route_needs_an_admin_session(client, session):
    add(session, "IOTA TESTER", FULL)

    resp = client.get(f"/api/snapshots/{session.snapshot.id}/entries")

    assert resp.status_code == 401
    assert "IOTA" not in resp.text


def test_eleventh_search_in_an_hour_gets_a_friendly_429(client, session):
    add(session, "KAPPA TESTER", FULL)

    for _ in range(10):
        assert search(client, "kappa", **{"X-Forwarded-For": "203.0.113.5"}).status_code == 200
    blocked = search(client, "kappa", **{"X-Forwarded-For": "203.0.113.5"})

    assert blocked.status_code == 429
    assert "search limit" in blocked.json()["detail"]
    # another visitor is unaffected
    assert search(client, "kappa", **{"X-Forwarded-For": "203.0.113.6"}).status_code == 200


def test_a_spoofed_leftmost_forwarded_value_does_not_dodge_the_limit(client, session):
    add(session, "LAMBDA TESTER", FULL)

    for i in range(10):
        assert search(client, "lambda", **{"X-Forwarded-For": f"198.51.100.{i}, 203.0.113.7"}).status_code == 200
    blocked = search(client, "lambda", **{"X-Forwarded-For": "198.51.100.99, 203.0.113.7"})

    assert blocked.status_code == 429


def test_the_shared_backstop_blocks_everyone_after_300_searches(client, session, monkeypatch):
    add(session, "MU TESTER", FULL)
    for i in range(300):
        assert search(client, "mu te", **{"X-Forwarded-For": f"10.{i // 250}.{i % 250}.1"}).status_code == 200

    blocked = search(client, "mu te", **{"X-Forwarded-For": "10.9.9.9"})

    assert blocked.status_code == 429
    assert "busy" in blocked.json()["detail"]


# --- client address -------------------------------------------------------------

class FakeRequest:
    def __init__(self, forwarded=None, peer="192.0.2.1"):
        self.headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
        self.client = type("C", (), {"host": peer})() if peer else None


def test_client_ip_takes_the_last_entry_by_default(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert ratelimit._client_ip(FakeRequest("1.2.3.4, 203.0.113.7")) == "203.0.113.7"
    assert ratelimit._client_ip(FakeRequest("203.0.113.7")) == "203.0.113.7"


def test_client_ip_counts_hops_from_the_right(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    assert ratelimit._client_ip(FakeRequest("9.9.9.9, 203.0.113.7, 198.51.100.2")) == "203.0.113.7"
    assert ratelimit._client_ip(FakeRequest("198.51.100.2")) == "192.0.2.1"    # fewer entries than hops


@pytest.mark.parametrize("header", ["not-an-ip", "1.2.3.4, <script>", "", "1.2.3.4," , "x" * 2000])
def test_client_ip_falls_back_to_the_peer_when_the_header_is_unusable(monkeypatch, header):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert ratelimit._client_ip(FakeRequest(header)) == "192.0.2.1"


def test_client_ip_with_no_header_or_peer(monkeypatch):
    assert ratelimit._client_ip(FakeRequest(None)) == "192.0.2.1"
    assert ratelimit._client_ip(FakeRequest(None, peer=None)) == "unknown"


def test_bad_hop_count_falls_back_to_one(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "banana")
    assert ratelimit._client_ip(FakeRequest("1.1.1.1, 203.0.113.7")) == "203.0.113.7"


# --- limiter memory -------------------------------------------------------------

def test_expired_keys_are_swept_and_the_key_count_is_capped(monkeypatch):
    ratelimit._hits.clear()
    ratelimit._windows.clear()
    limiter = ratelimit.rate_limit("t", limit=5, window_seconds=10)
    clock = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ratelimit, "_last_sweep", 0.0)
    for i in range(20):
        limiter(FakeRequest(f"203.0.113.{i}"))
    assert len(ratelimit._hits) == 20

    clock[0] += 100    # all expired; the next request triggers the sweep
    limiter(FakeRequest("198.51.100.1"))
    assert list(ratelimit._hits) == ["t:198.51.100.1"]

    monkeypatch.setattr(ratelimit, "MAX_KEYS", 5)
    for i in range(30):
        limiter(FakeRequest(f"192.0.2.{i + 10}"))
    assert len(ratelimit._hits) <= 5
    ratelimit._hits.clear()
    ratelimit._windows.clear()
