#!/usr/bin/env python3
"""
test_engine.py — invariants for the rules engine. Run from project root:

    python3 tests/test_engine.py

These guard the properties that, if violated, mean the engine is lying about
who won. Cheap, deterministic, no network.
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import load_test_decks
from src.engine.agents import RandomAgent, GreedyAgent
from src.engine.game import setup_game, can_pay_cost, Phase
from src.engine.run import play_game
from src.engine.state import InPlayPokemon


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    deck_a, deck_b = load_test_decks(db)

    # 1. basic energy got injected
    check("Basic Lightning Energy" in db, "basic energy not injected into CardDB")

    # 2. cost checking: a Lightning+Colorless attack needs matching energy
    pika = db.get("Pikachu ex")
    mon = InPlayPokemon(card=pika)
    thunderbolt = next(a for a in pika.attacks if a.name == "Thunderbolt")
    check(not can_pay_cost(mon, thunderbolt.cost), "empty mon should not pay cost")
    mon.energy = [db.get("Basic Lightning Energy")] * 2 + [db.get("Basic Psychic Energy")]
    check(can_pay_cost(mon, thunderbolt.cost),
          "LLC cost should be payable by L,L,Psychic(as colorless)")

    # 3. games always terminate with a valid result; prizes never go negative
    rng = random.Random(0)
    for g in range(300):
        s = rng.randint(0, 2**31 - 1)
        st = play_game(deck_a, deck_b, GreedyAgent(random.Random(s)),
                       GreedyAgent(random.Random(s + 1)), seed=s)
        check(st.winner in (0, 1, None), f"game {g}: invalid winner {st.winner}")
        for p in st.players:
            check(0 <= len(p.prizes) <= 6, f"game {g}: bad prize count {len(p.prizes)}")
        check(st.phase == Phase.GAME_OVER or st.turn_number >= 1,
              f"game {g}: game never started")

    # 4. greedy must dominate random (engine rewards better play)
    wins = 0
    n = 300
    for g in range(n):
        s = rng.randint(0, 2**31 - 1)
        st = play_game(deck_a, deck_b, GreedyAgent(random.Random(s)),
                       RandomAgent(random.Random(s + 1)), seed=s)
        if st.winner == 0:
            wins += 1
    rate = wins / n
    check(rate > 0.70, f"greedy beat random only {rate:.0%} (expected >70%) — engine/agent suspect")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"OK — engine invariants hold. greedy>random = {rate:.0%}")


if __name__ == "__main__":
    main()
