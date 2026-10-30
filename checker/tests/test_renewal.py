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


def test_integrity_gap_detected_on_total_ocr_failure():
    # a page OCR fails to read entirely -- no index markers, no rows. This
    # must still flag has_gap (not look identical to a genuinely empty
    # page), since every real table page has multiple rows.
    result = parse_renewal_page(1, "garbled unreadable noise\nwith no table structure at all")
    assert result.row_count == 0
    assert result.index_marker_count == 0
    assert result.has_gap


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


def test_renewal_passport_match_alone_is_not_sufficient():
    """Unlike the embassy PDF path (test_match.py), a masked-passport match
    alone is NOT enough here -- the hidden 2 digits mean a different real
    person could coincidentally share the same visible digits, and the
    name is the only way to tell them apart from this source."""
    result = parse_renewal_page(1, SAMPLE_PAGE)
    row = next(r for r in result.rows if r.name == "NYAN LIN HTET")
    entry = WatchlistEntry(id=1, full_name="Completely Different Person", passport_no="MG771548")
    assert match_renewal_row(entry, row) is None


def test_renewal_name_only_match_is_not_reported():
    result = parse_renewal_page(1, SAMPLE_PAGE)
    row = next(r for r in result.rows if r.name == "NYAN LIN HTET")
    entry = WatchlistEntry(id=1, full_name="Nyan Lin Htet", passport_no="ZZ999999")
    assert match_renewal_row(entry, row) is None


# The @mesg15 lists are photos of a *bordered* table, and the border is what
# breaks OCR in ways the clean-text sample above never shows. Every case below
# was observed in a real post that the checker silently mis-parsed.

BORDERED_PAGE = """PV to PJ passport validity extension list
6-11-2026 date - appointment notice

91 |MI KAY THI AUNG        MG 18**23   PV   PJ
92 |SU MON                 MG 22**99   Pv   PJ
93 |{LU SENG               MF 82**57   PV   PJ
94 |MOE NYUNT 00           MG 08**54   PV   PJ
95 |ZWE HTET NAING         MHO01**98   PV   PJ
96 |NAY WUNN LETT          MG 07°*56   PV   PT
"""


def test_bordered_table_rows_all_parse():
    result = parse_renewal_page(1, BORDERED_PAGE)
    assert result.row_count == 6
    assert result.index_numbers == [91, 92, 93, 94, 95, 96]
    assert result.missing_indexes == []
    assert not result.has_gap


def test_mangled_mask_and_spliced_letter_still_canonicalize():
    """OCR renders "*" as "°" and splices an "O" into the digits; demanding a
    literal "AA 99**99" dropped both rows outright."""
    rows = {r.name: r.masked_passport for r in parse_renewal_page(1, BORDERED_PAGE).rows}
    assert rows["ZWE HTET NAING"] == "MH01**98"   # from "MHO01**98"
    assert rows["NAY WUNN LETT"] == "MG07**56"    # from "MG 07°*56"


def test_table_border_is_stripped_from_the_name():
    rows = [r.name for r in parse_renewal_page(1, BORDERED_PAGE).rows]
    assert "LU SENG" in rows                      # not "{LU SENG"


def test_lowercase_type_code_is_still_read():
    """"PV" comes back as "Pv" often enough that a case-sensitive match left
    the alert saying "PJ -> ?" instead of "PV -> PJ"."""
    row = next(r for r in parse_renewal_page(1, BORDERED_PAGE).rows if r.name == "SU MON")
    assert (row.current_type, row.new_type) == ("PV", "PJ")


def test_a_hole_in_the_row_numbers_is_detected():
    """The row-count-vs-index-marker check is blind on a bordered table
    (INDEX_RE counts ~0 because the number is glued to the border), so a lost
    row has to be caught by the gap in the list's own numbering."""
    page = BORDERED_PAGE.replace("94 |MOE NYUNT 00           MG 08**54   PV   PJ\n", "")
    result = parse_renewal_page(1, page)
    assert result.row_count == 5
    assert result.missing_indexes == [94]
    assert result.has_gap


def test_ocr_digits_in_a_name_do_not_break_the_match():
    from checker.match import names_plausibly_match
    assert names_plausibly_match("MOE NYUNT OO", "MOE NYUNT 00")[0]
    assert names_plausibly_match("THANT ZIN AUNG", "/THANT ZIN AUNG")[0]
    assert names_plausibly_match("NAW THART WAH HTOO", "{NAW THART WAH HTOO")[0]


def test_loosened_name_normalization_still_rejects_a_different_person():
    """Regression guard: the fixes above must not reopen the false-positive
    token_set_ratio was dropped for -- an extra name word is a different
    person, not an OCR variant."""
    from checker.match import names_plausibly_match
    assert not names_plausibly_match("KAUNG HTET", "KAUNG HTET KYAW")[0]
    assert not names_plausibly_match("KAUNG HTET KYAW", "{KAUNG HTET")[0]
    assert not names_plausibly_match("MIN TUN", "MIN TUN AUNG")[0]
    assert not names_plausibly_match("THANT ZIN AUNG", "THANT ZIN PHYO")[0]
