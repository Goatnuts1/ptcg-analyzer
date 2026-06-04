#!/usr/bin/env python3
"""
optimize.py — Main entrypoint for the Pokémon TCG Deck Optimizer
"""

import argparse
from src.engine.cards import CardDB
from src.optimizer.core import DeckOptimizer
from src.optimizer.decklists import get_sample_decks
from src.optimizer.meta import get_current_meta_targets


def main():
    parser = argparse.ArgumentParser(description="Pokémon TCG Deck Optimizer")
    parser.add_argument("--deck", choices=["dragapult", "charizard"], default="dragapult",
                        help="Starting deck archetype")
    parser.add_argument("--target", choices=["current-meta", "mirror", "wildcard"],
                        default="current-meta", help="Optimization goal")
    parser.add_argument("--generations", type=int, default=8,
                        help="Number of generations to evolve")
    parser.add_argument("--population", type=int, default=12,
                        help="Population size per generation")
    parser.add_argument("--fast", action="store_true",
                        help="Use GreedyAgent instead of MCTS (much faster)")
    parser.add_argument("--output", default="optimizer_runs",
                        help="Directory to save results")
    args = parser.parse_args()

    print("Loading card database...")
    db = CardDB.from_pool()

    optimizer = DeckOptimizer(db)
    decks = get_sample_decks()
    base_deck = decks[args.deck]

    if args.target == "current-meta":
        target = get_current_meta_targets()[0]
    elif args.target == "mirror":
        target = get_current_meta_targets()[0]
        target.name = f"{base_deck.name} Mirror"
        target.opponent_decks = [base_deck]
    else:
        target = get_current_meta_targets()[-1]

    if args.fast:
        target.use_mcts = False
        print("⚡ Fast mode enabled (GreedyAgent)")

    report = optimizer.optimize(
        base_deck=base_deck,
        target=target,
        generations=args.generations,
        population_size=args.population,
        output_dir=args.output
    )

    print(f"\n🎯 Optimization complete! Check {args.output}/ for results.")


if __name__ == "__main__":
    main()
