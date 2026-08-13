#!/usr/bin/env python3
"""
test_prism_energy.py — Prism Energy's real text: "As long as this card is
attached to a Pokémon, it provides Colorless Energy. If this card is attached
to a Basic Pokémon, this card provides every type of Energy but provides only
1 Energy at a time." Confirmed missing this session — Wellspring Mask Ogerpon
ex's Torrential Pump, Pecharunt's Poison Chain, and Chi-Yu's Ground Melter were
all silently uncastable in the ogerpon_box deck because Prism Energy fell back
to fixed Colorless regardless of host.

Run: python3 tests/test_prism_energy.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import InPlayPokemon
from src.engine.game import can_pay_cost


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    prism = db.get("Prism Energy")

    # --- 1. On a Basic (Wellspring Mask Ogerpon ex): wildcard, can pay a typed cost ---
    wellspring = InPlayPokemon(card=db.get("Wellspring Mask Ogerpon ex"))
    check(wellspring.card.is_basic, "setup: Wellspring Mask Ogerpon ex must be Basic")
    wellspring.energy = [prism, db.get("Basic Grass Energy"), db.get("Basic Grass Energy")]
    check(can_pay_cost(wellspring, ("Water", "Colorless", "Colorless")),
          "Prism on a Basic must satisfy a Water typed requirement (Torrential Pump's real cost)")

    # --- 2. Only ONE energy at a time — 2 Prism can't satisfy 2 DIFFERENT typed
    # symbols simultaneously if there's nothing else to cover the rest. ---
    wellspring2 = InPlayPokemon(card=db.get("Wellspring Mask Ogerpon ex"))
    wellspring2.energy = [prism]
    check(not can_pay_cost(wellspring2, ("Water", "Fire")),
          "a single Prism unit must not satisfy two typed symbols at once")
    check(can_pay_cost(wellspring2, ("Water",)),
          "a single Prism unit alone must satisfy one typed symbol")

    # --- 3. On a NON-Basic host: falls back to plain Colorless (the "as long as
    # attached to a Pokémon" baseline clause), NOT a wildcard. ---
    crustle = InPlayPokemon(card=db.get("Crustle"))   # Stage 1, not Basic
    check(not crustle.card.is_basic, "setup: Crustle must not be Basic")
    crustle.energy = [prism, prism]
    check(not can_pay_cost(crustle, ("Grass", "Colorless")),
          "Prism on a non-Basic must NOT act as a wildcard for a typed Grass requirement")
    check(can_pay_cost(crustle, ("Colorless", "Colorless")),
          "Prism on a non-Basic must still pay plain Colorless costs")

    # --- 4. Unused wildcard still counts toward a Colorless requirement (a
    # leftover "Any" token is just as good as any other attached energy). ---
    wellspring3 = InPlayPokemon(card=db.get("Wellspring Mask Ogerpon ex"))
    wellspring3.energy = [prism, db.get("Basic Water Energy")]
    check(can_pay_cost(wellspring3, ("Water", "Colorless")),
          "an unused Prism wildcard must still count toward a trailing Colorless requirement")

    # --- 5. The real, previously-blocked attack: Torrential Pump [Water, Colorless, Colorless] ---
    wellspring4 = InPlayPokemon(card=db.get("Wellspring Mask Ogerpon ex"))
    atk = next(a for a in wellspring4.card.attacks if a.name == "Torrential Pump")
    wellspring4.energy = [prism, db.get("Basic Grass Energy"), db.get("Basic Grass Energy")]
    check(can_pay_cost(wellspring4, atk.cost),
          f"Torrential Pump (cost {atk.cost}) must now be payable with 1 Prism + 2 Grass on a Basic")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_prism_energy.py: all checks passed")


if __name__ == "__main__":
    main()
