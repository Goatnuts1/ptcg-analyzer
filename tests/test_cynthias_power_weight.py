#!/usr/bin/env python3
"""
test_cynthias_power_weight.py — Cynthia's Power Weight (sv10 162, Pokémon Tool):
"The Cynthia's Pokémon this card is attached to gets +70 HP."

An HP-CHANGING effect, so it must go through the DERIVED `hp_modifier` path
(TOOL_HP_MODIFIERS -> effects.refresh_hp_modifiers), never an accumulating write —
the same rule Gravity Mountain's −30 follows. The interesting cases are the ones a
naive "+70 on attach" implementation gets wrong: a non-Cynthia's holder, a double
refresh, losing the Tool, and stacking with a Stadium HP modifier.

Run: python3 tests/test_cynthias_power_weight.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import Action, apply_action


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    weight = db.get("Cynthia's Power Weight")

    check("Cynthia's Power Weight" in fx.TOOL_IMPLEMENTED,
          "Cynthia's Power Weight must be recorded in TOOL_IMPLEMENTED")
    check("Pokémon Tool" in weight.subtypes,
          "the card must be a Pokémon Tool (it is attached, not played as an Item)")

    # --- 1. Attached to a Cynthia's Pokémon: +70 max HP. Cynthia's Gible is 70 HP. ---
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    gible.tool = weight
    a.active = gible
    fx.refresh_hp_modifiers(st)
    check(gible.max_hp == 140, f"70 HP + 70 = 140 max HP, got {gible.max_hp}")
    check(gible.remaining_hp == 140, f"remaining HP must follow max HP, got {gible.remaining_hp}")

    # --- 2. DERIVED, never accumulated: refreshing again must not add another +70. ---
    fx.refresh_hp_modifiers(st)
    fx.refresh_hp_modifiers(st)
    check(gible.max_hp == 140,
          f"hp_modifier must be recomputed from scratch, not accumulated; got {gible.max_hp}")

    # --- 3. NEGATIVE: a holder that is NOT a Cynthia's Pokémon gets nothing. The Tool is
    # legal to attach to anything; the +70 clause names Cynthia's Pokémon only. ---
    st, a, b = fresh_state(db)
    dwebble = InPlayPokemon(card=db.get("Dwebble"))     # 70 HP, not a Cynthia's Pokémon
    dwebble.tool = weight
    a.active = dwebble
    fx.refresh_hp_modifiers(st)
    check(dwebble.max_hp == 70,
          f"a non-Cynthia's holder must stay at printed HP, got {dwebble.max_hp}")

    # --- 4. NEGATIVE: a Cynthia's Pokémon with NO Tool (or a different Tool) gets
    # nothing. ---
    st, a, b = fresh_state(db)
    bare = InPlayPokemon(card=db.get("Cynthia's Gible"))
    balloon = InPlayPokemon(card=db.get("Cynthia's Gible"))
    balloon.tool = db.get("Air Balloon")
    a.active = bare
    a.bench = [balloon]
    fx.refresh_hp_modifiers(st)
    check(bare.max_hp == 70, f"no Tool -> printed HP, got {bare.max_hp}")
    check(balloon.max_hp == 70, f"a different Tool -> printed HP, got {balloon.max_hp}")

    # --- 5. Stacks with a Stadium HP modifier, both derived from the same refresh:
    # Cynthia's Garchomp ex is a Stage 2 (330 HP), so under Gravity Mountain (−30) with
    # the Tool it lands on 330 − 30 + 70 = 370. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Gravity Mountain")
    st.stadium_owner = 0
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    chomp.tool = weight
    a.active = chomp
    fx.refresh_hp_modifiers(st)
    check(chomp.max_hp == 370,
          f"330 − 30 (Gravity Mountain) + 70 (Power Weight) = 370, got {chomp.max_hp}")

    # --- 6. Losing the Tool takes the HP back — and if that drops max HP to at-or-below
    # the damage already on the Pokémon, it is Knocked Out on the next sweep. This is the
    # case an accumulate-on-attach implementation silently gets wrong. ---
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    gible.tool = weight
    gible.damage = 130
    a.active = gible
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roselia"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.prizes = [db.get("Basic Fighting Energy")] * 6
    fx.refresh_hp_modifiers(st)
    check(not gible.is_knocked_out,
          "130 damage on a 140-HP (70+70) Gible must NOT be a knockout")
    gible.tool = None                       # e.g. the Tool was discarded
    fx.refresh_hp_modifiers(st)
    check(gible.max_hp == 70, f"the +70 must be given back, got {gible.max_hp}")
    check(gible.is_knocked_out,
          "with the Tool gone, 130 damage on a 70-HP Gible must be a knockout")
    fx.process_knockouts(st)
    check(a.active is not None and a.active.card.name == "Cynthia's Roselia",
          "process_knockouts must sweep it and promote the bencher")
    check(any(c.name == "Cynthia's Power Weight" for c in a.discard) is False,
          "the Tool was already detached here, so it must not be double-discarded")

    # --- 7. The LIVE path: attaching the Tool via the engine action refreshes max HP
    # immediately (agents/evaluation read remaining_hp before the next KO sweep). ---
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.active = gible
    a.hand = [weight]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    apply_action(st, Action("attach_tool", hand_index=0, target_index=-1))
    check(gible.tool is not None and gible.tool.name == "Cynthia's Power Weight",
          "the Tool must actually be attached by the engine action")
    check(gible.max_hp == 140,
          f"attach_tool must refresh hp_modifier right away, got {gible.max_hp}")

    # --- 8. A KO'd holder sends the Tool to the discard pile (existing engine rule, but
    # it matters here: the Tool must not be lost or kept in play). ---
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    gible.tool = weight
    gible.damage = 200                      # past 140
    a.active = gible
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roselia"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.prizes = [db.get("Basic Fighting Energy")] * 6
    fx.process_knockouts(st)
    check(any(c.name == "Cynthia's Power Weight" for c in a.discard),
          "the Tool must go to its owner's discard pile when the holder is KO'd")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_cynthias_power_weight.py: all checks passed — +70 HP only for a Cynthia's "
          "holder, derived (never accumulated), stacks with Gravity Mountain, and given "
          "back when the Tool leaves")


if __name__ == "__main__":
    main()
