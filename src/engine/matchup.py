#!/usr/bin/env python3
"""
matchup.py — the validation regression metric: Dragapult ex vs Mega Charizard X/Y ex.

Runs the two tournament lists head-to-head with MIRRORED seats (to cancel the
going-first advantage) and reports BOTH the win rate AND evidence that the agent is
choosing the right LINES — bench spread, gust, disruption, the Battle Cage counter.
Per the policy milestone's success criterion: a Dragapult-favored band reached for
the right reasons, not a tuned point.

CLI:  python3 -m src.engine.matchup --agent eval --games 30
"""

from __future__ import annotations

import argparse
import random

from .cards import CardDB
from .decks import load_tournament_deck
from .agents import RandomAgent, GreedyAgent, EvalAgent
from .mcts import MCTSAgent
from .game import setup_game, start_turn
from .run import finish_game, _resolve_tie

# Log substrings that evidence "the right lines" being played.
LINE_MARKERS = {
    "Phantom Dive (bench spread)": "Phantom Dive",
    "Cursed Blast (KO engine)": "Cursed Blast",
    "gust (Boss's Orders)": "Boss's Orders",
    "Item-lock (Budew)": "Itchy Pollen",
    "Crushing Hammer hit": "Crushing Hammer: heads",
    "TRW (ability lock)": "Stadium Team Rocket's Watchtower",
    "Battle Cage prevented spread": "Battle Cage: prevented",
}


def _make_agent(kind: str, rng: random.Random, iters: int):
    if kind == "random":
        return RandomAgent(rng)
    if kind == "greedy":
        return GreedyAgent(rng)
    if kind == "eval":
        return EvalAgent(rng)
    if kind == "mcts":
        return MCTSAgent(iterations=iters, rng=rng)
    raise ValueError(kind)


def run_matchup(agent: str = "eval", n_per_orient: int = 30, iters: int = 120,
                seed: int = 0) -> dict:
    db = CardDB.from_pool("data/standard_pool.json")
    drag_wins = char_wins = ties = 0
    line_counts = {name: 0 for name in LINE_MARKERS}
    prize_wins = 0
    for orient in (0, 1):
        for i in range(n_per_orient):
            rng = random.Random(seed + orient * 100000 + i)
            d_drag = load_tournament_deck(db, "dragapult")
            d_char = load_tournament_deck(db, "charizard_xy")
            if orient == 0:
                deck_a, deck_b, drag_seat = d_drag, d_char, 0
            else:
                deck_a, deck_b, drag_seat = d_char, d_drag, 1
            st = setup_game(deck_a, deck_b, seed=seed + orient * 100000 + i, db=db)
            start_turn(st)
            finish_game(st, _make_agent(agent, rng, iters), _make_agent(agent, rng, iters))
            _resolve_tie(st)
            if st.winner is None:
                ties += 1
            elif st.winner == drag_seat:
                drag_wins += 1
            else:
                char_wins += 1
            if st.winner is not None and len(st.players[st.winner].prizes) == 0:
                prize_wins += 1
            log = "\n".join(st.log)
            for name, marker in LINE_MARKERS.items():
                if marker in log:
                    line_counts[name] += 1
    total = drag_wins + char_wins
    games = 2 * n_per_orient
    return {
        "agent": agent, "games": games,
        "dragapult_winpct": 100 * drag_wins / total if total else 0,
        "drag_wins": drag_wins, "char_wins": char_wins, "ties": ties,
        "prize_win_pct": 100 * prize_wins / games,
        "line_counts": line_counts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="eval", choices=["random", "greedy", "eval", "mcts"])
    ap.add_argument("--games", type=int, default=30, help="games PER orientation (x2 total)")
    ap.add_argument("--iters", type=int, default=120, help="MCTS iterations (mcts only)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    r = run_matchup(args.agent, args.games, args.iters, args.seed)
    print(f"\nDragapult ex vs Mega Charizard X/Y ex — {r['agent'].upper()} mirror, {r['games']} games")
    print(f"  Dragapult ex   {r['drag_wins']:>3}  ({r['dragapult_winpct']:.1f}%)")
    print(f"  Charizard X/Y  {r['char_wins']:>3}  ({100 - r['dragapult_winpct']:.1f}%)  ties {r['ties']}")
    print(f"  won by prizes: {r['prize_win_pct']:.0f}%")
    print(f"  PUBLISHED (Limitless): Dragapult ~84% | success band: ~68-82% for the right reasons")
    print(f"  --- right-lines evidence (games where the line appeared) ---")
    for name, c in r["line_counts"].items():
        print(f"    {name:<32} {c}/{r['games']}")


if __name__ == "__main__":
    main()
