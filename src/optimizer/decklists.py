#!/usr/bin/env python3
"""
decklists.py — Sample base decks for the optimizer.

These are sourced from the engine's already-validated tournament recipes
(src/engine/decks.py: TOURNAMENT_DRAGAPULT, TOURNAMENT_CHARIZARD_XY), which
load to legal 60-card lists against data/standard_pool.json. We expand those
(name, count) recipes into the flat name-with-multiplicity lists the optimizer
mutates. This guarantees every base deck is pool-valid and legal on day one —
unlike hand-typed lists, which drift from the pool's exact card names.
"""

from typing import Dict, List

from ..engine.decks import TOURNAMENT_DRAGAPULT, TOURNAMENT_CHARIZARD_XY
from .types import Decklist


def _expand_names(recipe: List[tuple]) -> List[str]:
    """[(name, count), ...] -> flat ['name', 'name', ...] of length sum(counts)."""
    out: List[str] = []
    for name, count in recipe:
        out.extend([name] * count)
    return out


DRAGAPULT_STANDARD = Decklist(
    name="Dragapult ex (Standard)",
    cards=_expand_names(TOURNAMENT_DRAGAPULT),
    archetype="Dragapult",
)

CHARIZARD_MEGA = Decklist(
    name="Mega Charizard X/Y ex (Standard)",
    cards=_expand_names(TOURNAMENT_CHARIZARD_XY),
    archetype="Charizard",
)


def get_sample_decks() -> Dict[str, Decklist]:
    """Map the CLI --deck choices to base decklists."""
    return {
        "dragapult": DRAGAPULT_STANDARD,
        "charizard": CHARIZARD_MEGA,
    }
