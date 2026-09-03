#!/usr/bin/env python3
"""
core.py — Main Deck Optimizer Operating Loop
"""

import time
from pathlib import Path
from typing import List

from ..engine.cards import CardDB
from .types import Decklist, OptimizationTarget
from .deck_generator import DeckMutator
from .evaluator import evaluate_deck
from .report import OptimizerReport


class DeckOptimizer:
    """Main optimization engine."""

    def __init__(self, db: CardDB = None):
        self.db = db or CardDB.from_pool()
        self.mutator = DeckMutator(self.db)

    def optimize(self, base_deck: Decklist, target: OptimizationTarget,
                 generations: int = 10, population_size: int = 12,
                 output_dir: str = "optimizer_runs") -> OptimizerReport:

        if generations < 1:
            raise ValueError("generations must be >= 1")
        if population_size < 1:
            raise ValueError("population_size must be >= 1")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        print(f"\nStarting optimization -> {target.name}")
        print(f"Goal: {target.description}\n")

        current_best = base_deck.cards[:]
        base_winrate = None      # filled from generation 1 (see below)
        best_winrate = -1.0
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

            # generate_population keeps index 0 as the unmutated incumbent, and
            # evaluate_deck scores every candidate off the SAME fixed seed
            # sequence — so results[0] here is the incumbent's score under
            # exactly the games its challengers played. On generation 1 that is
            # the base deck, which is the only honest baseline for the delta.
            incumbent_winrate = results[0][1].win_rate
            if base_winrate is None:
                base_winrate = incumbent_winrate

            # Select best. Elitism is explicit: a generation that produces no
            # improvement keeps the incumbent rather than drifting sideways onto
            # an equal-scoring mutant.
            results.sort(key=lambda x: x[1].win_rate, reverse=True)
            if results[0][1].win_rate > best_winrate:
                current_best = results[0][0]
                best_winrate = results[0][1].win_rate

            history.append({
                "generation": gen,
                "win_rate": best_winrate,
                "generation_best": results[0][1].win_rate,
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
            total_time_seconds=total_time,
            base_win_rate=base_winrate,
        )

        report.print_summary()
        report.save_json(f"{output_dir}/result_{target.name.lower().replace(' ', '_')}.json")

        return report

