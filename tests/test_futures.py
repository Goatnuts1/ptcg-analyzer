#!/usr/bin/env python3
"""test_futures.py — the future-proof report (src/analysis/futures.py).
Run: python3 tests/test_futures.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.engine.decks import DECKS
from src.analysis.futures import rotation_risk, trend_risk, futures_report, _load_pool

fails = 0
def check(c, m):
    global fails
    print(("  ok  " if c else "  FAIL") + " " + m)
    if not c: fails += 1

pool = _load_pool("data/standard_pool.json")

# rotation risk is arithmetic on printed marks — verify against a hand count
rot, cards = rotation_risk(DECKS["mega_excadrill"], pool)
hand = sum(q for n, q in DECKS["mega_excadrill"]
           if pool.get(n, {}).get("regulationMark") == "H")
check(abs(rot - 100.0 * hand / 60) < 1e-9, f"mega_excadrill rotation% matches hand count ({rot:.1f}%)")
check(all(pool[n]["regulationMark"] == "H" for n, _ in cards), "every listed card is mark H")

# Basic Energy never rotates (no mark)
rot_e, _ = rotation_risk([("Basic Metal Energy", 60)], pool)
check(rot_e == 0.0, "Basic Energy contributes zero rotation risk")

# trend risk: only RISING archetypes with a sub-50 matchup contribute
import json
matrix = json.load(open("docs/matrix_2026-08_mcts2.json"))
tr, contrib = trend_risk("mega_excadrill", matrix)
check(all(wr < 50 for _, _, wr in contrib), "only sub-50% matchups contribute")
check(tr >= 0, "trend risk is non-negative")

# the report renders, contains the speculation firewall line, and never scores flags
rep = futures_report({"mega_excadrill": DECKS["mega_excadrill"]},
                     "data/standard_pool.json", "docs/matrix_2026-08_mcts2.json")
check("SPECULATION" in rep and "flags are SPECULATION, never scored" in rep,
      "speculation firewall is stated in the report itself")
check("Mega Rayquaza ex" in rep, "upcoming-set flags render")

print("\n" + ("ALL PASS" if not fails else f"{fails} FAILURES"))
sys.exit(1 if fails else 0)
