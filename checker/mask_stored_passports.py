"""One-time cleanup: masks full passport numbers already stored in the database.

Covers list rows' identifier, name and remark, and each match's dedup key. Prints
counts only, and changes nothing unless --apply is given. Applying can't be undone,
so run it only after the checker code that stores masked numbers is live.

Two matches for one person can become identical once masked, for example when a new
list arrived between deployment and this cleanup. They are merged, and the merged
match counts as delivered if either one was, so nobody is alerted twice.

Usage:
    python -m checker.mask_stored_passports           # report only
    python -m checker.mask_stored_passports --apply   # change the rows
"""
import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from . import db
from .crash_report import install_excepthook
from .masking import mask_identifier, scrub_identifiers


@dataclass
class Plan:
    entries: list[tuple[db.Entry, str, str, str | None]] = field(default_factory=list)
    matches: list[tuple[db.MatchRecord, str]] = field(default_factory=list)
    merged_away: list[db.MatchRecord] = field(default_factory=list)
    delivered_from_merge: list[tuple[db.MatchRecord, object]] = field(default_factory=list)


def plan(session) -> Plan:
    result = Plan()

    for entry in session.query(db.Entry).filter(db.Entry.id_kind != "masked_passport"):
        passport, name, remark = (
            mask_identifier(entry.passport_no), scrub_identifiers(entry.name), scrub_identifiers(entry.remark),
        )
        if (passport, name, remark) != (entry.passport_no, entry.name, entry.remark):
            result.entries.append((entry, passport, name, remark))

    groups = defaultdict(list)
    for match in session.query(db.MatchRecord).order_by(db.MatchRecord.id):
        groups[match.watchlist_id, mask_identifier(match.passport_canonical)].append(match)

    for (_watchlist_id, masked), group in groups.items():
        keep, *others = group
        result.merged_away.extend(others)
        delivered = next((m.notified_at for m in group if m.notified_at is not None), None)
        if keep.notified_at is None and delivered is not None:
            result.delivered_from_merge.append((keep, delivered))
        if keep.passport_canonical != masked:
            result.matches.append((keep, masked))
    return result


def apply_plan(session, p: Plan) -> None:
    """One transaction. Merged rows go first, because a masked key would otherwise
    collide with a row still waiting to be deleted."""
    for match in p.merged_away:
        session.delete(match)
    session.flush()
    for match, notified_at in p.delivered_from_merge:
        match.notified_at = notified_at
    for match, masked in p.matches:
        match.passport_canonical = masked
    for entry, passport, name, remark in p.entries:
        entry.passport_no, entry.name, entry.remark = passport, name, remark
    session.commit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="change the rows; can't be undone")
    args = parser.parse_args(argv)

    session = db.get_session()
    p = plan(session)
    print(f"list rows to mask: {len(p.entries)}")
    print(f"matches to mask: {len(p.matches)}")
    print(f"matches to merge away: {len(p.merged_away)}")

    if not args.apply:
        print("Report only. Nothing was changed.")
        return 0

    apply_plan(session, p)
    print("Applied.")
    return 0


if __name__ == "__main__":
    install_excepthook()
    sys.exit(main())
