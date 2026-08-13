#!/usr/bin/env python3
"""
test_protect_charge.py — Genesect ex (Black Bolt 67) Protect Charge:
"[M][M][C] 150 — During your opponent's next turn, this Pokémon takes 30 less damage
from attacks (after applying Weakness and Resistance)."

Two clauses are load-bearing and both are asserted:
  * "AFTER applying Weakness and Resistance" — a Fire attack for 100 into Genesect ex
    (Fire Weakness ×2) is 200, then −30 = 170. Reducing BEFORE W/R would give 140.
  * "During your opponent's NEXT turn" — the flag is set on Genesect's own turn and
    cleared at the start of the OWNER's next turn, so it covers exactly the one
    intervening opponent turn (the `shielded`/`retaliate` lifecycle).
Plus: the printed 150 is flat (engine-applied, so NOT in ATTACK_EFFECT_OWNS_DAMAGE),
and the reduction is an effect ON the defender, so a "damage isn't affected by any
effects on your opponent's Active" attack bypasses it.

Run: python3 tests/test_protect_charge.py
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
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    a.deck = [db.get("Basic Metal Energy")] * 8
    b.deck = [db.get("Basic Metal Energy")] * 8
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    gen_card = db.get("Genesect ex")

    # --- 0. card data + registry wiring. ---
    atk = next(a for a in gen_card.attacks if a.name == "Protect Charge")
    check(atk.cost == ("Metal", "Metal", "Colorless") and atk.damage == 150
          and atk.damage_suffix == "",
          f"Protect Charge is [M][M][C] for a flat 150, got {atk.cost} {atk.damage}")
    check("30 less damage" in atk.text and "after applying Weakness and Resistance" in atk.text,
          f"unexpected card text: {atk.text!r}")
    check(("Genesect ex", "Protect Charge") in fx.ATTACK_EFFECTS,
          "Protect Charge must be registered")
    check(("Genesect ex", "Protect Charge") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "the printed 150 is flat — the engine applies it, the effect only sets the shield")

    # --- 1. using it arms a 30-damage reduction on the user, nothing else. ---
    st, a, b = fresh_state(db)
    gen = InPlayPokemon(card=gen_card)
    a.active = gen
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    fx._protect_charge(ctx_for(st, a, b, source=gen))
    check(gen.damage_reduction == 30,
          f"Protect Charge must set damage_reduction=30, got {gen.damage_reduction}")
    check(b.active.damage == 0, "the effect itself deals no damage (the engine applies 150)")

    # --- 2. a plain 100-damage hit is reduced to 70. ---
    st, a, b = fresh_state(db)
    gen2 = InPlayPokemon(card=gen_card)
    gen2.damage_reduction = 30
    a.active = gen2
    attacker = InPlayPokemon(card=db.get("Crabominable"))    # Fighting: no W/R vs Genesect ex
    b.active = attacker
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=attacker), gen2, 100,
                                   owner=a, source=attacker)
    check(dealt == 70 and gen2.damage == 70,
          f"100 − 30 = 70 must land, got dealt={dealt} damage={gen2.damage}")

    # --- 3. AFTER Weakness: a Fire attacker's 100 doubles to 200, then −30 = 170. ---
    st, a, b = fresh_state(db)
    gen3 = InPlayPokemon(card=gen_card)
    gen3.damage_reduction = 30
    a.active = gen3
    fire = InPlayPokemon(card=db.get("Reshiram ex"))          # Fire type
    check(fire.card.types[0] == "Fire", "Reshiram ex is expected to be a Fire attacker")
    check(any(w == "Fire" for w, _ in gen_card.weaknesses), "Genesect ex is Fire-Weak")
    b.active = fire
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=fire), gen3, 100,
                                   owner=a, source=fire)
    check(dealt == 170,
          f"(100 ×2 Weakness) − 30 = 170 — the reduction is applied AFTER W/R, got {dealt}")

    # --- 4. NEGATIVE: no flag -> full damage. ---
    st, a, b = fresh_state(db)
    gen4 = InPlayPokemon(card=gen_card)                        # damage_reduction defaults 0
    a.active = gen4
    attacker2 = InPlayPokemon(card=db.get("Crabominable"))
    b.active = attacker2
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=attacker2), gen4, 100,
                                   owner=a, source=attacker2)
    check(dealt == 100, f"without Protect Charge the full 100 lands, got {dealt}")

    # --- 5. NEGATIVE: it never reduces below 0, and a small hit is fully absorbed. ---
    st, a, b = fresh_state(db)
    gen5 = InPlayPokemon(card=gen_card)
    gen5.damage_reduction = 30
    a.active = gen5
    attacker3 = InPlayPokemon(card=db.get("Crabominable"))
    b.active = attacker3
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=attacker3), gen5, 20,
                                   owner=a, source=attacker3)
    check(dealt == 0 and gen5.damage == 0,
          f"a 20-damage hit is fully absorbed (never negative), got {dealt}")

    # --- 6. an "ignore effects on the Active" attack bypasses the reduction. ---
    st, a, b = fresh_state(db)
    gen6 = InPlayPokemon(card=gen_card)
    gen6.damage_reduction = 30
    a.active = gen6
    bypasser = InPlayPokemon(card=db.get("Crabominable"))   # Fighting: no W/R vs Genesect ex
    b.active = bypasser
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=bypasser), gen6, 120,
                                   owner=a, source=bypasser, ignore_active_effects=True)
    check(dealt == 120,
          f"Superb Scissors-style damage ignores effects on the Active, got {dealt}")

    # --- 7. lifecycle: survives the opponent's turn, clears on the owner's next turn. ---
    st, a, b = fresh_state(db)
    gen7 = InPlayPokemon(card=gen_card)
    gen7.damage_reduction = 30
    a.active = gen7
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    st.active_index = 1
    start_turn(st)
    check(gen7.damage_reduction == 30,
          "the reduction must be live through the opponent's one intervening turn")
    st.active_index = 0
    start_turn(st)
    check(gen7.damage_reduction == 0,
          "the reduction must clear at the start of the owner's next turn")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_protect_charge.py: all checks passed — Protect Charge subtracts 30 AFTER "
          "Weakness/Resistance, for exactly the opponent's next turn")


if __name__ == "__main__":
    main()
