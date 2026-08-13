#!/usr/bin/env python3
"""
test_crustle_modern_tech.py — the three cards added for the Crustle modernization
(Hero's Cape, Mist Energy, Spiky Energy), plus the registered "crustle_modern" deck.

Run: python3 tests/test_crustle_modern_tech.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.decks import DECKS
from src.engine.legality import validate_deck


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None, effect_kind="attack"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng,
                            effect_kind=effect_kind)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 0. the deck itself. ---
    check("crustle_modern" in DECKS, "crustle_modern must be registered")
    recipe = DECKS["crustle_modern"]
    check(sum(n for _, n in recipe) == 60, f"must be 60 cards, got {sum(n for _, n in recipe)}")
    check(validate_deck(db, recipe) == [], f"must be legal, got {validate_deck(db, recipe)}")

    # --- 1. Hero's Cape: +100 HP, no holder restriction. ---
    st, a, b = fresh_state(db)
    dwebble = InPlayPokemon(card=db.get("Dwebble"))
    a.active = dwebble
    dwebble.tool = db.get("Hero's Cape")
    fx.refresh_hp_modifiers(st)
    check(dwebble.max_hp == (dwebble.card.hp or 0) + 100,
          f"Hero's Cape must add +100 max HP, got {dwebble.max_hp} vs printed {dwebble.card.hp}")

    # --- 2. Mist Energy: prevents attack EFFECTS (not damage), any holder type. ---
    st, a, b = fresh_state(db)
    mon = InPlayPokemon(card=db.get("Dwebble"))
    mon.energy = [db.get("Mist Energy")]
    a.active = mon
    attacker = InPlayPokemon(card=db.get("Beldum"))
    b.active = attacker
    ctx = ctx_for(st, b, a, source=attacker, effect_kind="attack")
    placed = fx.place_counters(ctx, mon, 5, owner=a)
    check(placed == 0, f"Mist Energy must block attack-effect counters, got {placed} placed")
    check(fx.mist_energy_prevents_effect(st, mon, attacker),
          "mist_energy_prevents_effect must report True for a Mist-Energy-holding target")

    # NEGATIVE: an ABILITY's counters (effect_kind='ability') still land.
    st, a, b = fresh_state(db)
    mon2 = InPlayPokemon(card=db.get("Dwebble"))
    mon2.energy = [db.get("Mist Energy")]
    a.active = mon2
    attacker2 = InPlayPokemon(card=db.get("Beldum"))
    b.active = attacker2
    ctx2 = ctx_for(st, b, a, source=attacker2, effect_kind="ability")
    placed2 = fx.place_counters(ctx2, mon2, 3, owner=a)
    check(placed2 == 3, f"Mist Energy must NOT block an ABILITY's counters, got {placed2}")

    # NEGATIVE: no Mist Energy attached -> no prevention.
    st, a, b = fresh_state(db)
    mon3 = InPlayPokemon(card=db.get("Dwebble"))
    a.active = mon3
    attacker3 = InPlayPokemon(card=db.get("Beldum"))
    b.active = attacker3
    ctx3 = ctx_for(st, b, a, source=attacker3, effect_kind="attack")
    placed3 = fx.place_counters(ctx3, mon3, 4, owner=a)
    check(placed3 == 4, f"without Mist Energy, counters must land normally, got {placed3}")

    # --- 3. Spiky Energy: Active-only standing retaliation, 2 counters (20 damage),
    # fires even on a KO, does NOT fire for a benched holder. ---
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Dwebble"))
    holder.energy = [db.get("Spiky Energy")]
    a.active = holder
    attacker4 = InPlayPokemon(card=db.get("Beldum"))
    b.active = attacker4
    ctx4 = ctx_for(st, b, a, source=attacker4)
    dealt = fx.apply_attack_damage(ctx4, holder, 400, owner=a, source=attacker4)  # KO-sized
    check(dealt == 400, f"the incoming damage must still land in full, got {dealt}")
    check(holder.is_knocked_out, "holder must actually be KO'd by 400 damage")
    check(attacker4.damage == 20,
          f"Spiky Energy must place 2 counters (20 dmg) on the attacker even on a KO, got {attacker4.damage}")

    # NEGATIVE: holder on the BENCH -> no retaliation.
    st, a, b = fresh_state(db)
    bench_holder = InPlayPokemon(card=db.get("Dwebble"))
    bench_holder.energy = [db.get("Spiky Energy")]
    a.active = InPlayPokemon(card=db.get("Crustle"))
    a.bench = [bench_holder]
    attacker5 = InPlayPokemon(card=db.get("Beldum"))
    b.active = attacker5
    ctx5 = ctx_for(st, b, a, source=attacker5)
    fx.apply_attack_damage(ctx5, bench_holder, 30, owner=a, source=attacker5)
    check(attacker5.damage == 0, "Spiky Energy must not retaliate for a benched holder")

    # --- 4. NEGATIVE: an opponent's own Spiky Energy attacking doesn't retaliate onto
    # itself (source is target's own controller's Pokémon -> not applicable here, but
    # confirm the owner-mismatch guard: retaliation only fires against the OPPOSING
    # attacker, never when source and target share a controller). ---
    st, a, b = fresh_state(db)
    same_owner_target = InPlayPokemon(card=db.get("Dwebble"))
    same_owner_target.energy = [db.get("Spiky Energy")]
    same_owner_source = InPlayPokemon(card=db.get("Crustle"))
    a.active = same_owner_target
    a.bench = [same_owner_source]
    ctx6 = ctx_for(st, a, b, source=same_owner_source)
    fx.apply_attack_damage(ctx6, same_owner_target, 10, owner=a, source=same_owner_source)
    check(same_owner_source.damage == 0, "Spiky Energy must not retaliate against your own Pokémon")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_crustle_modern_tech.py: all checks passed — Hero's Cape, Mist Energy, "
          "Spiky Energy, and crustle_modern all behave correctly")


if __name__ == "__main__":
    main()
