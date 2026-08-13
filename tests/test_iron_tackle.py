#!/usr/bin/env python3
"""
test_iron_tackle.py — Beldum (Temporal Forces 113) Iron Tackle:
"[M][C][C] 50 — This Pokémon also does 10 damage to itself."

The printed 50 is a flat number the engine auto-applies, so Iron Tackle must NOT be
in ATTACK_EFFECT_OWNS_DAMAGE; the registered effect only adds the 10 self-damage.
Self-damage from your own attack is not damage done TO a Pokémon you are attacking,
so it lands directly (no Weakness/Resistance, no shield check) — the same shape as
Koraidon ex's Kaiser Tackle.

Run: python3 tests/test_iron_tackle.py
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

    # --- 0. card data + registry wiring match the printed card. ---
    beldum_card = db.get("Beldum")
    atk = next(a for a in beldum_card.attacks if a.name == "Iron Tackle")
    check(atk.cost == ("Metal", "Colorless", "Colorless"),
          f"Iron Tackle costs [M][C][C], got {atk.cost}")
    check(atk.damage == 50 and atk.damage_suffix == "",
          f"Iron Tackle is a flat 50, got {atk.damage}{atk.damage_suffix!r}")
    check("10 damage to itself" in atk.text, f"unexpected card text: {atk.text!r}")
    check(("Beldum", "Iron Tackle") in fx.ATTACK_EFFECTS, "Iron Tackle must be registered")
    check(("Beldum", "Iron Tackle") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Iron Tackle's printed 50 is flat — the engine applies it, the effect must NOT")

    # --- 1. the effect does exactly 10 to ITSELF. ---
    st, a, b = fresh_state(db)
    beldum = InPlayPokemon(card=beldum_card)
    a.active = beldum
    victim = InPlayPokemon(card=db.get("Crabominable"))
    b.active = victim
    fx._iron_tackle(ctx_for(st, a, b, source=beldum))
    check(beldum.damage == 10, f"Iron Tackle must put 10 on itself, got {beldum.damage}")

    # --- 2. NEGATIVE: the self-damage must not touch the opponent's Active. ---
    check(victim.damage == 0,
          f"the 10 goes to itself only — opponent took {victim.damage}")

    # --- 3. NEGATIVE: it is not Weakness-multiplied and not blocked by a shield —
    # a shielded Beldum still takes its own 10 (the damage is self-inflicted, it
    # never routes through apply_attack_damage). ---
    st, a, b = fresh_state(db)
    shielded = InPlayPokemon(card=beldum_card)
    shielded.shielded = True
    a.active = shielded
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    fx._iron_tackle(ctx_for(st, a, b, source=shielded))
    check(shielded.damage == 10,
          f"self-damage is not attack damage — expected 10 on itself, got {shielded.damage}")

    # --- 4. the self-damage can genuinely KO Beldum (70 HP). ---
    st, a, b = fresh_state(db)
    hurt = InPlayPokemon(card=beldum_card, damage=60)
    a.active = hurt
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    fx._iron_tackle(ctx_for(st, a, b, source=hurt))
    check(hurt.damage == 70 and hurt.is_knocked_out,
          f"60 + 10 self-damage must KO a 70 HP Beldum, got {hurt.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_iron_tackle.py: all checks passed — Iron Tackle adds exactly 10 to "
          "itself on top of the engine-applied 50, and nothing to the defender")


if __name__ == "__main__":
    main()
