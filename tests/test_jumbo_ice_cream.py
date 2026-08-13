#!/usr/bin/env python3
"""
test_jumbo_ice_cream.py — Jumbo Ice Cream (Phantasmal Flames 91), Item:
"Heal 80 damage from your Active Pokémon that has 3 or more Energy attached."

Load-bearing: the ACTIVE only (a damaged Benched Pokémon is not healed), 3+ Energy
attached is a hard gate (2 is a negative case), and the heal never goes past 0 damage.

DATA CORRECTION recorded here: Jumbo Ice Cream is a PLAIN Item — it is NOT an ACE SPEC
(verified on Bulbapedia; the pool entry likewise carries no ACE SPEC subtype and no ACE
SPEC rule line). That matters for deck legality: DECK_MEGA_EXCADRILL runs 2 copies
alongside its single ACE SPEC (Precious Trolley), which is only legal because of this.

Run: python3 tests/test_jumbo_ice_cream.py
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


def trainer_ctx(st, me, opp):
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    card = db.get("Jumbo Ice Cream")
    metal = db.get("Basic Metal Energy")

    # --- 0. card data + registry wiring, incl. the NOT-an-ACE-SPEC assertion. ---
    check(card.is_item, "Jumbo Ice Cream is an Item")
    check("ACE SPEC" not in card.subtypes,
          f"Jumbo Ice Cream is NOT an ACE SPEC; pool subtypes = {card.subtypes}")
    check(any("Heal 80 damage from your Active Pokémon that has 3 or more Energy attached"
              in r for r in card.rules), f"unexpected card text: {card.rules}")
    check("Jumbo Ice Cream" in fx.TRAINER_EFFECTS, "Jumbo Ice Cream must be registered")

    # --- 1. Active with 3 Energy and 100 damage -> 80 healed (20 left). ---
    st, a, b = fresh_state(db)
    act = InPlayPokemon(card=db.get("Mega Excadrill ex"), damage=100)
    act.energy = [metal] * 3
    a.active = act
    did = fx._jumbo_ice_cream(trainer_ctx(st, a, b))
    check(did is True, "it must report that it acted")
    check(act.damage == 20, f"100 − 80 = 20 damage left, got {act.damage}")

    # --- 2. NEGATIVE: only 2 Energy attached -> nothing happens. ---
    st, a, b = fresh_state(db)
    act2 = InPlayPokemon(card=db.get("Mega Excadrill ex"), damage=100)
    act2.energy = [metal] * 2
    a.active = act2
    did = fx._jumbo_ice_cream(trainer_ctx(st, a, b))
    check(did is False, "2 Energy is not '3 or more' — it must report it did nothing")
    check(act2.damage == 100, f"no healing may happen, got {act2.damage}")

    # --- 3. NEGATIVE: an undamaged Active has nothing to heal. ---
    st, a, b = fresh_state(db)
    act3 = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    act3.energy = [metal] * 4
    a.active = act3
    check(fx._jumbo_ice_cream(trainer_ctx(st, a, b)) is False,
          "an undamaged Active means the card would do nothing")

    # --- 4. NEGATIVE: a damaged BENCHED Pokémon with 3 Energy is not healed. ---
    st, a, b = fresh_state(db)
    act4 = InPlayPokemon(card=db.get("Metang"))               # Active: no Energy, no damage
    bench = InPlayPokemon(card=db.get("Metagross"), damage=90)
    bench.energy = [metal] * 3
    a.active, a.bench = act4, [bench]
    did = fx._jumbo_ice_cream(trainer_ctx(st, a, b))
    check(did is False and bench.damage == 90,
          f"the Bench is never healed by this card, got bench damage {bench.damage}")

    # --- 5. the heal clamps at 0 (a 30-damage Active goes to 0, not negative). ---
    st, a, b = fresh_state(db)
    act5 = InPlayPokemon(card=db.get("Mega Excadrill ex"), damage=30)
    act5.energy = [metal] * 3
    a.active = act5
    fx._jumbo_ice_cream(trainer_ctx(st, a, b))
    check(act5.damage == 0, f"healing must clamp at 0 damage, got {act5.damage}")

    # --- 6. can_play mirrors the effect's gates. ---
    st, a, b = fresh_state(db)
    act6 = InPlayPokemon(card=db.get("Mega Excadrill ex"), damage=50)
    act6.energy = [metal] * 2
    a.active = act6
    check(fx.can_play_trainer(st, a, "Jumbo Ice Cream") is False,
          "2 Energy -> must not be offered")
    act6.energy.append(metal)
    check(fx.can_play_trainer(st, a, "Jumbo Ice Cream") is True,
          "3 Energy + damage -> must be offered")
    act6.damage = 0
    check(fx.can_play_trainer(st, a, "Jumbo Ice Cream") is False,
          "no damage -> must not be offered")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_jumbo_ice_cream.py: all checks passed — heals exactly 80 from a 3+ Energy "
          "Active only, and is not an ACE SPEC")


if __name__ == "__main__":
    main()
