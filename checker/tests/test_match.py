"""Name-matching regression tests.

token_set_ratio was replaced with token_sort_ratio after a live backfill run
surfaced real false positives: common short Myanmar name bases ("KAUNG
HTET") matching against unrelated longer names that happen to contain those
same words ("KAUNG HTET KYAW", "KAUNG HTET OO") as if they were OCR
variants of the same person. token_set_ratio scores a subset-of-words match
as a perfect 100 regardless of extra words; token_sort_ratio penalizes the
length difference instead, which is what we actually want here.
"""
from checker.match import WatchlistEntry, match_row
from checker.parse import Row


def _row(name, passport="ZZ000000"):
    return Row(page_no=1, name=name, passport_no=passport, id_kind="passport",
               approved_date="", remark="", raw_line="")


def test_short_name_does_not_match_a_longer_different_person():
    entry = WatchlistEntry(id=1, full_name="Kaung Htet", passport_no="MG459920")
    for different_person in ["KAUNG HTET KYAW", "KAUNG HTET OO", "KAUNG HTET AUNG"]:
        row = _row(different_person, passport="MX111111")  # different passport too
        assert match_row(entry, row) is None, f"false positive against {different_person}"


def test_missing_first_name_does_not_match():
    entry = WatchlistEntry(id=1, full_name="Yoon Shwe Zin Khaing", passport_no="MG165840")
    row = _row("SHWE ZIN KHAING", passport="MX222222")
    assert match_row(entry, row) is None


def test_overlapping_fragment_does_not_match():
    entry = WatchlistEntry(id=1, full_name="Yoon Shwe Zin Khaing", passport_no="MG165840")
    row = _row("ZIN ZIN KHAING", passport="MX333333")
    assert match_row(entry, row) is None


def test_genuine_ocr_typo_still_matches():
    entry = WatchlistEntry(id=1, full_name="Nay Linn Aung", passport_no="MF123456")
    row = _row("NAY LIN AUNG", passport="MF123456")  # same passport, OCR dropped a letter
    m = match_row(entry, row)
    assert m is not None
    assert m.confidence == "high"


def test_passport_only_match_is_not_reported():
    """Policy: both name and passport must match -- a passport hit alone
    (e.g. a data-entry error, or someone else entirely) is not alerted on."""
    entry = WatchlistEntry(id=1, full_name="Kaung Htet", passport_no="MF123456")
    row = _row("COMPLETELY DIFFERENT PERSON", passport="MF123456")
    assert match_row(entry, row) is None


def test_name_only_match_is_not_reported():
    """Policy: a name hit alone (even an exact one -- two different people
    can share a name) is not alerted on without a confirming passport match."""
    entry = WatchlistEntry(id=1, full_name="Kaung Htet", passport_no="MF123456")
    row = _row("KAUNG HTET", passport="ZZ999999")
    assert match_row(entry, row) is None
