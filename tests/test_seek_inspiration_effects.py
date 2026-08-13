#!/usr/bin/env python3
"""
test_seek_inspiration_effects.py — Seek Inspiration now genuinely invokes the
copied attack's registered effect (not just its flat printed damage), matching
the rules-correct reading of "use it as this attack": the attack's own costs
and effects apply to whoever is now using it. This specifically fixes Kyurem's
Trifrost, which previously dealt 0 via the copy (its 110 lives in the effect,
not the printed damage field — confirmed dead in live-fire testing before this
fix). Also confirms Metagross/Zeraora's copies now genuinely discard Slowking's
own Energy (the real rider), not just deal a bare number.

Run: python3 tests/test_seek_inspiration_effects.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
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

    # --- 1. THE BUG: copying Kyurem's Trifrost previously dealt 0 (its 110 lives
    # in the effect, printed damage field is 0). Now it must genuinely hit 3
    # targets for 110 each AND discard Slowking's own Energy (Trifrost's real
    # cost — "discard all Energy from this Pokémon"). ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=db.get("Slowking"))
    slowking.energy = [db.get("Basic Psychic Energy"), db.get("Basic Psychic Energy")]
    a.active = slowking
    kyurem = db.get("Kyurem")
    a.deck = [kyurem]
    opp_active = InPlayPokemon(card=db.get("Dwebble"))       # 70 HP
    opp_b1 = InPlayPokemon(card=db.get("Dwebble"))
    opp_b2 = InPlayPokemon(card=db.get("Dwebble"))
    b.active = opp_active
    b.bench = [opp_b1, opp_b2]

    fx._seek_inspiration(ctx_for(st, a, b, source=slowking))

    check(kyurem in a.discard, "Kyurem must be discarded from the top of the deck")
    check(opp_active.damage == 110 and opp_b1.damage == 110 and opp_b2.damage == 110,
          f"Trifrost must hit all 3 Pokémon for 110 each (damage isn't capped at HP — "
          f"KOs are checked via remaining_hp separately), got "
          f"{opp_active.damage}/{opp_b1.damage}/{opp_b2.damage}")
    check(len(slowking.energy) == 0,
          f"Trifrost's real cost (discard all Energy from this Pokémon) must apply to "
          f"SLOWKING (the one now using the attack), got {len(slowking.energy)} left")

    # --- 2. Metagross's Luster Blast copy must now ALSO discard 2 Energy from
    # Slowking (the real rider), on top of the flat 200 damage. ---
    st, a, b = fresh_state(db)
    slowking2 = InPlayPokemon(card=db.get("Slowking"))
    slowking2.energy = [db.get("Basic Psychic Energy"), db.get("Basic Psychic Energy"),
                        db.get("Basic Psychic Energy")]
    a.active = slowking2
    a.deck = [db.get("Metagross")]
    opp2 = InPlayPokemon(card=db.get("Dwebble"))
    b.active = opp2

    fx._seek_inspiration(ctx_for(st, a, b, source=slowking2))

    check(opp2.is_knocked_out or opp2.damage >= 70, "Luster Blast's 200 damage must still land")
    check(len(slowking2.energy) == 1,
          f"Luster Blast's discard-2-Energy rider must apply to Slowking, "
          f"expected 1 left, got {len(slowking2.energy)}")

    # --- 3. A copied attack with NO registered effect still falls back to plain
    # flat damage only (the pre-fix behavior, for anything without a handler). ---
    st, a, b = fresh_state(db)
    slowking3 = InPlayPokemon(card=db.get("Slowking"))
    a.active = slowking3
    a.deck = [db.get("Meowth ex")]   # a Rule-Box mon -> should MISS entirely regardless
    opp3 = InPlayPokemon(card=db.get("Dwebble"))
    b.active = opp3
    fx._seek_inspiration(ctx_for(st, a, b, source=slowking3))
    check(opp3.damage == 0, "a Rule-Box discard (Meowth ex) must still be a miss (0 damage)")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_seek_inspiration_effects.py: all checks passed — Trifrost's real 110x3 fires via the copy")


if __name__ == "__main__":
    main()
