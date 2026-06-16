#!/usr/bin/env python3
"""
test_crustle.py — the Crustle Grass-control line: Dwebble (Ascension), Brambleghast
(Powerful Needles), and Crustle's Mysterious Rock Inn (ex-damage wall).

Run from project root:  python3 tests/test_crustle.py
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


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    DREEPY = db.get("Dreepy")
    GRASS = db.get("Basic Grass Energy")

    # --- Dwebble Ascension: search-evolve Dwebble -> Crustle from the deck ---
    st, a, b = fresh(db)
    dweb = InPlayPokemon(card=db.get("Dwebble"))
    a.active = dweb
    a.deck = [db.get("Crustle"), DREEPY, GRASS]
    fx._ascension(ctx(st, a, b, source=dweb))
    check(dweb.card.name == "Crustle", f"Ascension evolves Dwebble -> Crustle (got {dweb.card.name})")
    check(not any(c.name == "Crustle" for c in a.deck), "Crustle was pulled from the deck")

    # --- Brambleghast Powerful Needles: 80 per heads, one flip per attached Energy ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Brambleghast"), energy=[GRASS, GRASS, GRASS])
    a.active = src
    b.active = InPlayPokemon(card=DREEPY)
    fx._powerful_needles(ctx(st, a, b, source=src, rng=_Coin(heads=True)))  # 3 energy, all heads
    exp = 240 * (2 if any(w == "Grass" for w, _ in DREEPY.weaknesses) else 1)
    check(b.active.damage == exp, f"Powerful Needles 3 heads -> 240 (got {b.active.damage})")
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Brambleghast"), energy=[GRASS, GRASS])
    a.active = src; b.active = InPlayPokemon(card=DREEPY)
    fx._powerful_needles(ctx(st, a, b, source=src, rng=_Coin(heads=False)))  # all tails
    check(b.active.damage == 0, f"Powerful Needles all tails -> 0 (got {b.active.damage})")

    # --- Crustle Mysterious Rock Inn: prevents damage from the opponent's Pokémon ex ---
    st, a, b = fresh(db)
    crustle = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle
    ex_attacker = InPlayPokemon(card=db.get("Mega Lucario ex"))   # an ex
    a.active = ex_attacker
    dealt = fx.apply_attack_damage(ctx(st, a, b, source=ex_attacker), crustle, 200,
                                   owner=b, source=ex_attacker)
    check(dealt == 0 and crustle.damage == 0, "Rock Inn prevents ALL damage from an ex attacker")
    # ...but a non-ex attacker gets through
    st, a, b = fresh(db)
    crustle = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle
    non_ex = InPlayPokemon(card=db.get("Riolu"))                  # not an ex
    a.active = non_ex
    dealt = fx.apply_attack_damage(ctx(st, a, b, source=non_ex), crustle, 60,
                                   owner=b, source=non_ex)
    check(dealt > 0 and crustle.damage > 0, "Rock Inn does NOT block a non-ex attacker")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Crustle line: Ascension evolves from deck; Powerful Needles flips per "
          "Energy (80 each); Mysterious Rock Inn walls ex attackers but not non-ex.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
