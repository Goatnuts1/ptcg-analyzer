#!/usr/bin/env python3
"""
state.py — the mutable game state the engine reads and writes.

ELI15: a snapshot of the board. Each player has a deck, hand, an Active Pokemon,
a bench, prizes, and a discard pile. An InPlayPokemon wraps a card with the
stuff that changes during play: damage on it and energy attached to it.

This file holds DATA, not rules. The rules live in game.py.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .cards import Card


class Phase(Enum):
    SETUP = "setup"
    DRAW = "draw"
    MAIN = "main"
    ATTACK = "attack"
    BETWEEN_TURNS = "between_turns"
    GAME_OVER = "game_over"


@dataclass
class InPlayPokemon:
    """A Pokemon physically on the board, with its mutable battle state."""
    card: Card
    damage: int = 0
    energy: list[Card] = field(default_factory=list)   # attached energy cards
    # evolution stack so we know what it evolved from (for devolve effects later)
    evolved_from: list[Card] = field(default_factory=list)
    ability_used_this_turn: bool = False
    played_this_turn: bool = False     # can't evolve the turn it was played
    evolved_this_turn: bool = False    # one evolution step per Pokemon per turn

    @property
    def remaining_hp(self) -> int:
        return (self.card.hp or 0) - self.damage

    @property
    def is_knocked_out(self) -> bool:
        return self.card.hp is not None and self.damage >= self.card.hp

    def energy_count(self) -> int:
        # Each attached energy provides at least one unit. Special energy that
        # provide multiple/typed units are a later refinement.
        return len(self.energy)

    def provided_types(self) -> list[str]:
        types = []
        for e in self.energy:
            types.extend(e.types or ["Colorless"])
        return types


@dataclass
class PlayerState:
    name: str
    deck: list[Card] = field(default_factory=list)
    hand: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    prizes: list[Card] = field(default_factory=list)
    active: Optional[InPlayPokemon] = None
    bench: list[InPlayPokemon] = field(default_factory=list)

    # per-turn flags the rules reset
    energy_attached_this_turn: bool = False
    supporter_played_this_turn: bool = False
    turns_taken: int = 0          # for the "no evolving on your first turn" rule

    MAX_BENCH = 5

    def all_in_play(self) -> list[InPlayPokemon]:
        return ([self.active] if self.active else []) + self.bench

    def has_pokemon_in_play(self) -> bool:
        return self.active is not None or len(self.bench) > 0

    def draw(self, n: int = 1) -> int:
        """Draw up to n cards. Returns how many were actually drawn."""
        drawn = 0
        for _ in range(n):
            if not self.deck:
                break
            self.hand.append(self.deck.pop(0))
            drawn += 1
        return drawn


@dataclass
class GameState:
    players: tuple[PlayerState, PlayerState]
    rng: random.Random
    active_index: int = 0          # whose turn it is (0 or 1)
    turn_number: int = 0
    phase: Phase = Phase.SETUP
    winner: Optional[int] = None   # 0, 1, or None (None + GAME_OVER = tie)
    log: list[str] = field(default_factory=list)
    db: Optional[object] = None    # CardDB, for searches / evolution-chain lookups

    @property
    def current(self) -> PlayerState:
        return self.players[self.active_index]

    @property
    def opponent(self) -> PlayerState:
        return self.players[1 - self.active_index]

    def opponent_index(self) -> int:
        return 1 - self.active_index

    def emit(self, msg: str) -> None:
        self.log.append(f"T{self.turn_number} P{self.active_index}: {msg}")
