#!/usr/bin/env python3
"""
test_cheer_on_to_glory.py — Cynthia's Roserade (sv10 8) Ability "Cheer On to Glory":
"Attacks used by your Cynthia's Pokémon do 30 more damage to your opponent's Active
Pokémon (before applying Weakness and Resistance)."

A PASSIVE, board-wide, non-self Ability, so it lives in the apply_attack_damage
chokepoint next to Brave Bangle's and Kieran's pre-W/R adds — not in ABILITY_EFFECTS.
Every clause is a separate negative case here: "your" (not the opponent's Roserade),
"your Cynthia's Pokémon" (not any attacker), "your opponent's ACTIVE" (never a Benched
target), and "before applying Weakness and Resistance" (the +30 is doubled by Weakness).

Run: python3 tests/test_cheer_on_to_glory.py
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


def hit(st, me, opp, attacker, target, amount):
    """One attack-damage swing through the chokepoint; returns damage dealt."""
    return fx.apply_attack_damage(ctx_for(st, me, opp, source=attacker), target, amount,
                                  owner=opp, source=attacker)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # It is recorded as a PASSIVE ability (handled at a chokepoint), not an activated one.
    check(("Cynthia's Roserade", "Cheer On to Glory") in fx.PASSIVE_ABILITIES,
          "Cheer On to Glory must be recorded in PASSIVE_ABILITIES")
    check(("Cynthia's Roserade", "Cheer On to Glory") not in fx.ABILITY_EFFECTS,
          "Cheer On to Glory is passive — it must NOT be an activated ABILITY_EFFECTS entry")

    # --- 1. One Benched Roserade: a Cynthia's attacker hits the opponent's Active for
    # +30. Dragapult ex has no Weakness and no Resistance, so the math is clean. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roserade"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    check(hit(st, a, b, chomp, b.active, 100) == 130,
          "one Benched Cynthia's Roserade must add +30 to a Cynthia's attacker's hit")

    # --- 2. Copies STACK — each Roserade is its own continuous Ability. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roserade")),
               InPlayPokemon(card=db.get("Cynthia's Roserade"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    check(hit(st, a, b, chomp, b.active, 100) == 160,
          "two Cynthia's Roserade must add +60 (each copy applies its own Ability)")

    # --- 3. "in play" includes the ACTIVE Spot: a Roserade attacking gets its own +30
    # (it is itself a Cynthia's Pokémon). Leaf Step's printed 80 -> 110. ---
    st, a, b = fresh_state(db)
    rose = InPlayPokemon(card=db.get("Cynthia's Roserade"))
    a.active = rose
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    check(hit(st, a, b, rose, b.active, 80) == 110,
          "an ACTIVE Cynthia's Roserade must boost its own attack (it is in play)")

    # --- 4. NEGATIVE: the attacker is not a Cynthia's Pokémon -> no boost, even with
    # Roserade benched. ---
    st, a, b = fresh_state(db)
    dwebble = InPlayPokemon(card=db.get("Dwebble"))
    a.active = dwebble
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roserade"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    check(hit(st, a, b, dwebble, b.active, 100) == 100,
          "a non-Cynthia's attacker must get no boost from Cheer On to Glory")

    # --- 5. NEGATIVE: "to your opponent's ACTIVE Pokémon" — a Benched target gets no
    # +30 (bench damage also skips W/R, which is the existing engine rule). ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roserade"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    victim = InPlayPokemon(card=db.get("Kyurem"))
    b.bench = [victim]
    check(hit(st, a, b, chomp, victim, 100) == 100,
          "a Benched target must never get the +30 (the card says Active)")

    # --- 6. NEGATIVE: "your" Cynthia's Pokémon — the OPPONENT's Roserade must not boost
    # my attacks. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.bench = [InPlayPokemon(card=db.get("Cynthia's Roserade"))]
    check(hit(st, a, b, chomp, b.active, 100) == 100,
          "the opponent's Cynthia's Roserade must not boost MY attacks")

    # --- 7. "before applying Weakness and Resistance": the +30 is inside the doubling.
    # Snorlax ex is Fighting ×2 and Cynthia's Garchomp ex is Fighting: (100+30)×2 = 260,
    # NOT 100×2+30 = 230. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roserade"))]
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))       # Fighting ×2
    check(hit(st, a, b, chomp, b.active, 100) == 260,
          "the +30 must be added BEFORE Weakness doubles ((100+30)×2 = 260)")

    # --- 8. Team Rocket's Watchtower ("Colorless Pokémon in play have no Abilities")
    # must NOT switch this off — Cynthia's Roserade is a GRASS Pokémon. This is the
    # precise scope of the suppression check, not a blanket one. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Team Rocket's Watchtower")
    st.stadium_owner = 1
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roserade"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    check(hit(st, a, b, chomp, b.active, 100) == 130,
          "Team Rocket's Watchtower only silences COLORLESS Pokémon — a Grass Roserade "
          "keeps Cheer On to Glory")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_cheer_on_to_glory.py: all checks passed — +30 only for your Cynthia's "
          "attackers into the opponent's Active, stacking per Roserade, applied before "
          "Weakness")


if __name__ == "__main__":
    main()
