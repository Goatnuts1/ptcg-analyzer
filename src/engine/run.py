#!/usr/bin/env python3
"""
run.py — play full games and report stats. This is the "crunch all day" loop.

ELI15: take two decks and two agents, play a whole game move by move, see who
wins. Then do it thousands of times and report win rates and speed. Every game
here costs ZERO tokens — it's pure CPU. That's the entire point of the design.

    python3 -m src.engine.run                 # 1000 games, greedy vs greedy
    python3 -m src.engine.run --games 5000 --agent-a random
    python3 -m src.engine.run --log            # print the move log of one game
"""

from __future__ import annotations

import argparse
import random
import time
from collections import Counter

from .cards import CardDB
from .game import (apply_action, check_win, end_turn, legal_actions,
                   setup_game, start_turn, MAX_TURNS, Phase)
from .agents import RandomAgent, GreedyAgent
from .decks import load_test_decks


def play_one_turn(state, agent) -> None:
    """A player takes actions until they attack (ends turn), pass, or hit a cap."""
    safety = 0
    while state.phase == Phase.MAIN:
        action = agent.choose(state)
        apply_action(state, action)
        if action.kind in ("attack", "pass"):
            if action.kind == "pass":
                state.phase = Phase.BETWEEN_TURNS
            break
        safety += 1
        if safety > 50:        # can't loop forever within a single turn
            state.phase = Phase.BETWEEN_TURNS
            break


def play_game(deck_a, deck_b, agent_a, agent_b, seed=None, keep_log=False, db=None):
    state = setup_game(deck_a, deck_b, seed=seed, db=db)
    agents = (agent_a, agent_b)

    while state.phase != Phase.GAME_OVER and state.turn_number < MAX_TURNS:
        if not start_turn(state):          # deck-out check
            break
        if check_win(state):
            break
        play_one_turn(state, agents[state.active_index])
        if check_win(state):
            break
        end_turn(state)

    # turn cap reached with no winner -> decide by prizes remaining (fewer = ahead)
    if state.winner is None:
        pa, pb = state.players
        if len(pa.prizes) != len(pb.prizes):
            state.winner = 0 if len(pa.prizes) < len(pb.prizes) else 1
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--agent-a", choices=["random", "greedy"], default="greedy")
    ap.add_argument("--agent-b", choices=["random", "greedy"], default="greedy")
    ap.add_argument("--pool", default="data/standard_pool.json")
    ap.add_argument("--log", action="store_true", help="print move log of one game and exit")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    db = CardDB.from_pool(args.pool)
    deck_a, deck_b = load_test_decks(db)

    def make(kind, rng):
        return RandomAgent(rng) if kind == "random" else GreedyAgent(rng)

    if args.log:
        rng = random.Random(args.seed or 1)
        st = play_game(deck_a, deck_b, make(args.agent_a, rng), make(args.agent_b, rng),
                       seed=args.seed or 1, keep_log=True, db=db)
        for line in st.log:
            print(line)
        print(f"\nWINNER: {'tie' if st.winner is None else 'P'+str(st.winner)} "
              f"in {st.turn_number} turns")
        return

    base = random.Random(args.seed)
    wins = Counter()
    turns_total = 0
    t0 = time.time()
    for g in range(args.games):
        s = base.randint(0, 2**31 - 1)
        rng_a, rng_b = random.Random(s), random.Random(s + 1)
        st = play_game(deck_a, deck_b, make(args.agent_a, rng_a),
                       make(args.agent_b, rng_b), seed=s, db=db)
        wins["tie" if st.winner is None else f"P{st.winner}"] += 1
        turns_total += st.turn_number
    dt = time.time() - t0

    print(f"\n{args.games} games | {args.agent_a} (P0) vs {args.agent_b} (P1)")
    print(f"  P0 wins: {wins['P0']} ({wins['P0']/args.games:.1%})")
    print(f"  P1 wins: {wins['P1']} ({wins['P1']/args.games:.1%})")
    print(f"  ties:    {wins['tie']} ({wins['tie']/args.games:.1%})")
    print(f"  avg game length: {turns_total/args.games:.1f} turns")
    print(f"  time: {dt:.2f}s  ->  {args.games/dt:,.0f} games/sec, 0 tokens")


if __name__ == "__main__":
    main()
