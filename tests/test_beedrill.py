#!/usr/bin/env python3
"""
test_beedrill.py — Beedrill ex (Rumbling Bees swarm) + Weedle (Surprise Attack).

Run from project root:  python3 tests/test_beedrill.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh(db):
    a = PlayerState(name="A"); b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0)); st.db = db; st.turn_number = 5
    return st, a, b


def ctx(st, me, opp, source=None, rng=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=rng or st.rng)


class _Coin:
    def __init__(self, heads): self._v = 1 if heads else 0
    def randint(self, a, b): return self._v
    def random(self): return 0.0
    def shuffle(self, s): pass


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
    BEE = db.get("Beedrill ex")
    DREEPY = db.get("Dreepy")        # not Fire-weak, so no Beedrill-weakness doubling

    # --- Rumbling Bees scales 110 per Beedrill in play ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=BEE)
    a.active = src
    b.active = InPlayPokemon(card=DREEPY)
    fx._rumbling_bees(ctx(st, a, b, source=src))
    check(b.active.damage == expected_dmg(BEE, DREEPY, 110), f"1 Beedrill -> 110 (got {b.active.damage})")

    st, a, b = fresh(db)
    src = InPlayPokemon(card=BEE)
    a.active = src
    a.bench = [InPlayPokemon(card=BEE)]      # a second Beedrill in play
    b.active = InPlayPokemon(card=DREEPY)
    fx._rumbling_bees(ctx(st, a, b, source=src))
    check(b.active.damage == expected_dmg(BEE, DREEPY, 220), f"2 Beedrill -> 220 (got {b.active.damage})")

    # --- Surprise Attack: 30 on heads, 0 on tails ---
    st, a, b = fresh(db)
    w = InPlayPokemon(card=db.get("Weedle"))
    a.active = w
    b.active = InPlayPokemon(card=DREEPY)
    fx._surprise_attack(ctx(st, a, b, source=w, rng=_Coin(heads=True)))
    check(b.active.damage == 30, f"Surprise Attack heads -> 30 (got {b.active.damage})")
    st, a, b = fresh(db)
    w = InPlayPokemon(card=db.get("Weedle"))
    a.active = w
    b.active = InPlayPokemon(card=DREEPY)
    fx._surprise_attack(ctx(st, a, b, source=w, rng=_Coin(heads=False)))
    check(b.active.damage == 0, f"Surprise Attack tails -> 0 (got {b.active.damage})")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Beedrill ex: Rumbling Bees scales 110 per Beedrill in play; "
          "Weedle's Surprise Attack is 30 on heads, 0 on tails.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
