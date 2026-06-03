#!/usr/bin/env python3
"""
types.py — Shared data classes for the Deck Optimizer
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Decklist:
    """A named deck for optimization."""
    name: str
    cards: List[str]                    # card names (with multiplicity)
    archetype: str = "Unknown"


@dataclass
class OptimizationTarget:
    """What are we optimizing for?"""
    name: str
    description: str
    opponent_decks: List[Decklist]
    num_games_per_matchup: int = 600
    use_mcts: bool = True               # False = fast greedy evaluation


@dataclass
class EvalResult:
    """Result of evaluating one deck against opponents."""
    deck: List[str]
    win_rate: float
    avg_turns: float
    wins: int
    losses: int
    ties: int
    metadata: Dict = field(default_factory=dict)

# NOTE: the optimization-run report lives in report.py (OptimizerReport — the
# reporter with print_summary/save_json). An earlier duplicate dataclass of the
# same name lived here; it was removed to eliminate the name collision. There is
# now exactly one public OptimizerReport.
