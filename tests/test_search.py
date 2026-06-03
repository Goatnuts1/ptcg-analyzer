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

    # --- Lillie's Determination: shuffle hand into deck, draw 6 (8 at exactly 6 prizes). ---
    st, a, b = fresh(db)
    a.hand = [FIRE, WATER]
    a.deck = [DREEPY] * 10
    a.prizes = [DREEPY] * 4            # not 6 -> draw 6
    fx._lillies_determination(ctx(st, a, b))
    # 2 hand + 10 deck = 12 conserved; after shuffle-in and draw 6 -> hand 6, deck 6.
    check(len(a.hand) == 6 and len(a.deck) == 6,
          f"Lillie's: shuffle hand in, draw 6 (hand={len(a.hand)}, deck={len(a.deck)})")
    st, a, b = fresh(db)
    a.hand = [FIRE]; a.deck = [DREEPY] * 12; a.prizes = [DREEPY] * 6   # exactly 6 -> draw 8
    fx._lillies_determination(ctx(st, a, b))
    check(len(a.hand) == 8, f"Lillie's should draw 8 at exactly 6 prizes (hand={len(a.hand)})")

    # --- Judge: BOTH players shuffle hand into deck and draw 4. ---
    st, a, b = fresh(db)
    a.hand = [FIRE, WATER, DREEPY]; a.deck = [DREEPY] * 10
    b.hand = [FIRE]; b.deck = [WATER] * 10
    fx._judge(ctx(st, a, b))
    check(len(a.hand) == 4 and len(b.hand) == 4,
          f"Judge should leave both players with 4 cards (a={len(a.hand)}, b={len(b.hand)})")

    # --- Crispin: 2 Basic Energy of DIFFERENT types; attach 1 to Active, 1 to hand. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=DREEPY)
    a.deck = [FIRE, FIRE, WATER]      # two types available: Fire, Water
    fx._crispin(ctx(st, a, b))
    attached = a.active.energy
    check(len(attached) == 1, f"Crispin should attach exactly 1 energy (got {len(attached)})")
    check(len(a.hand) == 1 and a.hand[0].is_basic_energy, "Crispin should put 1 energy into hand")
    types = {attached[0].types[0], a.hand[0].types[0]}
    check(types == {"Fire", "Water"}, f"Crispin's two energy must be DIFFERENT types, got {types}")

    # --- Dudunsparce Run Away Draw: draw 3, shuffle this Pokémon into the deck. ---
    st, a, b = fresh(db)
    dudun = InPlayPokemon(card=db.get("Dudunsparce"), energy=[FIRE])
    a.active = InPlayPokemon(card=DREEPY)      # so removing benched Dudun is clean
    a.bench = [dudun]
    a.deck = [WATER] * 5
    deck0 = len(a.deck)
    src_ctx = fx.EffectContext(state=st, me=a, opp=b, source=dudun, db=st.db, rng=st.rng)
    fx._run_away_draw(src_ctx)
    check(len(a.hand) == 3, f"Run Away Draw should draw 3 (hand={len(a.hand)})")
    check(all(m.card.name != "Dudunsparce" for m in a.bench),
          "Dudunsparce should leave play after Run Away Draw")
    check(any(c.name == "Dudunsparce" for c in a.deck) and FIRE in a.deck,
          "Dudunsparce and its attached energy should be shuffled into the deck")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — §2.1 draw/search engine: Poké Pad, Ultra Ball, Hilda, Dawn, Night Stretcher, "
          "Energy Retrieval, Switch, Lillie's Determination, Judge, Crispin, Run Away Draw "
          "all match card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
