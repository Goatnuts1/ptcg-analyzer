#!/usr/bin/env python3
"""
test_greninja.py — Mega Greninja ex (me4-22): Mortal Shuriken + Ninja Spinner.

Run from project root:  python3 tests/test_greninja.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def expected_dmg(attacker, defender, raw):
    if raw <= 0:
        return 0
    if attacker.types and defender.types:
        for w, _ in defender.weaknesses:
            if w == attacker.types[0]:
                return raw * 2
    return raw


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    GRN = db.get("Mega Greninja ex")
    WATER = db.get("Basic Water Energy")
    DREEPY = db.get("Dreepy")

    # --- Mortal Shuriken: discard a Basic Water from hand, snipe 60 onto a KO target ---
    st, a, b = fresh(db)
    grn = InPlayPokemon(card=GRN)
    a.active = grn
    a.hand = [WATER]
    b.active = InPlayPokemon(card=DREEPY)                 # 70 HP, full — not a KO target
    snipe = InPlayPokemon(card=db.get("Froakie"), damage=10)  # 60 HP, 50 left -> KO by 60
    b.bench = [snipe]
    fx._mortal_shuriken(ctx(st, a, b, source=grn))
    check(WATER in a.discard and not a.hand, "Mortal Shuriken discards a Basic Water from hand")
    check(snipe.damage == 70, f"Mortal Shuriken snipes 60 onto the KO target (got {snipe.damage})")
    check(b.active.damage == 0, "the snipe hit the bench KO target, not the Active")

    # --- Mortal Shuriken with no KO available -> 60 onto the Active ---
    st, a, b = fresh(db)
    grn = InPlayPokemon(card=GRN)
    a.active = grn
    a.hand = [WATER]
    b.active = InPlayPokemon(card=DREEPY)
    fx._mortal_shuriken(ctx(st, a, b, source=grn))
    check(b.active.damage == 60, f"Mortal Shuriken hits the Active for 60 when no KO (got {b.active.damage})")

    # --- can_use gate: no Basic Water in hand -> not usable ---
    gate = fx.get_ability_can_use("Mega Greninja ex", "Mortal Shuriken")
    st, a, b = fresh(db)
    grn = InPlayPokemon(card=GRN)
    a.active = grn
    b.active = InPlayPokemon(card=DREEPY)
    a.hand = []                                           # no water
    check(gate is not None and not gate(st, a, grn), "Mortal Shuriken needs a Water in hand")
    a.hand = [WATER]
    check(gate(st, a, grn), "Mortal Shuriken usable with a Water in hand + Active")

    # --- Ninja Spinner: 3 Energy -> return 1 Water to hand for +80 (= 200) ---
    st, a, b = fresh(db)
    grn = InPlayPokemon(card=GRN, energy=[WATER, WATER, WATER])
    a.active = grn
    d = InPlayPokemon(card=DREEPY)
    b.active = d
    fx._ninja_spinner(ctx(st, a, b, source=grn))
    check(len(grn.energy) == 2 and WATER in a.hand,
          f"Ninja Spinner returns a Water to hand (energy left {len(grn.energy)})")
    check(d.damage == expected_dmg(GRN, DREEPY, 200), f"Ninja Spinner does 200 with the boost (got {d.damage})")

    # --- Ninja Spinner: only 2 Energy -> keep them, plain 120 ---
    st, a, b = fresh(db)
    grn = InPlayPokemon(card=GRN, energy=[WATER, WATER])
    a.active = grn
    d = InPlayPokemon(card=DREEPY)
    b.active = d
    fx._ninja_spinner(ctx(st, a, b, source=grn))
    check(len(grn.energy) == 2 and not a.hand, "Ninja Spinner keeps Energy when only 2 attached")
    check(d.damage == expected_dmg(GRN, DREEPY, 120), f"Ninja Spinner does 120 without the boost (got {d.damage})")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Mega Greninja ex: Mortal Shuriken (discard Water -> snipe 60, KO-targeted) "
          "and Ninja Spinner (120, or 200 returning a Water) match card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
