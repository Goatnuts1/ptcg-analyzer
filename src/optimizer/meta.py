#!/usr/bin/env python3
"""
meta.py — Optimization targets (what an evolved deck is scored against).

Game counts here are deliberately MODEST. evaluate_deck SPLITS num_games across
the opponent set (it does not multiply by opponent count). At the reduced
optimizer MCTS budget a full run should stay in minutes, not hours. Raise
num_games_per_matchup when you want tighter confidence and have time to burn.

The August 2026 Live field is the registered decks that actually show up on
ladder / Limitless — not the June Dragapult-vs-Charizard pair.
"""

from typing import List

from .decklists import decklist_from_registry
from .types import OptimizationTarget


# Representable Live field. Keep this short: more opponents thins games-per-MU.
AUGUST_META_KEYS = [
    "mega_excadrill",
    "dragapult_blaziken",
    "festival_lead",
    "grimmsnarl_froslass",
    "fighting",
    "crustle_modern",
]


def get_current_meta_targets() -> List[OptimizationTarget]:
    opponents = [decklist_from_registry(k) for k in AUGUST_META_KEYS]
    return [
        OptimizationTarget(
            name="Current Meta",
            description=(
                "Beat the August 2026 Live field: Excadrill, Blaziken-Pult, "
                "Festival Lead, Grimmsnarl/Froslass, Mega Lucario, Crustle."
            ),
            opponent_decks=opponents,
            num_games_per_matchup=120,
            use_mcts=True,
        ),
        OptimizationTarget(
            name="House Mirror",
            description="Optimize the house Mega Excadrill list against itself.",
            opponent_decks=[decklist_from_registry("mega_excadrill")],
            num_games_per_matchup=160,
            use_mcts=True,
        ),
        OptimizationTarget(
            name="Wild Card",
            description="Fast greedy sweep against the August Live field (no MCTS).",
            opponent_decks=opponents,
            num_games_per_matchup=300,
            use_mcts=False,
        ),
    ]
