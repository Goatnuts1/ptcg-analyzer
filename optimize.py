#!/usr/bin/env python3
"""
optimize.py — Main entrypoint for the Pokémon TCG Deck Optimizer

Win rates are relative signal under an imperfect engine, not Live predictions.
See OPTIMIZER_HANDBOOK.md.
"""

import argparse
from src.engine.cards import CardDB
from src.optimizer.core import DeckOptimizer
from src.optimizer.decklists import get_sample_decks
from src.optimizer.meta import get_current_meta_targets


def main():
    decks = get_sample_decks()
    parser = argparse.ArgumentParser(description="Pokémon TCG Deck Optimizer")
    parser.add_argument(
        "--deck",
        choices=sorted(decks),
        default="mega_excadrill",
        help="Starting list from the engine registry (default: house Mega Excadrill)",
    )
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
    base_deck = decks[args.deck]

    targets = get_current_meta_targets()
    if args.target == "current-meta":
        target = targets[0]
    elif args.target == "mirror":
        target = targets[0]
        target.name = f"{base_deck.name} Mirror"
        target.description = f"Optimize {base_deck.name} against itself."
        target.opponent_decks = [base_deck]
    else:
        target = targets[-1]

    if args.fast:
        target.use_mcts = False
        print("Fast mode enabled (GreedyAgent)")

    print(f"Start: {base_deck.name}  ({len(base_deck.cards)} cards)")
    print(f"Target: {target.name} vs {[d.name for d in target.opponent_decks]}")

    optimizer.optimize(
        base_deck=base_deck,
        target=target,
        generations=args.generations,
        population_size=args.population,
        output_dir=args.output
    )

    print(f"\nOptimization complete. Check {args.output}/ for results.")
    print("Caveat: these win rates are relative signal, not Live predictions.")


if __name__ == "__main__":
    main()
