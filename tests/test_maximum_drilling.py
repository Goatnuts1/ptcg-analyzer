#!/usr/bin/env python3
"""
test_maximum_drilling.py — Mega Excadrill ex (Pitch Black 65) Maximum Drilling:
"[M][M][M] 200+ — If this Pokémon has at least 2 extra Energy attached (in addition to
this attack's cost), this attack does 130 more damage."

The cost is 3 Energy, so "at least 2 extra" = 5 or more attached -> 330 total.
4 attached is the negative case (still 200), and 6 attached does NOT scale further
(the bonus is a one-shot +130, not per-Energy).

Damage handling: the card is printed "200+", i.e. variable damage, so the engine
applies 0 base and this effect lands the whole hit through the Weakness/Resistance
chokepoint once — the same pattern as Regirock ex's Giant Rock ("140+"). It therefore
does NOT need an ATTACK_EFFECT_OWNS_DAMAGE entry, which is asserted below so nobody
"fixes" it into double-applying its damage.

Run: python3 tests/test_maximum_drilling.py
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


def drill(db, st, a, b, energy_count, defender_name="Genesect ex"):
    exca = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    exca.energy = [db.get("Basic Metal Energy")] * energy_count
    a.active = exca
    defender = InPlayPokemon(card=db.get(defender_name))
    b.active = defender
    fx._maximum_drilling(ctx_for(st, a, b, source=exca))
    return defender


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    exca_card = db.get("Mega Excadrill ex")

    # --- 0. card data + registry wiring. ---
    atk = next(a for a in exca_card.attacks if a.name == "Maximum Drilling")
    check(atk.cost == ("Metal", "Metal", "Metal"),
          f"Maximum Drilling costs [M][M][M], got {atk.cost}")
    check(atk.damage == 200 and atk.damage_suffix == "+",
          f"Maximum Drilling is printed 200+, got {atk.damage}{atk.damage_suffix!r}")
    check("at least 2 extra Energy" in atk.text and "130 more damage" in atk.text,
          f"unexpected card text: {atk.text!r}")
    check(("Mega Excadrill ex", "Maximum Drilling") in fx.ATTACK_EFFECTS,
          "Maximum Drilling must be registered")
    check(("Mega Excadrill ex", "Maximum Drilling") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "'200+' is variable damage — the engine already applies 0 base for it, so an "
          "OWNS_DAMAGE entry would be redundant/misleading")

    # --- 1. exactly the cost (3 Energy) -> 200. ---
    st, a, b = fresh_state(db)
    d = drill(db, st, a, b, 3)
    check(d.damage == 200, f"3 Energy (no extras) must do 200, got {d.damage}")

    # --- 2. NEGATIVE: 4 Energy is only ONE extra -> still 200. ---
    st, a, b = fresh_state(db)
    d = drill(db, st, a, b, 4)
    check(d.damage == 200, f"4 Energy is 1 extra — still 200, got {d.damage}")

    # --- 3. 5 Energy = 2 extra -> 200 + 130 = 330. ---
    st, a, b = fresh_state(db)
    d = drill(db, st, a, b, 5)
    check(d.damage == 330, f"5 Energy (2 extra) must do 330, got {d.damage}")

    # --- 4. NEGATIVE: 6 Energy does not scale past +130. ---
    st, a, b = fresh_state(db)
    d = drill(db, st, a, b, 6)
    check(d.damage == 330, f"the bonus is a flat +130, not per-Energy, got {d.damage}")

    # --- 5. NEGATIVE: 2 Energy (can't even pay the cost) still computes only the base —
    # the effect never invents a bonus from a short board. ---
    st, a, b = fresh_state(db)
    d = drill(db, st, a, b, 2)
    check(d.damage == 200, f"below-cost Energy must not grant the bonus, got {d.damage}")

    # --- 6. Weakness multiplies the FULL boosted total exactly once: 330 ×2 = 660. ---
    st, a, b = fresh_state(db)
    d = drill(db, st, a, b, 5, defender_name="Crabominable")   # Metal Weakness ×2
    check(any(w == "Metal" for w, _ in d.card.weaknesses),
          "Crabominable is expected to be Metal-Weak in this pool")
    check(d.damage == 660, f"330 doubled by Weakness = 660, got {d.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_maximum_drilling.py: all checks passed — Maximum Drilling is 200, and 330 "
          "only at 5+ attached Energy (2 past its 3-Energy cost)")


if __name__ == "__main__":
    main()
