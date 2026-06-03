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


@dataclass
class OptimizerReport:
    """Final report from an optimization run."""
    base_deck: Decklist
    final_deck: List[str]
    win_rate: float
    generations: int
    history: List
    target: OptimizationTarget
    total_time_seconds: float = 0.0
