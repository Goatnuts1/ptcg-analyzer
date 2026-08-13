#!/usr/bin/env python3
"""
test_repulsor_axe.py — assert Iron Boulder ex's Repulsor Axe (a real Basic
Fighting ex, used in the cornerstone_box build) does exactly what its card
text says, and that generalizing the shared `retaliate` mechanism to a
configurable `retaliate_counters` count didn't regress Mega Slowbro ex's
Shellnado Spin (the original user of that chokepoint).

Card text (verified this session, quoted at the assertion site):

  Iron Boulder ex — Repulsor Axe [F][C] 60: "During your opponent's next
  turn, if this Pokémon is damaged by an attack (even if it is Knocked
  Out), put 8 damage counters on the Attacking Pokémon."

Run from project root:  python3 tests/test_repulsor_axe.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game, effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    a.prizes = [db.get("Basic Fire Energy")] * 6
    b.prizes = [db.get("Basic Fire Energy")] * 6
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.turns_taken = b.turns_taken = 5
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    card = db.get("Iron Boulder ex")

    # --- 1. Repulsor Axe: 60 direct damage, arms retaliate=True with 8 counters. ---
    st, a, b = fresh_state(db)
    ib = InPlayPokemon(card=card)
    a.active = ib
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    ra_i = next(i for i, atk in enumerate(card.attacks) if atk.name == "Repulsor Axe")
    game._resolve_attack(st, ra_i)
    check(b.active.damage == 60, f"Repulsor Axe should deal 60, got {b.active.damage}")
    check(ib.retaliate is True and ib.retaliate_counters == 8,
          f"should arm retaliate=8, got {ib.retaliate}/{ib.retaliate_counters}")

    # --- 2. Retaliation actually fires for 80 (8 counters) on the attacker, even
    # when the SAME hit that triggers it also Knocks Out the retaliator — the
    # card's own "(even if it is Knocked Out)" clause. ---
    st, a, b = fresh_state(db)
    ib2 = InPlayPokemon(card=card)
    ib2.retaliate = True
    ib2.retaliate_counters = 8
    ib2.damage = 1000
    a.active = ib2
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    ctx = fx.EffectContext(state=st, me=b, opp=a, source=attacker, db=db, rng=st.rng)
    fx.apply_attack_damage(ctx, ib2, 50, owner=a, source=attacker)
    check(attacker.damage == 80,
          f"attacker should take 80 (8 counters) even though the target was KO'd "
          f"by the same hit, got {attacker.damage}")

    # --- 3. Regression: Mega Slowbro ex's Shellnado Spin still retaliates for the
    # default 12 counters (120 damage) — the generalized retaliate_counters field
    # must default correctly for the original user of this chokepoint. ---
    st, a, b = fresh_state(db)
    slowbro = InPlayPokemon(card=db.get("Mega Slowbro ex"))
    slowbro.retaliate = True
    a.active = slowbro
    attacker2 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker2
    ctx2 = fx.EffectContext(state=st, me=b, opp=a, source=attacker2, db=db, rng=st.rng)
    fx.apply_attack_damage(ctx2, slowbro, 50, owner=a, source=attacker2)
    check(attacker2.damage == 120,
          f"Shellnado Spin should still retaliate for the default 120 "
          f"(12 counters), got {attacker2.damage}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Repulsor Axe (60 dmg + 8-counter retaliation, fires through a KO) "
          "and the generalized retaliate_counters field (Shellnado Spin's default "
          "12 unaffected) both hold.")


if __name__ == "__main__":
    main()
