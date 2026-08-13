#!/usr/bin/env python3
"""
test_tourney_tech.py — Bianca's Devotion and Nighttime Mine, two real tech pieces
pulled from actual tournament decklists (Rahul Reddy's Crustle at the Indianapolis
Regional final; Cerys Jones's Alakazam/Dudunsparce, same event) while ground-truthing
the simulator against real tournament play. Card text quoted from data/standard_pool.json.

Covers:
  - Bianca's Devotion (sv5-142, Supporter): "Heal all damage from 1 of your Pokémon
    that has 30 HP or less remaining."
  - Nighttime Mine (me2pt5-197, Stadium): "Attacks used by each Tera Pokémon in play
    (both yours and your opponent's) cost [C] more."

Run from project root:  python3 tests/test_tourney_tech.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card, CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


def _low_hp_card(hp=30):
    """A synthetic Basic with a low max HP — real cards rarely print <=30 HP in
    the current pool, so this is the only clean way to test the "undamaged but
    already at/under the 30-remaining-HP threshold" edge case."""
    return Card(id="test-lowhp", name="Test Lowhp Basic", supertype="Pokémon",
               subtypes=("Basic",), hp=hp, types=("Colorless",), evolves_from=None,
               evolves_to=(), abilities=(), attacks=(), rules=(), weaknesses=(),
               resistances=(), retreat_cost=1, regulation_mark="H")


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source,
                            db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # =================================================================== #
    # BIANCA'S DEVOTION
    # =================================================================== #

    # --- 1a. POSITIVE: a Pokémon at exactly 30 remaining HP is a valid target and
    # gets fully healed. ---
    st, a, b = fresh_state(db)
    mon = InPlayPokemon(card=db.get("Crustle"))          # 150 HP
    mon.damage = 120                                      # remaining_hp = 30
    a.active = mon
    check(mon.remaining_hp == 30, "setup: expected exactly 30 remaining HP")
    check(fx._TRAINER_CAN_PLAY["Bianca's Devotion"](st, a),
          "can_play should be True at exactly 30 remaining HP")
    ok = fx._biancas_devotion(ctx_for(st, a, b))
    check(ok, "Bianca's Devotion should report success")
    check(mon.damage == 0, f"expected fully healed (damage=0), got {mon.damage}")

    # --- 1b. NEGATIVE: a Pokémon at 40 remaining HP (above the 30 threshold) is
    # NOT a valid target. ---
    st, a, b = fresh_state(db)
    mon2 = InPlayPokemon(card=db.get("Crustle"))
    mon2.damage = 110                                      # remaining_hp = 40
    a.active = mon2
    check(not fx._TRAINER_CAN_PLAY["Bianca's Devotion"](st, a),
          "can_play should be False at 40 remaining HP (above threshold)")
    ok = fx._biancas_devotion(ctx_for(st, a, b))
    check(not ok, "Bianca's Devotion should no-op with no qualifying target")
    check(mon2.damage == 110, "damage must be untouched when no-op")

    # --- 1c. NEGATIVE: no damage at all -> not a valid target (remaining_hp<=30
    # alone isn't enough; must also have damage>0 — healing an undamaged Pokémon
    # is a no-op even if its max HP happens to be <=30). Uses a synthetic 30-HP
    # Basic since real cards in the current pool rarely print that low. ---
    st, a, b = fresh_state(db)
    mon3 = InPlayPokemon(card=_low_hp_card(30))            # 30 HP, undamaged
    a.active = mon3
    check(mon3.damage == 0 and mon3.remaining_hp == 30,
          "setup: synthetic 30 HP mon should be undamaged with remaining_hp exactly 30")
    check(not fx._TRAINER_CAN_PLAY["Bianca's Devotion"](st, a),
          "can_play must be False for an undamaged mon even if remaining_hp<=30")
    ok = fx._biancas_devotion(ctx_for(st, a, b))
    check(not ok, "Bianca's Devotion must no-op on an undamaged (damage=0) target")

    # --- 1d. Multiple candidates: picks the LOWEST remaining HP (most in need). ---
    st, a, b = fresh_state(db)
    active = InPlayPokemon(card=db.get("Crustle"))
    active.damage = 130                                    # remaining_hp = 20
    bench_mon = InPlayPokemon(card=db.get("Crustle"))
    bench_mon.damage = 125                                 # remaining_hp = 25
    a.active = active
    a.bench = [bench_mon]
    ok = fx._biancas_devotion(ctx_for(st, a, b))
    check(ok, "Bianca's Devotion should fire with 2 candidates")
    check(active.damage == 0 and bench_mon.damage == 125,
          "must heal the LOWEST remaining_hp candidate (active, 20hp), not the bench one (25hp)")

    # --- 1e. A KO'd Pokémon (remaining_hp <= 0) is never a candidate — shouldn't
    # crash and shouldn't be "healed" (it's already off the board conceptually). ---
    st, a, b = fresh_state(db)
    dead = InPlayPokemon(card=db.get("Dwebble"))
    dead.damage = 999                                      # remaining_hp <= 0
    a.active = dead
    check(not fx._TRAINER_CAN_PLAY["Bianca's Devotion"](st, a),
          "a KO'd (remaining_hp<=0) mon must not count as a candidate")

    # =================================================================== #
    # NIGHTTIME MINE
    # Pool text: "Attacks used by each Tera Pokémon in play (both yours and your
    # opponent's) cost [C] more."
    # =================================================================== #

    # --- 2a. POSITIVE: a Tera Pokémon's attack costs 1 more Colorless while
    # Nighttime Mine is in play. Dragapult ex is Tera+ex (subtypes include 'Tera').
    # ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Nighttime Mine")
    st.stadium_owner = 0
    dragapult = InPlayPokemon(card=db.get("Dragapult ex"))
    atk = next(x for x in dragapult.card.attacks if x.name == "Phantom Dive")
    base_colorless = sum(1 for s in atk.cost if s == "Colorless")
    eff = fx.effective_cost(st, dragapult, atk)
    eff_colorless = sum(1 for s in eff if s == "Colorless")
    check("Tera" in dragapult.card.subtypes, "setup: Dragapult ex must be Tera-typed")
    check(eff_colorless == base_colorless + 1,
          f"expected +1 Colorless under Nighttime Mine, got base={base_colorless} eff={eff_colorless}")
    typed_before = tuple(s for s in atk.cost if s != "Colorless")
    typed_after = tuple(s for s in eff if s != "Colorless")
    check(typed_before == typed_after, "typed (non-Colorless) symbols must be untouched")

    # --- 2b. NEGATIVE: a non-Tera Pokémon's attack cost is unaffected. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Nighttime Mine")
    st.stadium_owner = 0
    crustle = InPlayPokemon(card=db.get("Crustle"))
    atk2 = next(x for x in crustle.card.attacks if x.name == "Superb Scissors")
    check("Tera" not in crustle.card.subtypes, "setup: Crustle must NOT be Tera-typed")
    eff2 = fx.effective_cost(st, crustle, atk2)
    check(eff2 == atk2.cost, "non-Tera attacker's cost must be unaffected by Nighttime Mine")

    # --- 2c. NEGATIVE: without Nighttime Mine in play, no increase (even for a
    # Tera Pokémon). ---
    st, a, b = fresh_state(db)
    st.stadium = None
    dragapult2 = InPlayPokemon(card=db.get("Dragapult ex"))
    atk3 = next(x for x in dragapult2.card.attacks if x.name == "Phantom Dive")
    eff3 = fx.effective_cost(st, dragapult2, atk3)
    check(eff3 == atk3.cost, "no Stadium in play -> cost must be exactly the printed cost")

    # --- 2d. SYMMETRY: Nighttime Mine taxes BOTH players' Tera Pokémon, not just
    # whoever didn't play it. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Nighttime Mine")
    st.stadium_owner = 1                                   # B played it
    dragapult3 = InPlayPokemon(card=db.get("Dragapult ex"))   # on side A
    atk4 = next(x for x in dragapult3.card.attacks if x.name == "Phantom Dive")
    eff4 = fx.effective_cost(st, dragapult3, atk4)
    eff4_colorless = sum(1 for s in eff4 if s == "Colorless")
    base4_colorless = sum(1 for s in atk4.cost if s == "Colorless")
    check(eff4_colorless == base4_colorless + 1,
          "Nighttime Mine must tax the OWNER's own Tera Pokémon too, not just the opponent's")

    # --- 2e. Integration: the extra Colorless actually gates legal_actions/can_pay_cost
    # (not just effective_cost in isolation). Give Dragapult ex exactly enough energy
    # for the PRINTED cost but one short of the Nighttime-Mine-inflated cost. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Nighttime Mine")
    st.stadium_owner = 0
    dragapult4 = InPlayPokemon(card=db.get("Dragapult ex"))
    atk5 = next(x for x in dragapult4.card.attacks if x.name == "Phantom Dive")
    check(atk5.cost == ("Fire", "Psychic"), f"setup: expected Phantom Dive cost ('Fire','Psychic'), got {atk5.cost}")
    dragapult4.energy = [db.get("Basic Fire Energy"), db.get("Basic Psychic Energy")]   # printed cost exactly
    a.active = dragapult4
    inflated = fx.effective_cost(st, dragapult4, atk5)
    check(not game.can_pay_cost(dragapult4, inflated),
          "with exactly the PRINTED energy count, the Nighttime-Mine-inflated cost must be unaffordable")
    dragapult4.energy.append(db.get("Basic Psychic Energy"))               # +1 to cover the tax
    check(game.can_pay_cost(dragapult4, fx.effective_cost(st, dragapult4, atk5)),
          "with printed cost + 1, the inflated cost must now be affordable")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_tourney_tech.py: all checks passed (Bianca's Devotion + Nighttime Mine)")


if __name__ == "__main__":
    main()
