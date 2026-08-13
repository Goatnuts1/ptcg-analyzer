#!/usr/bin/env python3
"""
test_shellnado_spin.py — Mega Slowbro ex's Shellnado Spin: "During your
opponent's next turn, if this Pokémon is damaged by an attack (even if this
Pokémon is Knocked Out), place 12 damage counters on the Attacking Pokémon."
Modeled like Dunsparce's Dig shield (a flag set directly on the attacker,
checked in apply_attack_damage, cleared at the start of the OWNER's next
turn) rather than the pending/active split used for opponent-wide debuffs,
since this is a standing retaliation on the Pokémon itself, not a turn-scoped
debuff on the opponent.

Run: python3 tests/test_shellnado_spin.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import start_turn


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

    # --- 1. Using Shellnado Spin sets the retaliate flag on the user, nothing else. ---
    st, a, b = fresh_state(db)
    slowbro = InPlayPokemon(card=db.get("Mega Slowbro ex"))
    a.active = slowbro
    fx._shellnado_spin(ctx_for(st, a, b, source=slowbro))
    check(slowbro.retaliate is True, "Shellnado Spin must set retaliate=True on the user")

    # --- 2. The opponent then attacks INTO the retaliating Slowbro (even for a
    # KO-sized hit) -> the ATTACKER takes 12 counters (120 damage), not Slowbro
    # taking extra damage itself. ---
    st, a, b = fresh_state(db)
    slowbro2 = InPlayPokemon(card=db.get("Mega Slowbro ex"))
    slowbro2.retaliate = True
    a.active = slowbro2
    attacker = InPlayPokemon(card=db.get("Dwebble"))   # any real attacker, 70 HP
    b.active = attacker
    ctx = ctx_for(st, b, a, source=attacker)   # b is "me" (the attacker's owner) this swing
    dealt = fx.apply_attack_damage(ctx, slowbro2, 400, owner=a, source=attacker)  # KO-sized hit
    check(dealt == 400, f"the incoming attack damage itself must still land in full, got {dealt}")
    check(slowbro2.is_knocked_out, "Slowbro must actually be Knocked Out by a 400-damage hit")
    check(attacker.damage == 120,
          f"the attacker must take 12 counters (120 damage) back, even though Slowbro was KO'd, got {attacker.damage}")

    # --- 3. No retaliate flag -> no counters land on the attacker. ---
    st, a, b = fresh_state(db)
    slowbro3 = InPlayPokemon(card=db.get("Mega Slowbro ex"))   # retaliate defaults False
    a.active = slowbro3
    attacker2 = InPlayPokemon(card=db.get("Dwebble"))
    b.active = attacker2
    ctx2 = ctx_for(st, b, a, source=attacker2)
    fx.apply_attack_damage(ctx2, slowbro3, 180, owner=a, source=attacker2)
    check(attacker2.damage == 0, "without the retaliate flag, the attacker must take no counters")

    # --- 4. The flag clears at the start of the OWNER's next turn (i.e. it lasts
    # exactly through the opponent's one intervening turn, same lifecycle as
    # Dunsparce's `shielded`). ---
    st, a, b = fresh_state(db)
    slowbro4 = InPlayPokemon(card=db.get("Mega Slowbro ex"))
    slowbro4.retaliate = True
    a.active = slowbro4
    a.deck = [db.get("Basic Psychic Energy")] * 5
    b.deck = [db.get("Basic Psychic Energy")] * 5
    st.active_index = 1
    start_turn(st)   # opponent's (B's) turn begins — must NOT clear A's flag
    check(slowbro4.retaliate is True, "the flag must survive through the opponent's own turn")
    st.active_index = 0
    start_turn(st)   # back to A's (the owner's) turn — NOW it clears
    check(slowbro4.retaliate is False,
          "the flag must clear at the start of the owner's next turn, same as `shielded`")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_shellnado_spin.py: all checks passed — Shellnado Spin's retaliation "
          "fires even on a KO, and clears on the right turn boundary")


if __name__ == "__main__":
    main()
