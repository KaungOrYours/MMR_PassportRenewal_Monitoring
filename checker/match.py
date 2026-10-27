"""Match parsed approval-list rows against the watchlist.

Passport/ID numbers are the strong signal (unique, and OCR-correctable via a
confusable-character fold); names are a supporting signal since common
Burmese names repeat across the list. A match is "high" confidence when both
agree, "medium" when only one does -- both are reported, but labelled, so
false positives are easy to eyeball rather than silently trusted.
"""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .parse import Row, canonical_passport, normalize_name

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
    score = fuzz.token_set_ratio(a, b)
    return score >= NAME_MATCH_THRESHOLD, int(score)


def match_row(entry: WatchlistEntry, row: Row) -> Match | None:
    passport_match = (
        entry.passport_no is not None
        and fold_confusables(entry.passport_no) == fold_confusables(row.passport_no)
    )
    name_match, name_score = _name_matches(entry.full_name, row.name)

    if passport_match and name_match:
        return Match(entry.id, row, "high", "name+passport", name_score)
    if passport_match:
        return Match(entry.id, row, "medium", "passport", name_score)
    if name_match:
        return Match(entry.id, row, "medium", "name", name_score)
    return None


def find_matches(watchlist: list[WatchlistEntry], rows: list[Row]) -> list[Match]:
    matches = []
    for entry in watchlist:
        for row in rows:
            m = match_row(entry, row)
            if m is not None:
                matches.append(m)
    return matches
