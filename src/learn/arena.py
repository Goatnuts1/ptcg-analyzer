"""arena.py — head-to-head evaluation + the promotion gate.

play_match pits two agent factories against each other over a deck pairing, mirroring
seats so neither gets the going-first edge, and returns a win rate with a Wilson 95% CI.

promotion_gate decides whether a candidate model becomes the new "best": it must beat the
baseline by a margin AND the engine's rules/determinism tests must still pass. That second
clause is what makes a rules regression un-promotable by construction (plan §5).
"""
from __future__ import annotations

import math
import os
import random
import subprocess

from src.engine.cards import CardDB
from src.engine.decks import load_deck, DECKS
from src.engine.run import play_game

from . import config


def wilson_ci(wins: int, n: int, z: float = 1.96):
    """95% Wilson interval for a win rate (decided games)."""
    if n == 0:
        return 0.0, (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return p, (max(0.0, centre - half), min(1.0, centre + half))


def play_match(make_a, make_b, n_games: int, decks=None, base_seed: int = 0,
               pool: str = config.DEFAULT_POOL):
    """Play n_games of make_a vs make_b across deck pairings, mirrored. Returns a dict.

    make_a/make_b are callables (rng) -> agent. Seats are swapped every other game so the
    going-first advantage cancels. Win rate is over DECIDED games (ties excluded).
    """
    db = CardDB.from_pool(pool)
    deck_ids = decks or list(DECKS.keys())
    rng = random.Random(base_seed)
    a_wins = b_wins = ties = 0
    for g in range(n_games):
        d1 = deck_ids[g % len(deck_ids)]
        d2 = deck_ids[(g * 7 + 3) % len(deck_ids)]      # vary the opponent pairing
        deck1, deck2 = load_deck(db, d1), load_deck(db, d2)
        seed = rng.randint(0, 2**31 - 1)
        a_first = (g % 2 == 0)
        ra, rb = random.Random(seed), random.Random(seed + 1)
        agent_a, agent_b = make_a(ra), make_b(rb)
        if a_first:
            st = play_game(deck1, deck2, agent_a, agent_b, seed=seed, db=db)
            a_seat, b_seat = 0, 1
        else:
            st = play_game(deck1, deck2, agent_b, agent_a, seed=seed, db=db)
            a_seat, b_seat = 1, 0
        if st.winner is None:
            ties += 1
        elif st.winner == a_seat:
            a_wins += 1
        else:
            b_wins += 1
    decided = a_wins + b_wins
    rate, ci = wilson_ci(a_wins, decided)
    return {"a_wins": a_wins, "b_wins": b_wins, "ties": ties, "decided": decided,
            "a_rate": rate, "ci": ci, "games": n_games}


def rules_tests_pass(tests=("tests/test_determinism.py", "tests/test_learn.py")) -> bool:
    """Run the rule/determinism guards; True only if all exit 0 (the gate's hard clause)."""
    for t in tests:
        path = os.path.join(config.REPO_ROOT, t)
        if not os.path.exists(path):
            continue
        r = subprocess.run(["python3", path], cwd=config.REPO_ROOT,
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False
    return True


def promotion_gate(match: dict, margin: float = 0.55, run_tests: bool = True) -> dict:
    """Decide promotion: candidate (agent A) must beat baseline by `margin` AND rules pass."""
    beats = match["a_rate"] >= margin and match["ci"][0] > 0.5
    tests_ok = rules_tests_pass() if run_tests else True
    return {
        "promote": bool(beats and tests_ok),
        "beats_baseline": beats,
        "tests_pass": tests_ok,
        "a_rate": match["a_rate"], "ci": match["ci"],
        "reason": ("promoted" if beats and tests_ok else
                   "lost/too-close vs baseline" if not beats else "rules tests failed"),
    }
