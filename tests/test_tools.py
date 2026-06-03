#!/usr/bin/env python3
"""
test_tools.py — Pokémon Tools (§2.8), Special Energy (§2.10), passive Agile.

Air Balloon (retreat −2), Powerglass (end-of-turn Energy from discard), Charmander
Agile (no retreat cost with no Energy), Enriching Energy (provides Colorless, draw
4 on attach). Run from project root:  python3 tests/test_tools.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    a.turns_taken = b.turns_taken = 5
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    FIRE = db.get("Basic Fire Energy")
    PULT = db.get("Dragapult ex")          # retreat cost 2

    # --- Air Balloon: retreat cost −2. ---
    mon = InPlayPokemon(card=PULT, energy=[FIRE, FIRE])
    base = game.retreat_cost(mon)
    mon.tool = db.get("Air Balloon")
    check(game.retreat_cost(mon) == max(0, base - 2),
          f"Air Balloon should reduce retreat by 2 (base {base} -> {game.retreat_cost(mon)})")

    # --- Charmander Agile: no retreat cost when no Energy attached. ---
    charm = InPlayPokemon(card=db.get("Charmander"))       # no energy
    check(game.retreat_cost(charm) == 0, "Agile: no Energy -> retreat cost 0")
    charm.energy = [FIRE]
    check(game.retreat_cost(charm) == game.retreat_cost(InPlayPokemon(card=db.get("Charmander"), energy=[FIRE])),
          "Agile inactive with Energy attached")

    # --- Powerglass: end of turn, if holder is Active, attach a Basic Energy from discard. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT, tool=db.get("Powerglass"))
    a.discard = [FIRE]
    st.active_index = 0
    game.end_turn(st)
    check(FIRE in a.active.energy and FIRE not in a.discard,
          "Powerglass should move a Basic Energy from discard onto the Active")

    # --- Enriching Energy: provides Colorless + draw 4 on attach from hand. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT)
    enrich = db.get("Enriching Energy")
    a.hand = [enrich]
    a.deck = [db.get("Dreepy")] * 10
    st.active_index = 0
    game.apply_action(st, game.Action("attach_energy", hand_index=0, target_index=-1))
    check(enrich in a.active.energy, "Enriching Energy should attach")
    check(len(a.hand) == 4, f"Enriching Energy should draw 4 on attach (hand={len(a.hand)})")
    check("Colorless" in a.active.provided_types(), "Enriching Energy should provide Colorless")

    # --- greedy attaches an available Tool. ---
    from src.engine.agents import GreedyAgent
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Flutter Mane"))
    a.hand = [db.get("Air Balloon")]
    b.active = InPlayPokemon(card=PULT)
    act = GreedyAgent().choose(st)
    check(act.kind == "attach_tool", f"greedy should attach an available Tool, chose {act.kind!r}")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Tools (Air Balloon, Powerglass) + Agile + Enriching Energy all match card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
