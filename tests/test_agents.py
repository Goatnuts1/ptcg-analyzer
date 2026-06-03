#!/usr/bin/env python3
"""
test_agents.py — the AGENT actually plays the cards we implement.

A recurring failure mode (found twice in review): an effect is implemented and
unit-tested, but the agent has no branch to play it, so it's silently INERT in
live games and the matchup number is wrong (Battle Cage; then the whole draw/
search engine). These guards assert greedy exercises the consistency engine.

Run from project root:  python3 tests/test_agents.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine.agents import GreedyAgent


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    a.turns_taken = 5
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    def hand_card(st, p):
        return p.hand[GreedyAgent().choose(st).hand_index]

    # greedy plays a draw Supporter when hand is low and one is offered.
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Flutter Mane"))   # no energy -> can't attack
    a.hand = [db.get("Lillie's Determination")]
    a.deck = [db.get("Dreepy")] * 10
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    act = GreedyAgent().choose(st)
    check(act.kind == "play_trainer" and a.hand[act.hand_index].name == "Lillie's Determination",
          f"greedy should play Lillie's Determination, chose {act.kind!r}")

    # greedy plays a consistency Item (Poké Pad) when offered.
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Flutter Mane"))
    a.hand = [db.get("Poké Pad")]
    a.deck = [db.get("Dreepy")] * 5        # a non-Rule-Box Pokémon to find
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    act = GreedyAgent().choose(st)
    check(act.kind == "play_trainer" and a.hand[act.hand_index].name == "Poké Pad",
          f"greedy should play Poké Pad, chose {act.kind!r}")

    # greedy plays a Stadium when offered (regression of the Battle Cage bug).
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Flutter Mane"))
    a.bench = [InPlayPokemon(card=db.get("Dreepy")) for _ in range(3)]
    a.hand = [db.get("Battle Cage")]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    act = GreedyAgent().choose(st)
    check(act.kind == "play_stadium", f"greedy should play a Stadium, chose {act.kind!r}")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — greedy exercises the cards it should: draw Supporter, consistency Item, Stadium.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
