#!/usr/bin/env python3
"""
test_legality.py — the format / rotation framework (engine/legality.py).

Two jobs:
  1. Guard: both registered tournament lists must be legal in the CURRENT format.
     If a future rotation makes one illegal, this fails loudly and names the cards.
  2. Prove the framework works: validate_deck catches each construction violation,
     and a simulated rotation (shrinking the legal-mark set) flags the now-illegal
     cards — that's the whole point of making rotation a one-line change.

Run from project root:  python3 tests/test_legality.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import TOURNAMENT_LISTS
from src.engine.legality import (STANDARD_LEGAL_MARKS, validate_deck, is_deck_legal,
                                  DECK_SIZE)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 1. Guard: registered tournament lists are legal NOW. ---
    for name, recipe in TOURNAMENT_LISTS.items():
        v = validate_deck(db, recipe)
        check(v == [], f"{name} should be legal, but: {v}")

    # --- 2a. 4-copy rule (Basic Energy exempt). ---
    too_many = [("Ultra Ball", 5), ("Basic Fire Energy", 55)]   # 60 cards, 5 Ultra Ball
    v = validate_deck(db, too_many)
    check(any("Ultra Ball" in x and "5 copies" in x for x in v),
          f"5x Ultra Ball should violate the 4-copy rule: {v}")
    # 30 of a basic energy must be fine on the copy rule
    energy_ok = [("Basic Fire Energy", 30), ("Basic Water Energy", 30)]
    v = validate_deck(db, energy_ok)
    check(not any("copies" in x for x in v),
          f"basic energy should be exempt from the 4-copy rule: {v}")

    # --- 2b. 1-ACE-SPEC rule. (Unfair Stamp + Enriching Energy are both ACE SPEC.) ---
    two_ace = [("Unfair Stamp", 1), ("Enriching Energy", 1), ("Basic Fire Energy", 58)]
    v = validate_deck(db, two_ace)
    check(any("ACE SPEC" in x for x in v), f"2 ACE SPEC cards should violate: {v}")

    # --- 2c. deck size. ---
    v = validate_deck(db, [("Basic Fire Energy", 59)])
    check(any("59 cards" in x for x in v), f"59-card deck should violate size: {v}")

    # --- 2d. unknown card. ---
    v = validate_deck(db, [("Totally Not A Card", 60)])
    check(any("not in the card pool" in x for x in v), f"unknown card should violate: {v}")

    # --- 3. ROTATION SIMULATION: shrink the legal marks and confirm detection. ---
    # The Dragapult list has mark-I and mark-J cards (e.g. Lillie's Determination = I,
    # Crushing Hammer = J). Pretend only H is legal: those must be flagged.
    drag = TOURNAMENT_LISTS["dragapult"]
    check(is_deck_legal(db, drag, STANDARD_LEGAL_MARKS),
          "dragapult should be legal under the real format")
    v_rot = validate_deck(db, drag, legal_marks=frozenset({"H"}))
    check(any("not legal" in x for x in v_rot),
          "shrinking legal marks to {H} should flag the I/J cards (rotation detection)")
    # sanity: at least one specific known-non-H card is named
    flagged = " ".join(v_rot)
    check("Lillie's Determination" in flagged or "Crushing Hammer" in flagged
          or "Boss's Orders" in flagged,
          f"rotation should name the now-illegal cards: {v_rot[:3]}")

    # --- 4. self-check: the canonical mark set is the expected current one. ---
    check(STANDARD_LEGAL_MARKS == frozenset({"H", "I", "J"}),
          f"current Standard marks drifted: {sorted(STANDARD_LEGAL_MARKS)}")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print(f"OK — both tournament lists legal under marks {sorted(STANDARD_LEGAL_MARKS)}; "
          "construction rules + rotation detection all hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
