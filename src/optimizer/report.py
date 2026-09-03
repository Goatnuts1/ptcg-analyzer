#!/usr/bin/env python3
"""
report.py — Human-readable + JSON summary of an optimization run.

This is the single OptimizerReport in the package — the *runtime reporter*
(fields + formatting + persistence). core.py constructs it and optimize()
returns it. (An earlier duplicate dataclass of the same name in types.py was
removed to eliminate a name collision.)
"""

import json
from collections import Counter
from typing import List

from .types import Decklist, OptimizationTarget


class OptimizerReport:
    """Formats and persists the result of one optimization run."""

    def __init__(self, base_deck: Decklist, final_deck: List[str], win_rate: float,
                 generations: int, history: list, target: OptimizationTarget,
                 total_time_seconds: float = 0.0, base_win_rate: float = None):
        self.base_deck = base_deck
        self.final_deck = final_deck
        self.win_rate = win_rate
        # The starting list's win rate under the SAME opponents and the same
        # fixed game seeds. Without it the final number is unreadable: you
        # cannot tell an optimizer that found something from one that found
        # nothing and handed the base list back.
        self.base_win_rate = base_win_rate
        self.generations = generations
        self.history = history
        self.target = target
        self.total_time_seconds = total_time_seconds

    @property
    def improvement(self) -> float:
        """Final minus baseline, in win-rate points (0.0 if no baseline)."""
        if self.base_win_rate is None:
            return 0.0
        return self.win_rate - self.base_win_rate

    def changes(self):
        """[(name, base_count, final_count), ...] for every card whose count moved."""
        base = Counter(self.base_deck.cards)
        final = Counter(self.final_deck)
        return [(n, base[n], final[n])
                for n in sorted(set(base) | set(final)) if base[n] != final[n]]

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print(f"  OPTIMIZATION REPORT — {self.target.name}")
        print("=" * 60)
        print(f"  Base deck:    {self.base_deck.name}")
        print(f"  Generations:  {self.generations}")
        if self.base_win_rate is not None:
            print(f"  Base win rate (vs {self.target.name}): {self.base_win_rate:.1%}")
        print(f"  Final win rate (vs {self.target.name}): {self.win_rate:.1%}")
        if self.base_win_rate is not None:
            print(f"  Improvement:  {self.improvement:+.1%}")
        print(f"  Wall time:    {self.total_time_seconds:.1f}s")
        print("\n  NOTE: win rate is under an UN-VALIDATED simulator at a reduced")
        print("  MCTS budget. Treat it as relative signal, not a real win rate.")
        changed = self.changes()
        if changed:
            print("\n  Changes from the base list:")
            for name, before, after in changed:
                print(f"    {before}x -> {after}x  {name}")
        else:
            print("\n  No change: the base list survived every generation.")
        print("\n  Final decklist:")
        for name, count in sorted(Counter(self.final_deck).items(), key=lambda x: (-x[1], x[0])):
            print(f"    {count:>2}x {name}")
        print("=" * 60 + "\n")

    def save_json(self, filepath: str = "optimizer_results.json") -> None:
        payload = {
            "target": self.target.name,
            "base_deck": self.base_deck.name,
            "base_win_rate": self.base_win_rate,
            "win_rate": self.win_rate,
            "improvement": self.improvement,
            "generations": self.generations,
            "total_time_seconds": self.total_time_seconds,
            "history": self.history,
            "final_deck": dict(Counter(self.final_deck)),
            "changes": [{"card": n, "before": b, "after": a}
                        for n, b, a in self.changes()],
            "caveat": ("Win rate rests on an un-validated simulator at a reduced "
                       "MCTS budget; relative signal only, not a predicted real win rate."),
        }
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
