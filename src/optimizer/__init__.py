"""
optimizer — evolutionary deck-optimization outer loop for the ptcg engine.

Mutates decklists and scores them via simulated battles (src/engine). The scores
rest on the engine, which is NOT yet validated to tournament-grade fidelity, and
optimizer MCTS runs at a reduced budget — so win-rates here are relative signal
between candidate decks under a fixed imperfect model, not predicted real rates.
See OPTIMIZER_HANDBOOK.md.
"""

from .types import Decklist, OptimizationTarget, EvalResult
from .core import DeckOptimizer
from .deck_generator import DeckMutator
from .evaluator import evaluate_deck
from .report import OptimizerReport
from .decklists import get_sample_decks
from .meta import get_current_meta_targets

__all__ = [
    "Decklist", "OptimizationTarget", "EvalResult",
    "DeckOptimizer", "DeckMutator", "evaluate_deck", "OptimizerReport",
    "get_sample_decks", "get_current_meta_targets",
]
