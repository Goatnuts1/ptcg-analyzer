#!/usr/bin/env python3
"""
cards.py — typed Card objects + a loader that reads the data-layer pool.

ELI15: the pool is a big list of plain dictionaries. The engine wants real
objects it can ask questions of ("is this a Basic Pokemon?", "what does this
attack cost?"). This file turns dicts into Card objects and provides a CardDB
you can look cards up in by name.

NOTE — basic energy: basic Energy cards (Grass, Fire, ...) are ALWAYS legal and
carry no regulation mark, so the data-layer filter drops them. The engine needs
them, so we inject them here as synthetic cards. This is the one place the engine
adds cards the pool doesn't contain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

# The basic energy types that exist as physical "Basic Energy" cards.
BASIC_ENERGY_TYPES = ["Grass", "Fire", "Water", "Lightning", "Psychic",
                      "Fighting", "Darkness", "Metal"]


@dataclass(frozen=True)
class Attack:
    name: str
    cost: tuple[str, ...]          # e.g. ("Lightning", "Colorless")
    damage: int                    # base damage, 0 if none/variable
    damage_suffix: str             # "", "×", "+" — flags variable damage we don't model yet
    text: str                      # raw effect text (NOT yet parsed)

    @property
    def cost_size(self) -> int:
        return len(self.cost)


@dataclass(frozen=True)
class Ability:
    name: str
    text: str


@dataclass(frozen=True)
class Card:
    id: str
    name: str
    supertype: str                 # "Pokémon" | "Trainer" | "Energy"
    subtypes: tuple[str, ...]
    hp: Optional[int]
    types: tuple[str, ...]
    evolves_from: Optional[str]
    evolves_to: tuple[str, ...]
    abilities: tuple[Ability, ...]
    attacks: tuple[Attack, ...]
    rules: tuple[str, ...]
    weaknesses: tuple[tuple[str, str], ...]   # (type, value) e.g. ("Fire", "×2")
    resistances: tuple[tuple[str, str], ...]
    retreat_cost: int                          # number of energy to retreat
    regulation_mark: Optional[str]

    # --- convenience predicates the engine leans on ---
    @property
    def is_pokemon(self) -> bool:
        return self.supertype == "Pokémon"

    @property
    def is_trainer(self) -> bool:
        return self.supertype == "Trainer"

    @property
    def is_energy(self) -> bool:
        return self.supertype == "Energy"

    @property
    def is_basic(self) -> bool:
        return "Basic" in self.subtypes

    @property
    def is_basic_energy(self) -> bool:
        return self.is_energy and "Basic" in self.subtypes

    @property
    def is_supporter(self) -> bool:
        return "Supporter" in self.subtypes

    @property
    def is_item(self) -> bool:
        return "Item" in self.subtypes

    @property
    def gives_up_prizes(self) -> int:
        # Mega Evolution ex give up 3 prizes when KO'd (per their printed rule);
        # other ex give 2; everything else gives 1.
        subs = [s.lower() for s in self.subtypes]
        if "ex" in subs and "mega" in subs:
            return 3
        if "ex" in subs:
            return 2
        return 1


def _parse_damage(raw: str) -> tuple[int, str]:
    """'120' -> (120, ''); '70×' -> (70, '×'); '' -> (0, '')."""
    if not raw:
        return 0, ""
    suffix = ""
    if raw and raw[-1] in "×+-":
        suffix = raw[-1]
        raw = raw[:-1]
    try:
        return int(raw), suffix
    except ValueError:
        return 0, suffix


def card_from_dict(d: dict) -> Card:
    attacks = tuple(
        Attack(
            name=a.get("name", ""),
            cost=tuple(a.get("cost", [])),
            damage=_parse_damage(a.get("damage", ""))[0],
            damage_suffix=_parse_damage(a.get("damage", ""))[1],
            text=a.get("text", ""),
        )
        for a in d.get("attacks", [])
    )
    abilities = tuple(Ability(name=a.get("name", ""), text=a.get("text", ""))
                      for a in d.get("abilities", []))
    return Card(
        id=d["id"],
        name=d["name"],
        supertype=d["supertype"],
        subtypes=tuple(d.get("subtypes", [])),
        hp=d.get("hp"),
        types=tuple(d.get("types", [])),
        evolves_from=d.get("evolvesFrom"),
        evolves_to=tuple(d.get("evolvesTo", [])),
        abilities=abilities,
        attacks=attacks,
        rules=tuple(d.get("rules", [])),
        weaknesses=tuple((w["type"], w["value"]) for w in d.get("weaknesses", [])),
        resistances=tuple((r["type"], r["value"]) for r in d.get("resistances", [])),
        retreat_cost=len(d.get("retreatCost", [])),
        regulation_mark=d.get("regulationMark"),
    )


def _synthetic_basic_energy() -> list[Card]:
    """The basic energy cards the pool filter drops. Each just provides its type."""
    out = []
    for t in BASIC_ENERGY_TYPES:
        out.append(Card(
            id=f"basic-{t.lower()}", name=f"Basic {t} Energy", supertype="Energy",
            subtypes=("Basic",), hp=None, types=(t,), evolves_from=None, evolves_to=(),
            abilities=(), attacks=(), rules=(f"Provides {t} energy.",),
            weaknesses=(), resistances=(), retreat_cost=0, regulation_mark=None,
        ))
    return out


class CardDB:
    """Look cards up by name. Includes injected basic energy."""

    def __init__(self, cards: list[Card]):
        self._by_name = {c.name: c for c in cards}

    @classmethod
    def from_pool(cls, path: str = "data/standard_pool.json") -> "CardDB":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        cards = [card_from_dict(d) for d in raw] + _synthetic_basic_energy()
        return cls(cards)

    def get(self, name: str) -> Card:
        if name not in self._by_name:
            raise KeyError(f"card not in DB: {name!r}")
        return self._by_name[name]

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)

    def names(self) -> list[str]:
        """All known card names (used by the deck importer to match by name)."""
        return list(self._by_name)
