"""Masks a list row's identifier before it is stored.

Matching compares full numbers in memory, so a full number never needs to reach
the database. Anything without a recognized passport shape, such as a seaman-book
number, is masked harder rather than returned as it came.
"""
import re

from .parse import LOOSE_ID_RE, STRICT_PASSPORT_RE

_PASSPORT_RE = re.compile(r"^([A-Z]{1,3})(\d{6,7})$")
_MIN_LENGTH_TO_SHOW_ENDS = 8


def mask_identifier(value: str) -> str:
    """'MK650912' -> 'MK6***12', 'SIRB-10245/24-12-2014' -> 'SI***14', 'CDC3363' -> '***'.

    A value that is already masked comes back unchanged, so this is safe to apply
    twice."""
    compact = re.sub(r"\s+", "", value).upper()
    if "*" in compact:
        return compact
    passport = _PASSPORT_RE.match(compact)
    if passport:
        letters, digits = passport.groups()
        return f"{letters}{digits[0]}***{digits[-2:]}"
    if len(compact) < _MIN_LENGTH_TO_SHOW_ENDS:
        return "***"
    return f"{compact[:2]}***{compact[-2:]}"


def scrub_identifiers(text: str | None) -> str | None:
    """Masks anything identifier-shaped left in a row's name or remark. A line
    can hold a second identifier, and the parser leaves it in the text around
    the first one. A number OCR has split apart can't be recognized here."""
    if not text:
        return text
    masked = STRICT_PASSPORT_RE.sub(lambda m: mask_identifier(m.group(0)), text)
    return LOOSE_ID_RE.sub(lambda m: mask_identifier(m.group(0)), masked)
