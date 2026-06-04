#!/usr/bin/env python3
"""
meta.py — Optimization targets (what an evolved deck is scored against).

Game counts here are deliberately MODEST. At the reduced optimizer MCTS budget
(~a few games/sec) a target of N games per matchup, P-deck population, G
generations costs roughly N * P * G games per opponent. 800-game MCTS targets
(as originally drafted) run for many hours; the defaults below keep a full run
in the minutes-to-tens-of-minutes range so the loop is actually usable. Raise
num_games_per_matchup when you want tighter confidence and have time to burn.
"""

from typing import List

from .types import OptimizationTarget
from .decklists import DRAGAPULT_STANDARD, CHARIZARD_MEGA


def get_current_meta_targets() -> List[OptimizationTarget]:
    return [
        OptimizationTarget(
            name="Current Meta",
            description="Beat the top Standard decks (Dragapult + Mega Charizard).",
            opponent_decks=[DRAGAPULT_STANDARD, CHARIZARD_MEGA],
            num_games_per_matchup=120,
            use_mcts=True,
        ),
        OptimizationTarget(
            name="Charizard Mirror",
            description="Optimize the Charizard list against itself.",
            opponent_decks=[CHARIZARD_MEGA],
            num_games_per_matchup=160,
            use_mcts=True,
        ),
        OptimizationTarget(
            name="Wild Card",
            description="Fast greedy sweep against both meta decks (no MCTS).",
            opponent_decks=[DRAGAPULT_STANDARD, CHARIZARD_MEGA],
            num_games_per_matchup=300,
            use_mcts=False,
        ),
    ]
