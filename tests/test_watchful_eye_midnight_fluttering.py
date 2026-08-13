#!/usr/bin/env python3
"""
test_watchful_eye_midnight_fluttering.py — the two Ability-lock passives the
hide_n_sneak list runs.

  Patrat (CRI 70) "Watchful Eye": "Damage counters on each Pokémon (both yours and
      your opponent's) can't be moved to other Pokémon."
      -> effects.damage_counter_move_blocked, consulted by Munkidori's Adrena-Brain
      (the engine's only counter-MOVE effect) and by its ABILITY_CAN_USE guard.
      PRECISION: it bans MOVING counters. It does not stop counters being PLACED, and
      it does not stop damage. Those are different things and this test pins that down.

  Flutter Mane "Midnight Fluttering": "As long as this Pokémon is in the Active Spot,
      your opponent's Active Pokémon has no Abilities, except for Midnight Fluttering."
      -> effects.ability_suppressed (_midnight_fluttering_suppressed). Both halves are
      Active-only, so a Benched Ability is untouched — which is why it cannot switch
      off a Benched Hide 'n' Sneak.

Also asserts the pool's OLD bare "Patrat" (White Flare, no Ability, Procurement) is
left exactly as it was.

Run: python3 tests/test_watchful_eye_midnight_fluttering.py
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


def ctx_for(st, me, opp, source=None, kind="ability"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=st.rng, effect_kind=kind)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # ----------------------------------------------------------------- #
    # 0. The prints.
    # ----------------------------------------------------------------- #
    patrat = db.get("Patrat (CRI)")
    check(patrat.hp == 70 and any(ab.name == "Watchful Eye" for ab in patrat.abilities),
          f"Patrat (CRI) must be the 70 HP Watchful Eye print, got {patrat.hp}/"
          f"{[ab.name for ab in patrat.abilities]}")
    check([a.name for a in patrat.attacks] == ["Bite"],
          f"Patrat (CRI)'s only attack is Bite — 'Procurement' belongs to the White "
          f"Flare print, got {[a.name for a in patrat.attacks]}")
    old = db.get("Patrat")
    check(not old.abilities and any(a.name == "Procurement" for a in old.attacks),
          "the pool's old bare 'Patrat' (White Flare, Procurement, no Ability) must be "
          "left untouched")

    # ----------------------------------------------------------------- #
    # 1. WATCHFUL EYE — counters can't be MOVED.
    # ----------------------------------------------------------------- #
    def adrena_setup(with_patrat_on, db=db):
        """Munkidori (B) tries to move counters off its own damaged Pokémon onto A's
        Active. `with_patrat_on` is None / "A" / "B" — which side has Patrat (CRI)."""
        st, a, b = fresh_state(db)
        munki = InPlayPokemon(card=db.get("Munkidori"))
        munki.energy = [db.get("Basic Darkness Energy")]
        donor = InPlayPokemon(card=db.get("Dreepy"))
        donor.damage = 30
        b.active, b.bench = munki, [donor]
        victim = InPlayPokemon(card=db.get("Dhelmise (PBL)"))    # 140 HP, no Ability
        a.active = victim
        if with_patrat_on == "A":
            a.bench = [InPlayPokemon(card=db.get("Patrat (CRI)"))]
        elif with_patrat_on == "B":
            b.bench.append(InPlayPokemon(card=db.get("Patrat (CRI)")))
        return st, a, b, munki, donor, victim

    # 1a. BASELINE (no Patrat): Adrena-Brain moves 3 counters across.
    st, a, b, munki, donor, victim = adrena_setup(None)
    fx._adrena_brain(ctx_for(st, b, a, source=munki))
    check(victim.damage == 30 and donor.damage == 0,
          f"baseline: Adrena-Brain should move 3 counters, got victim={victim.damage} "
          f"donor={donor.damage}")

    # 1b. POSITIVE: Patrat (CRI) on the DEFENDING side blanks the move entirely.
    st, a, b, munki, donor, victim = adrena_setup("A")
    check(fx.damage_counter_move_blocked(st) is True,
          "with Patrat (CRI) in play, damage_counter_move_blocked must be True")
    fx._adrena_brain(ctx_for(st, b, a, source=munki))
    check(victim.damage == 0 and donor.damage == 30,
          f"Watchful Eye must stop the move outright — no counters arrive AND none "
          f"leave the donor, got victim={victim.damage} donor={donor.damage}")

    # 1c. POSITIVE: it is SYMMETRIC — the Ability's own controller is locked too.
    st, a, b, munki, donor, victim = adrena_setup("B")
    fx._adrena_brain(ctx_for(st, b, a, source=munki))
    check(victim.damage == 0 and donor.damage == 30,
          "'both yours and your opponent's' — Watchful Eye locks its OWN controller's "
          "counter movement too")

    # 1d. the usability guard hides the now-useless Ability from the engine.
    st, a, b, munki, donor, victim = adrena_setup("A")
    guard = fx.get_ability_can_use("Munkidori", "Adrena-Brain")
    check(guard is not None and guard(st, b, munki) is False,
          "with Watchful Eye in play, Adrena-Brain must not even be offered")
    st, a, b, munki, donor, victim = adrena_setup(None)
    check(guard(st, b, munki) is True,
          "without Watchful Eye, Adrena-Brain must still be offered")

    # 1e. NEGATIVE: PLACING counters is not MOVING them — Watchful Eye does nothing
    #     to Phantom Dive / Cursed Blast / Furtive Drop.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    target = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    a.bench = [target, InPlayPokemon(card=db.get("Patrat (CRI)"))]
    pult = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = pult
    ctx = ctx_for(st, b, a, source=pult, kind="attack")
    fx._phantom_dive(ctx)
    check(sum(m.damage for m in a.bench) == 60,
          f"Watchful Eye must NOT block counters being PLACED — only counters being "
          f"moved; all 6 Phantom Dive counters should have landed, got "
          f"{sum(m.damage for m in a.bench)}")

    # 1f. NEGATIVE: it does not touch damage either.
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Patrat (CRI)"))     # 70 HP
    a.active = holder
    foe = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = foe
    ctx = ctx_for(st, b, a, source=foe, kind="attack")
    check(fx.apply_attack_damage(ctx, holder, 50, owner=a, source=foe) == 50,
          "Watchful Eye is not damage prevention — attack damage lands in full")

    # ----------------------------------------------------------------- #
    # 2. MIDNIGHT FLUTTERING — the opposing ACTIVE has no Abilities.
    # ----------------------------------------------------------------- #
    # 2a. POSITIVE: an Active Flutter Mane switches off the opposing ACTIVE's Ability,
    #     so a Hide 'n' Sneak Pokémon stuck in the Active Spot loses its protection.
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Banette (PBL)"))
    a.active = holder
    fm = InPlayPokemon(card=db.get("Flutter Mane"))
    b.active = fm
    check(fx.ability_suppressed(st, holder) is True,
          "an Active Flutter Mane must suppress the opposing ACTIVE's Ability")
    ctx = ctx_for(st, b, a, source=fm, kind="attack")
    check(fx.place_counters(ctx, holder, 2, owner=a) == 2,
          "with Hide 'n' Sneak suppressed by Midnight Fluttering, the counters must land")

    # 2b. NEGATIVE: only the ACTIVE loses its Ability — a Benched Hide 'n' Sneak keeps it.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    benched = InPlayPokemon(card=db.get("Shuppet (PBL)"))
    a.bench = [benched]
    fm = InPlayPokemon(card=db.get("Flutter Mane"))
    b.active = fm
    check(fx.ability_suppressed(st, benched) is False,
          "Midnight Fluttering names the opposing ACTIVE only — a Benched Ability "
          "is untouched")
    ctx = ctx_for(st, b, a, source=fm, kind="attack")
    check(fx.place_counters(ctx, benched, 2, owner=a) == 0,
          "a BENCHED Hide 'n' Sneak keeps working under an opposing Flutter Mane")

    # 2c. NEGATIVE: a BENCHED Flutter Mane suppresses nothing ("As long as this
    #     Pokémon is in the Active Spot").
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Banette (PBL)"))
    a.active = holder
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.bench = [InPlayPokemon(card=db.get("Flutter Mane"))]
    check(fx.ability_suppressed(st, holder) is False,
          "a BENCHED Flutter Mane must not suppress anything")

    # 2d. "except for Midnight Fluttering" — a mirror keeps its own Ability, and this
    #     is also what makes the check terminate instead of recursing.
    st, a, b = fresh_state(db)
    fm_a = InPlayPokemon(card=db.get("Flutter Mane"))
    fm_b = InPlayPokemon(card=db.get("Flutter Mane"))
    a.active, b.active = fm_a, fm_b
    check(fx.ability_suppressed(st, fm_a) is False and fx.ability_suppressed(st, fm_b) is False,
          "'except for Midnight Fluttering' — two facing Flutter Mane both keep theirs")

    # 2e. the Stadium lock still applies to Flutter Mane's victim independently, and a
    #     Flutter Mane that IS Watchtower-suppressed projects nothing. (Flutter Mane is
    #     Psychic, so use a Colorless holder for the Stadium half.)
    st, a, b = fresh_state(db)
    colorless = InPlayPokemon(card=db.get("Dudunsparce"))
    a.active = colorless
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.stadium = db.get("Team Rocket's Watchtower")
    st.stadium_owner = 1
    check(fx.ability_suppressed(st, colorless) is True,
          "Team Rocket's Watchtower must still suppress a Colorless Pokémon's Ability")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_watchful_eye_midnight_fluttering.py: all checks passed — Watchful Eye "
          "blocks counter MOVEMENT only (symmetric, both players), and Midnight "
          "Fluttering blanks the opposing ACTIVE's Ability only")


if __name__ == "__main__":
    main()
