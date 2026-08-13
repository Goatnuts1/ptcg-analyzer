#!/usr/bin/env python3
"""
test_first_player_override.py — setup_game(first_player=...) deterministically
forces who goes first, without disturbing the default (None = real coin flip)
behavior other tests already depend on.

Run: python3 tests/test_first_player_override.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import DECKS, _expand
from src.engine.game import setup_game


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    deck_a = _expand(db, DECKS["the_vault"])
    deck_b = _expand(db, DECKS["dragapult"])

    # --- forced first_player=0 always wins the "coin flip", across many seeds ---
    for seed in range(30):
        st = setup_game(deck_a, deck_b, seed=seed, first_player=0)
        check(st.active_index == 0, f"seed={seed}: expected active_index=0, got {st.active_index}")

    # --- forced first_player=1 always wins, across many seeds ---
    for seed in range(30):
        st = setup_game(deck_a, deck_b, seed=seed, first_player=1)
        check(st.active_index == 1, f"seed={seed}: expected active_index=1, got {st.active_index}")

    # --- default (first_player=None) must still be a genuine coin flip: both
    # outcomes appear across enough seeds (not silently pinned to one value). ---
    outcomes = {setup_game(deck_a, deck_b, seed=seed).active_index for seed in range(30)}
    check(outcomes == {0, 1}, f"default coin flip should hit both 0 and 1 across 30 seeds, got {outcomes}")

    # --- same seed, same first_player -> byte-identical setup (deck order, hands) ---
    st1 = setup_game(deck_a, deck_b, seed=7, first_player=1)
    st2 = setup_game(deck_a, deck_b, seed=7, first_player=1)
    check([c.name for c in st1.players[0].hand] == [c.name for c in st2.players[0].hand],
          "same seed + first_player must reproduce an identical opening hand")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_first_player_override.py: all checks passed")


if __name__ == "__main__":
    main()
