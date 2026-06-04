#!/usr/bin/env python3
"""
validation_runner.py — Convenience driver for a meatier optimization run.

WHAT THIS IS NOT: this does NOT validate the simulator. Validating the engine
means comparing its output to real tournament results (see docs/VALIDATION_*.md);
that is a separate, still-open question (Dragapult mirror sims ~58% vs a published
~84%). Running the OPTIMIZER — which mutates decks and scores them under that same
engine — cannot confirm the engine is right; a deck that scores well here scores
well *under an un-validated model at a reduced agent budget*. Treat the output as
relative signal between candidate decks, not as a validated result.

WHAT THIS IS: a one-call driver that runs a larger optimization pass than the
smoke tests, against the current-meta opponent set, with knobs and an explicit
cost estimate so you don't accidentally kick off a multi-hour MCTS run.
"""

from ..engine.cards import CardDB
from .core import DeckOptimizer
from .decklists import get_sample_decks
from .meta import get_current_meta_targets
from .evaluator import OPTIMIZER_MCTS_ITERATIONS


def run_validation_pass(deck: str = "dragapult",
                        num_games_per_matchup: int = 120,
                        generations: int = 4,
                        population_size: int = 8,
                        use_mcts: bool = True,
                        db: CardDB = None):
    """Run an optimization pass on a sample deck vs the current-meta target.

    Defaults are deliberately modest. Cost ≈
        num_games_per_matchup * population_size * generations * n_opponents
    games. With MCTS at ~a few games/sec that is the dominant time. Raise the
    counts when you have time to spend; the estimate below prints first.
    """
    db = db or CardDB.from_pool()
    decks = get_sample_decks()
    if deck not in decks:
        raise ValueError(f"unknown deck {deck!r}; choose from {sorted(decks)}")

    target = get_current_meta_targets()[0]
    target.num_games_per_matchup = num_games_per_matchup
    target.use_mcts = use_mcts

    est_games = (num_games_per_matchup * population_size *
                 generations * len(target.opponent_decks))
    print("🔬 Optimization pass (NOT simulator validation — see module docstring)\n")
    print(f"  deck:        {decks[deck].name}")
    print(f"  opponents:   {[d.name for d in target.opponent_decks]}")
    print(f"  budget:      ~{est_games:,} games "
          f"({'MCTS@'+str(OPTIMIZER_MCTS_ITERATIONS) if use_mcts else 'greedy'})")
    if use_mcts and est_games > 5000:
        print("  ⚠️  MCTS at this game count can take a long time (many minutes+).")
        print("      Pass use_mcts=False or lower the counts for a quick pass.\n")

    report = optimizer_optimize(db, target, decks[deck], generations, population_size)

    print("\n✅ Pass complete (relative signal under an un-validated model).")
    print(f"   Best win rate achieved: {report.win_rate:.1%}")
    return report


def optimizer_optimize(db, target, base_deck, generations, population_size):
    return DeckOptimizer(db).optimize(
        base_deck=base_deck,
        target=target,
        generations=generations,
        population_size=population_size,
    )


if __name__ == "__main__":
    # Quick, honest default: greedy so it finishes promptly.
    run_validation_pass(use_mcts=False)
