#!/usr/bin/env python3
"""
decklists.py — Base decks for the optimizer, sourced from the engine registry.

Every list is expanded from src/engine/decks.py:DECKS, so it is pool-valid by
construction (same guarantee as the old TOURNAMENT_* copies). Starting keys are
the August 2026 ladders that actually matter; `dragapult` / `charizard` stay as
aliases so existing flags and tests keep working.
"""

from typing import Dict, List, Tuple

from ..engine.decks import DECKS
from .types import Decklist


Recipe = List[Tuple[str, int]]


def _expand_names(recipe: Recipe) -> List[str]:
    """[(name, count), ...] -> flat ['name', 'name', ...] of length sum(counts)."""
    out: List[str] = []
    for name, count in recipe:
        out.extend([name] * count)
    return out


def decklist_from_registry(key: str) -> Decklist:
    if key not in DECKS:
        raise KeyError(f"unknown deck {key!r}. have: {sorted(DECKS)}")
    return Decklist(name=key, cards=_expand_names(DECKS[key]), archetype=key)


# CLI --deck starters. House list first; aliases map old flags onto registry keys.
STARTING_KEYS = [
    "mega_excadrill",
    "mega_excadrill_shaymin",
    "dragapult",
    "dragapult_blaziken",
    "crustle_modern",
    "festival_lead",
    "grimmsnarl_froslass",
    "fighting",
    "charizard_xy",
]

ALIASES = {
    "charizard": "charizard_xy",
}


def get_sample_decks() -> Dict[str, Decklist]:
    """Map CLI --deck choices to base decklists (aliases included)."""
    out: Dict[str, Decklist] = {}
    for key in STARTING_KEYS:
        out[key] = decklist_from_registry(key)
    for alias, real in ALIASES.items():
        src = out[real]
        out[alias] = Decklist(name=alias, cards=src.cards[:], archetype=real)
    return out


# Back-compat names some older imports used.
DRAGAPULT_STANDARD = decklist_from_registry("dragapult")
CHARIZARD_MEGA = decklist_from_registry("charizard_xy")
