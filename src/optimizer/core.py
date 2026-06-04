#!/usr/bin/env python3
"""
core.py — Main Deck Optimizer Operating Loop
"""

import argparse
import time
from pathlib import Path
from typing import List

from ..engine.cards import CardDB
from .types import Decklist, OptimizationTarget
from .deck_generator import DeckMutator
from .evaluator import evaluate_deck
from .report import OptimizerReport
from .meta import get_current_meta_targets


class DeckOptimizer:
    """Main optimization engine."""

    def __init__(self, db: CardDB = None):
        self.db = db or CardDB.from_pool()
        self.mutator = DeckMutator(self.db)

    def optimize(self, base_deck: Decklist, target: OptimizationTarget,
                 generations: int = 10, population_size: int = 12,
                 output_dir: str = "optimizer_runs") -> OptimizerReport:

        Path(output_dir).mkdir(exist_ok=True)

        print(f"\n🚀 Starting Optimization → {target.name}")
        print(f"Goal: {target.description}\n")

        current_best = base_deck.cards[:]
        best_winrate = 0.0
        history = []

        start_time = time.time()

        for gen in range(generations):
            gen_start = time.time()
            print(f"Generation {gen+1}/{generations}...")

            population = self.mutator.generate_population(current_best, population_size)
            results = []

            for deck in population:
                score = evaluate_deck(
                    deck,
                    target.opponent_decks,
                    self.db,
                    num_games=target.num_games_per_matchup,
                    use_mcts=target.use_mcts
                )
                results.append((deck, score))

            # Select best
            results.sort(key=lambda x: x[1].win_rate, reverse=True)
            current_best = results[0][0]
            best_winrate = results[0][1].win_rate

            history.append({
                "generation": gen,
                "win_rate": best_winrate
            })

            print(f"  Best: {best_winrate:.1%} | Time: {time.time()-gen_start:.1f}s")

        total_time = time.time() - start_time

        report = OptimizerReport(
            base_deck=base_deck,
            final_deck=current_best,
            win_rate=best_winrate,
            generations=generations,
            history=history,
            target=target,
            total_time_seconds=total_time
        )

        report.print_summary()
        report.save_json(f"{output_dir}/result_{target.name.lower().replace(' ', '_')}.json")

        return report


def main():
    parser = argparse.ArgumentParser(description="Pokémon TCG Deck Optimizer")
    parser.add_argument("--deck", choices=["dragapult", "charizard"], default="dragapult")
    parser.add_argument("--target", choices=["current-meta", "mirror", "wildcard"], default="current-meta")
    parser.add_argument("--generations", type=int, default=8)
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--output", default="optimizer_runs")
    args = parser.parse_args()

    db = CardDB.from_pool()
    optimizer = DeckOptimizer(db)

    # TODO: Load proper decklists from decklists.py
    # For now using placeholder
    print("Note: Using sample decklists (expand later)")

    target = get_current_meta_targets()[0]
    if args.fast:
        target.use_mcts = False

    optimizer.optimize(target.opponent_decks[0], target,
                      generations=args.generations,
                      population_size=args.population,
                      output_dir=args.output)


if __name__ == "__main__":
    main()
