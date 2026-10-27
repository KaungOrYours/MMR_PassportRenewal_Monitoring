"""Parse the PV/PJ passport-type renewal table format posted to the
@mesg15 Telegram channel.

This is a different document family from the embassy website's Lost &
Seaman PDF (see parse.py): one specific appointment date per image, a bare
numeric index with no punctuation, and a passport number with the middle
two digits redacted for privacy (e.g. "MF 40**22"). Row anchor is the
masked-passport pattern; the same per-page integrity check (index markers
vs. parsed rows) applies.
"""
import re
from dataclasses import dataclass, field

from .parse import BURMESE_DIGITS, normalize_name

MASKED_PASSPORT_RE = re.compile(r"\b([A-Za-z]{2})\s?(\d{2})\*{1,2}(\d{2})\b")
INDEX_RE = re.compile(r"^\s*(\d{1,3})\s+(?=[A-Za-z])", re.MULTILINE)
TYPE_CODE_RE = re.compile(r"\b([A-Z]{2})\b")
HEADER_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b")


@dataclass
class RenewalRow:
    page_no: int
    name: str
    masked_passport: str
    current_type: str | None
    new_type: str | None
    appointment_date: str | None
    raw_line: str


@dataclass
class RenewalPageParseResult:
    page_no: int
    rows: list[RenewalRow] = field(default_factory=list)
    index_marker_count: int = 0
    row_count: int = 0

    @property
    def has_gap(self) -> bool:
        return self.row_count < self.index_marker_count


def normalize_text(text: str) -> str:
    text = text.translate(BURMESE_DIGITS)
    text = text.replace("​", "").replace("﻿", "")
    return text


def canonical_masked_passport(letters: str, first: str, last: str) -> str:
    return f"{letters.upper()}{first}**{last}"


def _page_date(text: str) -> str | None:
    """The appointment/announcement date appears once near the top of the
    image and applies to every row on that page."""
    m = HEADER_DATE_RE.search(text)
    return m.group(1) if m else None


def _extract_row(page_no: int, line: str, page_date: str | None) -> RenewalRow | None:
    m = MASKED_PASSPORT_RE.search(line)
    if not m:
        return None

    masked = canonical_masked_passport(*m.groups())
    before = line[: m.start()]
    after = line[m.end():]

    name = normalize_name(re.sub(r"^\s*\d{1,3}\s*", "", before))
    if not name:
        return None

    type_codes = TYPE_CODE_RE.findall(after)
    current_type = type_codes[0] if len(type_codes) >= 1 else None
    new_type = type_codes[1] if len(type_codes) >= 2 else None

    return RenewalRow(
        page_no=page_no, name=name, masked_passport=masked,
        current_type=current_type, new_type=new_type,
        appointment_date=page_date, raw_line=line.strip(),
    )


def parse_renewal_page(page_no: int, raw_text: str) -> RenewalPageParseResult:
    text = normalize_text(raw_text)
    index_count = len(INDEX_RE.findall(text))
    page_date = _page_date(text)

    rows: list[RenewalRow] = []
    for line in text.splitlines():
        row = _extract_row(page_no, line, page_date)
        if row is not None:
            rows.append(row)

    return RenewalPageParseResult(page_no=page_no, rows=rows, index_marker_count=index_count, row_count=len(rows))
