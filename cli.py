#!/usr/bin/env python3
"""
cli.py — run a head-to-head between two decks and report win rates.

    python3 cli.py --deck1 dragapult --deck2 raging_bolt --games 5000
    python3 cli.py --deck1 raging_bolt --deck2 charizard_xy --games 1000 --agent mcts

Decks are referenced by name from the registry in src/engine/decks.py (run with
--list to see them). Seats are mirrored by default (each deck goes first in half
the games) so the win rate isn't skewed by the going-first advantage. Everything
is deterministic: the same --seed reproduces the exact same set of games.
"""

from __future__ import annotations

import argparse
import random
import time

from src.engine.cards import CardDB
from src.engine.decks import DECKS, load_deck
from src.engine.agents import RandomAgent, GreedyAgent
from src.engine.run import play_game


def _make_agent(kind: str, rng: random.Random):
    if kind == "random":
        return RandomAgent(rng)
    if kind == "mcts":
        from src.engine.mcts import MCTSAgent
        return MCTSAgent(iterations=120, rollout="eval", rng=rng, search_plies=2)
    return GreedyAgent(rng)


def run(deck1: str, deck2: str, games: int, agent: str, seed: int,
        mirror: bool, pool: str) -> dict:
    db = CardDB.from_pool(pool)
    load_deck(db, deck1)            # validate names up front (raises with a helpful msg)
    load_deck(db, deck2)

    d1_wins = d2_wins = ties = 0
    for i in range(games):
        s = seed + i
        # mirror: on odd games deck2 takes seat 0 (goes first) so neither deck keeps
        # the first-turn edge. Track wins by DECK identity, not seat.
        swap = mirror and (i % 2 == 1)
        name_a, name_b = (deck2, deck1) if swap else (deck1, deck2)
        deck_a, deck_b = load_deck(db, name_a), load_deck(db, name_b)
        rng_a, rng_b = random.Random(s), random.Random(s + 1_000_000)
        st = play_game(deck_a, deck_b, _make_agent(agent, rng_a),
                       _make_agent(agent, rng_b), seed=s, db=db)
        if st.winner is None:
            ties += 1
        else:
            winner_name = (name_a, name_b)[st.winner]
            if winner_name == deck1:
                d1_wins += 1
            else:
                d2_wins += 1
    return {"d1_wins": d1_wins, "d2_wins": d2_wins, "ties": ties}


def main():
    ap = argparse.ArgumentParser(description="Run N games between two decks; report win rates.")
    ap.add_argument("--deck1", help="first deck name (see --list)")
    ap.add_argument("--deck2", help="second deck name (see --list)")
    ap.add_argument("--games", type=int, default=1000, help="number of games (default 1000)")
    ap.add_argument("--agent", choices=["greedy", "random", "mcts"], default="greedy",
                    help="agent piloting both decks (default greedy; mcts is far slower)")
    ap.add_argument("--seed", type=int, default=0, help="base RNG seed (deterministic)")
    ap.add_argument("--no-mirror", action="store_true",
                    help="don't mirror seats (deck1 always goes first)")
    ap.add_argument("--pool", default="data/standard_pool.json")
    ap.add_argument("--list", action="store_true", help="list available decks and exit")
    args = ap.parse_args()

    if args.list or not (args.deck1 and args.deck2):
        print("Available decks:")
        for name in sorted(DECKS):
            print(f"  {name}")
        if not args.list:
            print("\nUsage: python3 cli.py --deck1 <name> --deck2 <name> --games 5000")
        return

    t0 = time.time()
    r = run(args.deck1, args.deck2, args.games, args.agent, args.seed,
            mirror=not args.no_mirror, pool=args.pool)
    dt = time.time() - t0
    n = args.games
    seats = "deck1 first" if args.no_mirror else "mirrored seats"
    print(f"\n{args.deck1} vs {args.deck2} — {n} games ({args.agent}, {seats}, seed {args.seed})")
    print(f"  {args.deck1:<16} {r['d1_wins']:>6}  {r['d1_wins'] / n:6.1%}")
    print(f"  {args.deck2:<16} {r['d2_wins']:>6}  {r['d2_wins'] / n:6.1%}")
    print(f"  {'ties':<16} {r['ties']:>6}  {r['ties'] / n:6.1%}")
    print(f"  {n / dt:,.0f} games/sec  ({dt:.1f}s, 0 tokens)")


if __name__ == "__main__":
    main()
