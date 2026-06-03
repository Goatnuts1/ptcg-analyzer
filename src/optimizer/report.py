#!/usr/bin/env python3
"""
report.py — Human-readable + JSON summary of an optimization run.

This OptimizerReport is the *runtime reporter* (formatting + persistence). It is
distinct from the lightweight `OptimizerReport` dataclass in types.py, which is
just a data container. core.py constructs THIS one. To avoid the name collision
the dataclass is no longer imported into core.py.
"""

import json
from collections import Counter
from typing import List

from .types import Decklist, OptimizationTarget


class OptimizerReport:
    """Formats and persists the result of one optimization run."""

    def __init__(self, base_deck: Decklist, final_deck: List[str], win_rate: float,
                 generations: int, history: list, target: OptimizationTarget,
                 total_time_seconds: float = 0.0):
        self.base_deck = base_deck
        self.final_deck = final_deck
        self.win_rate = win_rate
        self.generations = generations
        self.history = history
        self.target = target
        self.total_time_seconds = total_time_seconds

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print(f"  OPTIMIZATION REPORT — {self.target.name}")
        print("=" * 60)
        print(f"  Base deck:    {self.base_deck.name}")
        print(f"  Generations:  {self.generations}")
        print(f"  Final win rate (vs {self.target.name}): {self.win_rate:.1%}")
        print(f"  Wall time:    {self.total_time_seconds:.1f}s")
        print("\n  NOTE: win rate is under an UN-VALIDATED simulator at a reduced")
        print("  MCTS budget. Treat it as relative signal, not a real win rate.")
        print("\n  Final decklist:")
        for name, count in sorted(Counter(self.final_deck).items(), key=lambda x: (-x[1], x[0])):
            print(f"    {count:>2}x {name}")
        print("=" * 60 + "\n")

    def save_json(self, filepath: str = "optimizer_results.json") -> None:
        payload = {
            "target": self.target.name,
            "base_deck": self.base_deck.name,
            "win_rate": self.win_rate,
            "generations": self.generations,
            "total_time_seconds": self.total_time_seconds,
            "history": self.history,
            "final_deck": dict(Counter(self.final_deck)),
            "caveat": ("Win rate rests on an un-validated simulator at a reduced "
                       "MCTS budget; relative signal only, not a predicted real win rate."),
        }
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
