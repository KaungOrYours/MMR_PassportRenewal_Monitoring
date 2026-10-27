"""Tests for the PV/PJ renewal-list parser and masked-passport matching.

Uses synthetic text matching the real table structure rather than real
channel images/fixtures -- the channel's actual content is other people's
names and passport fragments, which doesn't belong in a public repo.
"""
from checker.match import WatchlistEntry, masked_passport_matches, match_renewal_row
from checker.parse_renewal import parse_renewal_page

SAMPLE_PAGE = """PV to PJ passport validity extension list
28-10-2026 date - appointment notice

No   Name                   Passport No.   Current   New
61   NYAN LIN HTET          MG 77**48      PV        PJ
62   ZIN MAR AYE MYINT      MG 19**26      PV        PJ
63   AYE THET WIN           MG 28**73      PV        PJ
64   ZIN KYU HNIN           MF 59**44      PV        PT
"""


def test_renewal_rows_parsed_with_no_gap():
    result = parse_renewal_page(1, SAMPLE_PAGE)
    assert result.row_count == 4
    assert not result.has_gap
    names = {r.name: r.masked_passport for r in result.rows}
    assert names["NYAN LIN HTET"] == "MG77**48"
    assert names["ZIN KYU HNIN"] == "MF59**44"


def test_renewal_row_captures_type_change_and_date():
    result = parse_renewal_page(1, SAMPLE_PAGE)
    row = next(r for r in result.rows if r.name == "ZIN KYU HNIN")
    assert row.current_type == "PV"
    assert row.new_type == "PT"
    assert row.appointment_date == "28-10-2026"


def test_integrity_gap_detected_when_a_row_is_unreadable():
    # index marker "62" survives OCR but the rest of the line is garbled
    # beyond recognition -- the row itself is lost, not the whole line
    broken = SAMPLE_PAGE.replace(
        "62   ZIN MAR AYE MYINT      MG 19**26      PV        PJ\n",
        "62   ZIN MAR AYE MYINT      unreadable-id      PV        PJ\n",
    )
    result = parse_renewal_page(1, broken)
    assert result.row_count == 3
    assert result.has_gap  # 4 index markers (61-64) but only 3 rows recovered


def test_masked_passport_matches_known_visible_digits():
    assert masked_passport_matches("MG771548", "MG77**48")
    assert not masked_passport_matches("MG991548", "MG77**48")  # prefix mismatch
    assert not masked_passport_matches("MG771599", "MG77**48")  # suffix mismatch


def test_masked_passport_ignores_redacted_middle_digits():
    # the two middle digits are inherently unrecoverable from a masked list --
    # this is expected behavior, not a false positive
    assert masked_passport_matches("MG771148", "MG77**48")
    assert masked_passport_matches("MG779948", "MG77**48")


def test_full_renewal_match_is_high_confidence():
    result = parse_renewal_page(1, SAMPLE_PAGE)
    row = next(r for r in result.rows if r.name == "NYAN LIN HTET")
    entry = WatchlistEntry(id=1, full_name="Nyan Lin Htet", passport_no="MG771548")
    m = match_renewal_row(entry, row)
    assert m is not None
    assert m.confidence == "high"


def test_unrelated_entry_does_not_match_renewal_row():
    result = parse_renewal_page(1, SAMPLE_PAGE)
    row = next(r for r in result.rows if r.name == "NYAN LIN HTET")
    entry = WatchlistEntry(id=1, full_name="Completely Different Person", passport_no="ZZ999999")
    assert match_renewal_row(entry, row) is None


def test_renewal_passport_match_alone_is_sufficient():
    """Passport number is authoritative -- see test_match.py for why."""
    result = parse_renewal_page(1, SAMPLE_PAGE)
    row = next(r for r in result.rows if r.name == "NYAN LIN HTET")
    entry = WatchlistEntry(id=1, full_name="Completely Different Person", passport_no="MG771548")
    m = match_renewal_row(entry, row)
    assert m is not None
    assert m.matched_on == "passport"


def test_renewal_name_only_match_is_not_reported():
    result = parse_renewal_page(1, SAMPLE_PAGE)
    row = next(r for r in result.rows if r.name == "NYAN LIN HTET")
    entry = WatchlistEntry(id=1, full_name="Nyan Lin Htet", passport_no="ZZ999999")
    assert match_renewal_row(entry, row) is None
