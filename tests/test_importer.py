#!/usr/bin/env python3
"""
test_importer.py — the TCG Live deck importer (src/importers/tcglive.py).

Asserts the parser/matcher handles real export quirks: set codes, bare lines, the
"4x" quantity form, section/total headers, energy naming, accent-insensitive
matching, missing cards, split-line merging, and the JSON save round-trip.

Run from project root:  python3 tests/test_importer.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.importers import tcglive

POOL = "data/standard_pool.json"

SAMPLE = """\
Pokémon: 11
3 Mega Gardevoir ex MEG 50
4 Ralts SVI 84
2 Kirlia SVI 85
2 Pidgeot ex OBF 164

Trainer: 4
4x Ultra Ball SVI 196
2 Pokegear 3.0 SVI 186
1 Boss's Orders

Energy: 12
8 Psychic Energy SVE 5
4 Basic Fire Energy

# a stray comment and a junk line
this is not a card line
Total Cards: 60
"""


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool(POOL)
    res = tcglive.import_deck(SAMPLE, db)
    rec = dict(res.recipe)

    # quantities total across all parsed CARD lines (headers/comments/junk excluded)
    check(res.total == 3 + 4 + 2 + 2 + 4 + 2 + 1 + 8 + 4,
          f"total parsed should be 30 (got {res.total})")

    # set codes stripped + matched
    check(rec.get("Mega Gardevoir ex") == 3, "3 Mega Gardevoir ex (set code stripped)")
    check(rec.get("Ralts") == 4 and rec.get("Kirlia") == 2, "Ralts/Kirlia matched")

    # "4x" quantity form + bare line (no set code)
    check(rec.get("Ultra Ball") == 4, "'4x Ultra Ball' parsed")
    check(rec.get("Boss's Orders") == 1, "bare 'Boss's Orders' (no set code) matched")

    # accent-insensitive matching: 'Pokegear 3.0' -> 'Pokégear 3.0'
    check(rec.get("Pokégear 3.0") == 2, "accent-insensitive match for Pokégear 3.0")

    # energy normalisation
    check(rec.get("Basic Psychic Energy") == 8, "'Psychic Energy' -> Basic Psychic Energy")
    check(rec.get("Basic Fire Energy") == 4, "'Basic Fire Energy' matched")

    # a rotated card is reported missing, not silently dropped
    check(("Pidgeot ex", 2) in res.missing, "Pidgeot ex reported missing")
    check(res.matched_total == res.total - 2, "matched_total excludes the 2 missing")

    # the junk line becomes a warning (not a crash)
    check(any("not a card" in w for w in res.warnings), "junk line recorded as a warning")

    # by_type counts (matched only)
    check(res.by_type.get("Pokémon") == 3 + 4 + 2, "Pokémon count")
    check(res.by_type.get("Energy") == 12, "Energy count")

    # split-line merge: same card across two lines sums
    res2 = tcglive.import_deck("2 Ralts SVI 84\n2 Ralts PAF 84\n", db)
    check(dict(res2.recipe).get("Ralts") == 4, "split lines for the same card merge to 4")

    # save round-trip
    path = tcglive.save_deck(res, "_test_import_tmp", out_dir="/tmp/_imp_test")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        check(data["recipe"] == [[n, q] for n, q in res.recipe], "JSON recipe round-trips")
        check(data["missing"] == [["Pidgeot ex", 2]], "JSON records missing cards")
        check(data["source"] == "tcglive", "JSON tags the source")
    finally:
        if os.path.exists(path):
            os.remove(path)

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — TCG Live importer: parses set codes / bare lines / 4x / headers, "
          "normalises energy, matches accent-insensitively, reports missing, merges "
          "split lines, and round-trips to JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
