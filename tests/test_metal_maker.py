#!/usr/bin/env python3
"""
test_metal_maker.py — Metang (SVP Black Star Promos 90) Ability Metal Maker:
"Once during your turn, you may look at the top 4 cards of your deck and attach any
number of Basic Metal Energy cards you find there to your Pokémon in any way you
like. Shuffle the other cards and put them on the bottom of your deck."

Asserted here, clause by clause: the window is exactly the top 4; ONLY Basic Metal
Energy is attachable (other Energy types and Pokémon are not); the leftovers go to
the BOTTOM of the deck (they are not shuffled into it, and the cards that were below
the window keep their positions above them); the deck loses exactly the attached
cards; and the ability is once-per-turn (not in REPEATABLE_ABILITIES).

Run: python3 tests/test_metal_maker.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    metal = db.get("Basic Metal Energy")
    psychic = db.get("Basic Psychic Energy")
    metang_card = db.get("Metang")

    # --- 0. card text + registry wiring. ---
    ab = next(a for a in metang_card.abilities if a.name == "Metal Maker")
    check("top 4 cards" in ab.text and "Basic Metal Energy" in ab.text
          and "bottom of your deck" in ab.text, f"unexpected ability text: {ab.text!r}")
    check(("Metang", "Metal Maker") in fx.ABILITY_EFFECTS, "Metal Maker must be registered")
    check(not fx.is_repeatable_ability("Metang", "Metal Maker"),
          "Metal Maker is ONCE during your turn — it must not be repeatable")

    # --- 1. two Metal in the window -> both attached to the Active; the other two
    # window cards go to the BOTTOM, below the cards that were already under them. ---
    st, a, b = fresh_state(db)
    metang = InPlayPokemon(card=metang_card)
    a.active = metang
    below1, below2 = db.get("Beldum"), db.get("Ultra Ball")
    a.deck = [metal, psychic, metal, db.get("Drilbur"), below1, below2]
    fx._metal_maker(ctx_for(st, a, b, source=metang))
    check(metang.energy_count() == 2 and all(e.name == "Basic Metal Energy"
                                             for e in metang.energy),
          f"both Basic Metal Energy must be attached, got {[e.name for e in metang.energy]}")
    check(len(a.deck) == 4, f"deck must shrink by exactly the 2 attached, got {len(a.deck)}")
    check(a.deck[0] is below1 and a.deck[1] is below2,
          "the cards that were BELOW the top 4 must now be on top, in order")
    check({c.name for c in a.deck[2:]} == {"Basic Psychic Energy", "Drilbur"},
          f"the 2 non-Metal window cards must be on the bottom, got "
          f"{[c.name for c in a.deck[2:]]}")

    # --- 2. NEGATIVE: a window with no Basic Metal Energy attaches nothing, and the
    # whole window is bottomed (deck size unchanged). Other Energy types don't count. ---
    st, a, b = fresh_state(db)
    metang2 = InPlayPokemon(card=metang_card)
    a.active = metang2
    top = [psychic, psychic, db.get("Beldum"), db.get("Boss's Orders")]
    a.deck = list(top) + [below1]
    fx._metal_maker(ctx_for(st, a, b, source=metang2))
    check(metang2.energy_count() == 0,
          f"no Basic Metal Energy in the top 4 -> nothing attached, got "
          f"{[e.name for e in metang2.energy]}")
    check(len(a.deck) == 5 and a.deck[0] is below1,
          f"the whole window must be bottomed (size 5, below1 on top), got "
          f"{len(a.deck)} / {a.deck[0].name}")

    # --- 3. NEGATIVE: a Special Energy that provides Metal is NOT a "Basic Metal
    # Energy" card and must not be attached. ---
    st, a, b = fresh_state(db)
    metang3 = InPlayPokemon(card=metang_card)
    a.active = metang3
    special = next((db.get(n) for n in ("Boomerang Energy", "Prism Energy")
                    if n in db), None)
    check(special is not None, "expected a Special Energy in the pool for this check")
    a.deck = [special, metal, db.get("Beldum"), db.get("Beldum")]
    fx._metal_maker(ctx_for(st, a, b, source=metang3))
    check([e.name for e in metang3.energy] == ["Basic Metal Energy"],
          f"only the Basic Metal Energy may be attached, got "
          f"{[e.name for e in metang3.energy]}")

    # --- 4. fewer than 4 cards left: look at what there is, no crash. ---
    st, a, b = fresh_state(db)
    metang4 = InPlayPokemon(card=metang_card)
    a.active = metang4
    a.deck = [metal]
    fx._metal_maker(ctx_for(st, a, b, source=metang4))
    check(metang4.energy_count() == 1 and a.deck == [],
          f"a 1-card deck must still yield its Metal, got {metang4.energy_count()} / {a.deck}")

    # --- 5. with no Active, the attach falls back to a Benched Pokémon. ---
    st, a, b = fresh_state(db)
    bench_mon = InPlayPokemon(card=db.get("Beldum"))
    a.bench = [bench_mon]
    a.deck = [metal, metal, metal, metal]
    fx._metal_maker(ctx_for(st, a, b, source=bench_mon))
    check(bench_mon.energy_count() == 4,
          f"all 4 Metal must land on the only Pokémon in play, got {bench_mon.energy_count()}")

    # --- 6. the can-use guard is deck-based only (it must NOT peek at the window,
    # which is hidden information): empty deck -> unusable, any deck -> usable. ---
    guard = fx.get_ability_can_use("Metang", "Metal Maker")
    check(guard is not None, "Metal Maker should have a can-use guard")
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=metang_card)
    a.deck = []
    check(guard(st, a, a.active) is False, "with an empty deck Metal Maker must be unusable")
    a.deck = [db.get("Boss's Orders")]     # no Metal Energy anywhere in the deck...
    check(guard(st, a, a.active) is True,
          "...the guard must still allow it — the top 4 are hidden information")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_metal_maker.py: all checks passed — Metal Maker attaches every Basic "
          "Metal Energy from the top 4 and bottoms the rest")


if __name__ == "__main__":
    main()
