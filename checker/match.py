"""Match parsed approval-list rows against the watchlist.

Matching relies on the passport/ID number alone. Names are OCR'd from
scanned images and are too failure-prone to gate a match on -- a genuine
match can have a mangled name (a dropped letter, a misread character) while
the passport number still reads correctly, and requiring both would turn
that into a missed notification instead of a successful one. The passport
number is the authoritative unique identifier; the name is kept only as an
informational field on the match (matched_on/score), not a requirement.
"""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .parse import Row, canonical_passport, normalize_name
from .parse_renewal import RenewalRow

# characters that OCR and manual typing commonly confuse in alphanumeric codes
_CONFUSABLE_FOLD = str.maketrans({
    "O": "0", "Q": "0",
    "I": "1", "L": "1",
    "S": "5",
    "B": "8",
    "Z": "2",
    "G": "6",
})

NAME_MATCH_THRESHOLD = 88


@dataclass
class WatchlistEntry:
    id: int
    full_name: str
    passport_no: str | None


@dataclass
class Match:
    watchlist_id: int
    row: Row
    confidence: str  # "high" or "medium"
    matched_on: str  # "name+passport", "passport", or "name"
    score: int


def fold_confusables(identifier: str) -> str:
    """Collapse visually-confusable characters so OCR/typing slips don't break equality."""
    return re.sub(r"\s+", "", identifier).upper().translate(_CONFUSABLE_FOLD)


def _name_matches(watch_name: str, row_name: str) -> tuple[bool, int]:
    a = normalize_name(watch_name)
    b = normalize_name(row_name)
    if not a or not b:
        return False, 0
    # spaces-removed exact check catches OCR/typo word-splitting, e.g.
    # "MA JI SENG GAM" vs "MAJISENG GAM"
    if a.replace(" ", "") == b.replace(" ", ""):
        return True, 100
    # token_sort_ratio (not token_set_ratio): token_set_ratio scores a
    # perfect 100 whenever one name's words are a subset of the other's,
    # which is a false-positive magnet for Myanmar names that commonly
    # share a short base ("KAUNG HTET" vs "KAUNG HTET KYAW" are different
    # people, not an OCR variant of the same name). token_sort_ratio
    # penalizes the extra/missing word via overall string length instead.
    score = fuzz.token_sort_ratio(a, b)
    return score >= NAME_MATCH_THRESHOLD, int(score)


def match_row(entry: WatchlistEntry, row: Row) -> Match | None:
    passport_match = (
        entry.passport_no is not None
        and fold_confusables(entry.passport_no) == fold_confusables(row.passport_no)
    )
    if not passport_match:
        return None
    name_match, name_score = _name_matches(entry.full_name, row.name)
    return Match(entry.id, row, "high", "name+passport" if name_match else "passport", name_score)


def find_matches(watchlist: list[WatchlistEntry], rows: list[Row]) -> list[Match]:
    matches = []
    for entry in watchlist:
        for row in rows:
            m = match_row(entry, row)
            if m is not None:
                matches.append(m)
    return matches


@dataclass
class RenewalMatch:
    watchlist_id: int
    row: RenewalRow
    confidence: str
    matched_on: str
    score: int


def masked_passport_matches(full_passport: str, masked: str) -> bool:
    """Compares a watchlist entry's full passport number against a masked
    entry (e.g. "MG77**48") where the middle two of the six digits are
    redacted -- checks the letters and the visible first/last two digits."""
    full = canonical_passport(full_passport)
    m = re.match(r"^([A-Z]{2})(\d{6})$", full)
    if not m:
        return False
    full_letters, full_digits = m.groups()

    masked = masked.upper().replace(" ", "")
    mm = re.match(r"^([A-Z]{2})(\d{2})\*{1,2}(\d{2})$", masked)
    if not mm:
        return False
    masked_letters, first2, last2 = mm.groups()

    return full_letters == masked_letters and full_digits[0:2] == first2 and full_digits[4:6] == last2


def match_renewal_row(entry: WatchlistEntry, row: RenewalRow) -> RenewalMatch | None:
    # same reasoning as match_row above -- passport alone is sufficient
    passport_match = entry.passport_no is not None and masked_passport_matches(entry.passport_no, row.masked_passport)
    if not passport_match:
        return None
    name_match, name_score = _name_matches(entry.full_name, row.name)
    return RenewalMatch(entry.id, row, "high", "name+passport" if name_match else "passport", name_score)


def find_renewal_matches(watchlist: list[WatchlistEntry], rows: list[RenewalRow]) -> list[RenewalMatch]:
    matches = []
    for entry in watchlist:
        for row in rows:
            m = match_renewal_row(entry, row)
            if m is not None:
                matches.append(m)
    return matches
