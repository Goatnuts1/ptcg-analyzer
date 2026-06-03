#!/usr/bin/env python3
"""
test_search.py — the draw/search engine (MILESTONE §2.1).

Asserts each search/recovery Trainer does EXACTLY what its card text says, built on
the generalized search_deck / recover_from_discard primitives.

Run from project root:  python3 tests/test_search.py
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


def ctx(st, me, opp):
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    EX = db.get("Dragapult ex")     # Stage 2 + ex (has a Rule Box)
    DREEPY = db.get("Dreepy")        # Basic, evolves to Drakloak
    DRAKLOAK = db.get("Drakloak")    # Stage 1
    FIRE = db.get("Basic Fire Energy")
    WATER = db.get("Basic Water Energy")

    # --- Poké Pad: search a non-Rule-Box Pokémon → hand (skips the ex). ---
    st, a, b = fresh(db)
    a.deck = [EX, DREEPY]
    ok = fx._poke_pad(ctx(st, a, b))
    check(ok and DREEPY in a.hand, "Poké Pad should fetch the non-Rule-Box Dreepy")
    check(EX in a.deck, "Poké Pad must NOT fetch a Rule-Box Pokémon (Dragapult ex)")

    # --- Ultra Ball: discard 2 others, search any Pokémon (incl. ex). ---
    st, a, b = fresh(db)
    a.hand = [FIRE, WATER]          # the 2 "other" cards (Ultra Ball already popped)
    a.deck = [EX]
    ok = fx._ultra_ball(ctx(st, a, b))
    check(ok and EX in a.hand, "Ultra Ball should search any Pokémon (the ex) to hand")
    check(len(a.discard) == 2 and FIRE in a.discard and WATER in a.discard,
          f"Ultra Ball should discard exactly 2 others, discard={[c.name for c in a.discard]}")
    check(EX not in a.deck, "searched Pokémon should leave the deck")

    # --- Hilda: an Evolution Pokémon AND an Energy → hand. ---
    st, a, b = fresh(db)
    a.deck = [DRAKLOAK, FIRE, DREEPY]
    ok = fx._hilda(ctx(st, a, b))
    check(ok and DRAKLOAK in a.hand and FIRE in a.hand,
          "Hilda should fetch an Evolution Pokémon + an Energy")
    check(DREEPY in a.deck, "Hilda should not fetch a non-Evolution Basic")

    # --- Dawn: a Basic + a Stage 1 + a Stage 2 → hand (Stage 2 may be an ex). ---
    st, a, b = fresh(db)
    a.deck = [DREEPY, DRAKLOAK, EX, FIRE]
    ok = fx._dawn(ctx(st, a, b))
    check(ok and DREEPY in a.hand and DRAKLOAK in a.hand and EX in a.hand,
          "Dawn should fetch one Basic + one Stage 1 + one Stage 2")
    check(FIRE in a.deck and len(a.hand) == 3, "Dawn should fetch exactly the 3 Pokémon")

    # --- Night Stretcher: a Pokémon OR Basic Energy from discard → hand. ---
    st, a, b = fresh(db)
    a.discard = [DREEPY]
    ok = fx._night_stretcher(ctx(st, a, b))
    check(ok and DREEPY in a.hand and DREEPY not in a.discard,
          "Night Stretcher should pull a Pokémon from discard to hand")

    # --- Energy Retrieval: up to 2 Basic Energy from discard → hand. ---
    st, a, b = fresh(db)
    a.discard = [FIRE, FIRE, FIRE]
    ok = fx._energy_retrieval(ctx(st, a, b))
    check(ok and a.hand.count(FIRE) == 2 and a.discard.count(FIRE) == 1,
          f"Energy Retrieval should recover exactly 2 of 3 (hand={a.hand.count(FIRE)})")

    # --- Switch: Active <-> a Benched Pokémon (v0 brings up the healthiest). ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=DREEPY, damage=60)        # nearly dead
    healthy = InPlayPokemon(card=DRAKLOAK)                  # full HP
    a.bench = [healthy]
    ok = fx._switch(ctx(st, a, b))
    check(ok and a.active is healthy and a.active.card.name == "Drakloak",
          "Switch should bring up the benched Pokémon")
    check(any(m.card.name == "Dreepy" for m in a.bench),
          "the old Active should go to the bench")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — §2.1 search/recovery engine: Poké Pad, Ultra Ball, Hilda, Dawn, "
          "Night Stretcher, Energy Retrieval, Switch all match card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
