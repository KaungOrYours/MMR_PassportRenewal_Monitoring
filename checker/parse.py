"""Parse normalized page text into structured approval-list rows.

Each row lives on a single line in the embassy's layout: index marker, name,
an identifier column, a date, and a Burmese remark. The identifier column is
usually a passport number (2 letters + 6 digits) but for seaman/offshore
entries it is instead a seaman-book style code (e.g. "SIRB-10245/24-12-2014"
or "M835131"). Row anchoring tries the strict passport pattern first and
falls back to the looser "other identifier" pattern so those rows are not
silently dropped -- a dropped row means a missed notification.

A per-page integrity check compares the count of index markers against the
count of successfully parsed rows, to catch anything neither pattern caught
(this is what exposed the seaman-book-number case during testing).
"""
import re
from dataclasses import dataclass, field

BURMESE_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")

STRICT_PASSPORT_RE = re.compile(r"\b([A-Za-z])\s?([A-Za-z])\s?(\d{6})\b")  # standard MF123456 form -> 'passport' kind
LOOSE_ID_RE = re.compile(r"\b([A-Za-z]{1,4})[\s-]?(\d{4,7})\b")  # seaman-book / CDC / mistyped-length codes -> 'other' kind
DATE_RE = re.compile(r"\b(\d{1,2}\s?[/-]\s?\d{1,2}\s?[/-]\s?\d{4})\b")
# Index markers: "1.", "12,", "1။" (post Burmese-digit-normalization), OCR table pipes "1. |"
INDEX_RE = re.compile(r"^\s*(\d{1,3})\s*[.|,၊။]", re.MULTILINE)
LEADING_INDEX_RE = re.compile(r"^\s*\d{1,3}\s*[.|,၊။]?\s*\|?\s*")
TABLE_NOISE_RE = re.compile(r"[|│]")


@dataclass
class Row:
    page_no: int
    name: str
    passport_no: str
    id_kind: str  # "passport" or "other"
    approved_date: str | None
    remark: str
    raw_line: str


@dataclass
class PageParseResult:
    page_no: int
    rows: list[Row] = field(default_factory=list)
    index_marker_count: int = 0
    row_count: int = 0

    @property
    def has_gap(self) -> bool:
        # row_count may exceed index_marker_count (e.g. a special unnumbered
        # entry) but must never fall short of it
        return self.row_count < self.index_marker_count


def normalize_text(text: str) -> str:
    text = text.translate(BURMESE_DIGITS)
    text = text.replace("​", "").replace("﻿", "")
    # OCR confusable: tesseract reads a capital "I" as "!" often enough in the
    # embassy scans (seen e.g. in "M! 659383" for "MI 659383") -- "!" never
    # otherwise occurs in this document, so folding it to "I" is safe.
    text = text.replace("!", "I")
    return text


def normalize_name(name: str) -> str:
    name = TABLE_NOISE_RE.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip(" .,:-")
    return name.upper()


def canonical_passport(raw: str) -> str:
    """Uppercase, strip internal spaces -- used for exact storage/display form."""
    return re.sub(r"\s+", "", raw).upper()


def _extract_row(page_no: int, line: str, fallback_name: str) -> Row | None:
    """fallback_name is used when the row line itself has no name text --
    this happens when a long or Burmese-script name wraps to its own line
    directly above the index+identifier line."""
    m = STRICT_PASSPORT_RE.search(line)
    id_kind = "passport"
    if not m:
        m = LOOSE_ID_RE.search(line)
        id_kind = "other"
    if not m:
        return None

    identifier = canonical_passport(m.group(0))
    before = line[: m.start()]
    after = line[m.end():]

    name = normalize_name(LEADING_INDEX_RE.sub("", before))
    if not name:
        name = normalize_name(fallback_name)
    if not name:
        return None  # identifier-shaped match with no recoverable name is noise, not a row

    date_m = DATE_RE.search(after)
    approved_date = date_m.group(1) if date_m else None
    remark = after[date_m.end():].strip(" .,:-|") if date_m else after.strip(" .,:-|")

    return Row(
        page_no=page_no,
        name=name,
        passport_no=identifier,
        id_kind=id_kind,
        approved_date=approved_date,
        remark=remark,
        raw_line=line.strip(),
    )


def parse_page(page_no: int, raw_text: str) -> PageParseResult:
    text = normalize_text(raw_text)
    index_count = len(INDEX_RE.findall(text))

    rows: list[Row] = []
    prev_candidate_name = ""
    for line in text.splitlines():
        stripped = line.strip()
        has_own_id = bool(STRICT_PASSPORT_RE.search(line) or LOOSE_ID_RE.search(line))

        row = _extract_row(page_no, line, fallback_name=prev_candidate_name)
        if row is not None:
            rows.append(row)

        if has_own_id or not stripped:
            prev_candidate_name = ""
        else:
            # a bare name line (no identifier of its own) may be a wrapped
            # name belonging to the row immediately below it
            prev_candidate_name = stripped

    return PageParseResult(page_no=page_no, rows=rows, index_marker_count=index_count, row_count=len(rows))
