#!/usr/bin/env python3
"""
test_legacy_energy.py — Legacy Energy (Special Energy, ACE SPEC; TWM 167 / pool
id sv6-167). Two clauses, both under test:

  1. "As long as this card is attached to a Pokémon, it provides every type of Energy
     but provides only 1 Energy at a time."
     -> InPlayPokemon.provided_types() emits ONE "Any" wildcard unit, UNCONDITIONALLY.
     Unlike Prism Energy ("if attached to a Basic") and Neo Upper Energy ("if attached
     to a Stage 2", 2 at a time) there is no stage clause and no 2-at-a-time amount, so
     a Basic, a Stage 1 and a Stage 2 all get exactly one wildcard.
     SCOPE (same as the other wildcard energy): this is the ATTACK-COST path only.
     energy_count() still counts CARDS, so retreat cost is unaffected.

  2. "If the Pokémon this card is attached to is Knocked Out by damage from an attack
     from your opponent's Pokémon, that player takes 1 fewer Prize card. This effect of
     your Legacy Energy can't be applied more than once per game."
     -> effects._ko_cleanup, using the KO-CAUSE flag that apply_attack_damage sets
     (InPlayPokemon.koed_by_opponent_attack_damage) and the per-player, per-game budget
     PlayerState.legacy_energy_prize_reduction_used.
     The cause matters: a KO by placed damage counters, or a self-KO, is NOT "damage
     from an attack" and must NOT reduce prizes. Those negatives are asserted here.

Run: python3 tests/test_legacy_energy.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import can_pay_cost


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    a.prizes = [db.get("Basic Psychic Energy")] * 6
    b.prizes = [db.get("Basic Psychic Energy")] * 6
    return st, a, b


def ctx_for(st, me, opp, source=None, kind="attack"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=st.rng, effect_kind=kind)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    LEGACY = db.get("Legacy Energy")

    check("Legacy Energy" in fx.SPECIAL_ENERGY_IMPLEMENTED,
          "Legacy Energy must be recorded as an implemented Special Energy")
    check("ACE SPEC" in LEGACY.subtypes, "sanity: Legacy Energy is an ACE SPEC card")

    # ----------------------------------------------------------------- #
    # 1. ENERGY PROVISION — one "Any" wildcard, on any stage.
    # ----------------------------------------------------------------- #
    basic = InPlayPokemon(card=db.get("Dhelmise (PBL)"))          # Basic
    stage1 = InPlayPokemon(card=db.get("Banette (PBL)"))          # Stage 1
    stage2 = InPlayPokemon(card=db.get("Dragapult ex"))           # Stage 2
    for mon, label in ((basic, "Basic"), (stage1, "Stage 1"), (stage2, "Stage 2")):
        mon.energy = [LEGACY]
        check(mon.provided_types() == ["Any"],
              f"one Legacy Energy on a {label} must provide exactly one 'Any' wildcard, "
              f"got {mon.provided_types()}")

    # it really pays a TYPED symbol (that's what "every type of Energy" means)...
    solo = InPlayPokemon(card=db.get("Banette (PBL)"))
    solo.energy = [LEGACY]
    check(can_pay_cost(solo, ("Psychic",)) is True,
          "one Legacy Energy must pay Puppet Pull's [P]")
    check(can_pay_cost(solo, ("Fighting",)) is True,
          "'every type of Energy' — it pays any single typed symbol, not just Psychic")
    # ...but only ONE at a time, so it cannot pay a 2-symbol cost alone.
    check(can_pay_cost(solo, ("Psychic", "Colorless")) is False,
          "'provides only 1 Energy at a time' — one copy must NOT pay a 2-symbol cost")
    # NEGATIVE: no 2-at-a-time upgrade on a Stage 2 (that is Neo Upper Energy, not this).
    s2 = InPlayPokemon(card=db.get("Dragapult ex"))
    s2.energy = [LEGACY]
    check(can_pay_cost(s2, ("Psychic", "Psychic")) is False,
          "Legacy Energy has no Stage 2 clause — it never provides 2 at a time")
    # SCOPE: energy_count() still counts CARDS (retreat cost is unaffected).
    check(solo.energy_count() == 1,
          "energy_count() counts CARDS — the wildcard does not inflate it")

    # ----------------------------------------------------------------- #
    # 2. THE PRIZE CLAUSE.
    # ----------------------------------------------------------------- #
    def ko_by_attack(victim_card="Lillie's Clefairy ex", attach_legacy=True):
        """B attacks A's Active to death with real attack damage. Returns
        (prizes B took, state, A)."""
        st, a, b = fresh_state(db)
        victim = InPlayPokemon(card=db.get(victim_card))
        if attach_legacy:
            victim.energy = [LEGACY]
        a.active = victim
        a.bench = [InPlayPokemon(card=db.get("Dhelmise (PBL)"))]
        attacker = InPlayPokemon(card=db.get("Dragapult ex"))
        b.active = attacker
        st.active_index = 1
        ctx = ctx_for(st, b, a, source=attacker)
        fx.apply_attack_damage(ctx, victim, 500, owner=a, source=attacker)
        before = len(b.prizes)
        fx.process_knockouts(st)
        return before - len(b.prizes), st, a

    # 2a. POSITIVE: a 2-prize Pokémon ex KO'd by attack damage awards only 1.
    took, st, a = ko_by_attack()
    check(took == 1,
          f"Lillie's Clefairy ex normally gives 2 Prizes; with Legacy Energy attached "
          f"and KO'd by an attack the opponent takes 1, got {took}")
    check(a.legacy_energy_prize_reduction_used is True,
          "the once-per-game budget must be consumed by the Pokémon's OWNER")

    # 2b. BASELINE: without Legacy Energy the same KO awards the full 2.
    took, _, _ = ko_by_attack(attach_legacy=False)
    check(took == 2, f"without Legacy Energy the ex must award its full 2 Prizes, got {took}")

    # 2c. a 1-prize Pokémon awards 0 ("1 fewer", floored at 0).
    took, _, _ = ko_by_attack(victim_card="Dhelmise (PBL)")
    check(took == 0,
          f"a 1-Prize Pokémon with Legacy Energy KO'd by an attack awards 0 Prizes, "
          f"got {took}")

    # 2d. ONCE PER GAME: a second Legacy-Energy KO for the same player is at full price.
    st, a, b = fresh_state(db)
    st.active_index = 1
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    first = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    first.energy = [LEGACY]
    second = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    second.energy = [LEGACY]
    a.active = first
    a.bench = [second, InPlayPokemon(card=db.get("Dhelmise (PBL)"))]
    ctx = ctx_for(st, b, a, source=attacker)
    fx.apply_attack_damage(ctx, first, 500, owner=a, source=attacker)
    n0 = len(b.prizes)
    fx.process_knockouts(st)
    took1 = n0 - len(b.prizes)
    ctx = ctx_for(st, b, a, source=attacker)
    fx.apply_attack_damage(ctx, second, 500, owner=a, source=attacker)
    n1 = len(b.prizes)
    fx.process_knockouts(st)
    took2 = n1 - len(b.prizes)
    check(took1 == 1 and took2 == 2,
          f"'can't be applied more than once per game' — first KO gives 1, the second "
          f"gives the full 2, got {took1} then {took2}")

    # 2e. NEGATIVE: KO'd by placed damage COUNTERS is not "damage from an attack".
    st, a, b = fresh_state(db)
    st.active_index = 1
    victim = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    victim.energy = [LEGACY]
    a.active = victim
    a.bench = [InPlayPokemon(card=db.get("Dhelmise (PBL)"))]
    dusknoir = InPlayPokemon(card=db.get("Dusknoir"))
    b.active = dusknoir
    ctx = ctx_for(st, b, a, source=dusknoir, kind="ability")
    fx.place_counters(ctx, victim, 19, owner=a)     # 190 = exactly lethal, as counters
    n0 = len(b.prizes)
    fx.process_knockouts(st)
    check(n0 - len(b.prizes) == 2,
          "a KO by placed damage COUNTERS is not 'damage from an attack' — the full 2 "
          "Prizes must be taken")
    check(a.legacy_energy_prize_reduction_used is False,
          "a counter-KO must not burn the once-per-game use either")

    # 2f. NEGATIVE: a SELF-KO is not a KO "from your opponent's Pokémon".
    st, a, b = fresh_state(db)
    selfko = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    selfko.energy = [LEGACY]
    a.active = selfko
    a.bench = [InPlayPokemon(card=db.get("Dhelmise (PBL)"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    selfko.damage = 190
    n0 = len(b.prizes)
    fx.process_knockouts(st)
    check(n0 - len(b.prizes) == 2,
          "a self-KO is not 'by damage from an attack from your opponent's Pokémon' — "
          "the opponent still takes 2")

    # 2g. NEGATIVE: the budget is PER PLAYER — A using theirs leaves B's intact.
    st, a, b = fresh_state(db)
    a.legacy_energy_prize_reduction_used = True
    check(b.legacy_energy_prize_reduction_used is False,
          "the once-per-game budget is tracked per player, not globally")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_legacy_energy.py: all checks passed — one unconditional 'Any' wildcard "
          "for attack costs, and exactly one 1-fewer-Prize reduction per game, only on "
          "a KO by an opponent's ATTACK DAMAGE")


if __name__ == "__main__":
    main()
