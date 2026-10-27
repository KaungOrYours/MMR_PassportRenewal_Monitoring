"""Golden-file tests against the two real sample PDFs the embassy has published.

These fixtures live in ~/Downloads because that is where the user saved them;
if they are absent (e.g. a fresh clone / CI), the tests are skipped rather
than failing the build.
"""
from pathlib import Path

import pytest

from checker.extract import extract_pdf
from checker.match import WatchlistEntry, match_row
from checker.parse import Row, parse_page

TEXT_PDF = Path("~/Downloads/PassportLost&Seaman_offshore_Approved-List.pdf").expanduser()
SCAN_PDF = Path("~/Downloads/PassportLost&SeamanOffshoreApprovedList.pdf").expanduser()

requires_text_pdf = pytest.mark.skipif(not TEXT_PDF.exists(), reason="sample text-layer PDF not present")
requires_scan_pdf = pytest.mark.skipif(not SCAN_PDF.exists(), reason="sample scanned PDF not present")


@requires_text_pdf
def test_text_layer_pdf_parses_with_no_gaps():
    pages, mode = extract_pdf(TEXT_PDF)
    assert mode == "text"
    assert len(pages) == 23

    total_rows = 0
    for page in pages:
        result = parse_page(page.page_no, page.text)
        assert not result.has_gap, f"page {page.page_no}: rows={result.row_count} markers={result.index_marker_count}"
        total_rows += result.row_count

    assert total_rows >= 400  # observed 422 at authoring time


@requires_scan_pdf
def test_scanned_pdf_ocr_parses_with_no_gaps():
    pages, mode = extract_pdf(SCAN_PDF)
    assert mode == "ocr"
    assert len(pages) == 6

    total_rows = 0
    unresolved_gaps = 0
    for page in pages:
        result = parse_page(page.page_no, page.text)
        if result.has_gap:
            unresolved_gaps += 1
        total_rows += result.row_count

    assert unresolved_gaps == 0, "OCR'd pages should have zero unresolved integrity gaps"
    assert total_rows >= 60  # observed 66 at authoring time


@requires_scan_pdf
def test_known_real_entry_is_recovered():
    """SAW SANDAR KYWE / MI071187 is a real row on page 3 of the live scan."""
    pages, _mode = extract_pdf(SCAN_PDF)
    page3 = next(p for p in pages if p.page_no == 3)
    result = parse_page(3, page3.text)
    names = {row.name: row.passport_no for row in result.rows}
    assert names.get("SAW SANDAR KYWE") == "MI071187"


def test_ocr_slip_name_still_matches_via_fuzzy():
    """MOE EI SAN (watchlist) should match an OCR'd 'MOE EL SAN' (I misread as L)."""
    row = Row(page_no=3, name="MOE EL SAN", passport_no="MF989672", id_kind="passport",
              approved_date="", remark="", raw_line="")
    entry = WatchlistEntry(id=1, full_name="MOE EI SAN", passport_no="MF989672")
    m = match_row(entry, row)
    assert m is not None
    assert m.confidence == "high"


def test_word_split_name_still_matches():
    """MA JI SENG GAM (watchlist) should match OCR's 'MAJISENG GAM' (lost spaces)."""
    row = Row(page_no=3, name="MAJISENG GAM", passport_no="MJ620846", id_kind="passport",
              approved_date="", remark="", raw_line="")
    entry = WatchlistEntry(id=1, full_name="MA JI SENG GAM", passport_no="MJ620846")
    m = match_row(entry, row)
    assert m is not None
    assert m.confidence == "high"


def test_unrelated_entry_does_not_match():
    row = Row(page_no=3, name="RANDOM PERSON", passport_no="MX999999", id_kind="passport",
              approved_date="", remark="", raw_line="")
    entry = WatchlistEntry(id=1, full_name="Saw Sandar Kywe", passport_no="MI071187")
    assert match_row(entry, row) is None


def test_seaman_book_identifier_is_parsed_not_dropped():
    result = parse_page(1, "1.   HAN SHEIN   CDC3363   12-10-2018   remark")
    assert result.row_count == 1
    assert result.rows[0].id_kind == "other"
    assert result.rows[0].passport_no == "CDC3363"


def test_wrapped_name_line_is_recovered():
    text = "     NAW SAY RER MU\n2.                          MD187179           17-9-2019       remark"
    result = parse_page(1, text)
    assert result.row_count == 1
    assert result.rows[0].name == "NAW SAY RER MU"
    assert result.rows[0].passport_no == "MD187179"
