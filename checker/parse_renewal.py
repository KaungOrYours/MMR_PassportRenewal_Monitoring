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

# OCR of a bordered table mangles the masked passport in predictable ways:
# the "*" comes back as "°", "+" or another stray mark; 0/1/5/8 come back as
# O/I/S/B; and an extra character sometimes splices in ("MHO01**98" for
# "MH01**98"). Demanding the literal "AA 99**99" only clean OCR produces was
# silently dropping real rows, so match a tolerant shape -- two letters, two
# or three digit-ish characters, a run of punctuation, two or three more --
# and canonicalize afterwards in canonical_masked_passport().
_DIGIT_ISH = r"[0-9OoQIl!|SsBZz]"
MASKED_PASSPORT_RE = re.compile(
    rf"\b([A-Za-z]{{2}})\s*({_DIGIT_ISH}{{2,3}})\s*([^0-9A-Za-z\s]{{1,3}})\s*({_DIGIT_ISH}{{2,3}})\b"
)
_TO_DIGIT = str.maketrans({
    "O": "0", "o": "0", "Q": "0",
    "I": "1", "l": "1", "!": "1", "|": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2",
})
# Index markers only ever matched cleanly-separated "99 NAME" lines, so on a
# bordered table ("91 |MI KAY THI AUNG") it counts 0 and the row-count-vs-
# marker-count integrity check is blind. The row numbers captured per row
# (RenewalRow.index_no) are the reliable signal -- see missing_indexes.
INDEX_RE = re.compile(r"^\s*(\d{1,3})\s+(?=[A-Za-z])", re.MULTILINE)
LEADING_INDEX_RE = re.compile(r"^\s*(\d{1,3})\s*")
TYPE_CODE_RE = re.compile(r"\b([A-Za-z]{2})\b")  # OCR reads "PV" as "Pv" often enough
HEADER_DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b")


@dataclass
class RenewalRow:
    page_no: int
    index_no: int | None  # the list's own row number, for sequence-gap detection
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
    def index_numbers(self) -> list[int]:
        return sorted({r.index_no for r in self.rows if r.index_no is not None})

    @property
    def missing_indexes(self) -> list[int]:
        """Row numbers absent from the run this page covers. These lists are
        numbered consecutively, so a hole is proof a row was lost -- and
        unlike the index-marker count, this still works when OCR glues the
        row number to a table border ("91 |MI KAY...")."""
        nums = self.index_numbers
        if len(nums) < 2:
            return []
        present = set(nums)
        return [n for n in range(nums[0], nums[-1] + 1) if n not in present]

    @property
    def has_gap(self) -> bool:
        # Three independent signals, because each misses what the others catch:
        # (1) row_count < index_marker_count -- a partial miss, when the index
        #     markers happen to be countable at all;
        # (2) row_count == 0 -- a *total* OCR failure, where index_marker_count
        #     comes back 0 too, so 0 < 0 is False and the page would otherwise
        #     be indistinguishable from an intentionally empty one;
        # (3) a hole in the row numbers -- the only one that fires on the real
        #     @mesg15 tables, where (1) is blind because INDEX_RE counts ~0.
        return (self.row_count < self.index_marker_count
                or self.row_count == 0
                or bool(self.missing_indexes))


def normalize_text(text: str) -> str:
    text = text.translate(BURMESE_DIGITS)
    text = text.replace("​", "").replace("﻿", "")
    # same confusable fold parse.py applies: tesseract reads a capital "I" as
    # "!" often enough, and "!" never legitimately appears in these lists
    text = text.replace("!", "I")
    return text


def canonical_masked_passport(letters: str, first: str, last: str) -> str:
    """Folds OCR's letter-for-digit slips and drops any spliced-in extra
    character, keeping the two digits nearest the mask from each side."""
    first = first.translate(_TO_DIGIT)[-2:]
    last = last.translate(_TO_DIGIT)[:2]
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

    masked = canonical_masked_passport(m.group(1), m.group(2), m.group(4))
    before = line[: m.start()]
    after = line[m.end():]

    index_match = LEADING_INDEX_RE.match(before)
    index_no = int(index_match.group(1)) if index_match else None

    name = normalize_name(LEADING_INDEX_RE.sub("", before, count=1))
    if not name:
        return None

    type_codes = [c.upper() for c in TYPE_CODE_RE.findall(after)]
    current_type = type_codes[0] if len(type_codes) >= 1 else None
    new_type = type_codes[1] if len(type_codes) >= 2 else None

    return RenewalRow(
        page_no=page_no, index_no=index_no, name=name, masked_passport=masked,
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
