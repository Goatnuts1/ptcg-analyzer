#!/usr/bin/env python3
"""
decks.py — test deck fixtures for exercising the engine.

ELI15: a deck is 60 cards. These are NOT tournament lists — they're minimal,
legal-shaped fixtures using real cards from the pool so the engine has something
to play. Real archetype decklists come later once effects are implemented.

A deck is given as a list of (card_name, count) and expanded into Card objects.
"""

from __future__ import annotations

from .cards import Card, CardDB
from .legality import DECK_SIZE   # single source of truth for the 60-card rule


def _expand(db: CardDB, recipe: list[tuple[str, int]]) -> list[Card]:
    cards: list[Card] = []
    for name, count in recipe:
        card = db.get(name)
        cards.extend([card] * count)
    if len(cards) != DECK_SIZE:
        raise ValueError(f"deck has {len(cards)} cards, expected {DECK_SIZE}")
    return cards


# Two simple single-Basic-attacker decks. Both rely only on base damage, so they
# run correctly even with attack effects still stubbed.
DECK_LIGHTNING = [
    ("Pikachu ex", 4),            # 200 HP, Thunderbolt: LLC for 120
    ("Miraidon", 4),              # 110 HP, Peak Acceleration: C for 40
    ("Iron Thorns", 2),           # 140 HP attacker
    ("Basic Lightning Energy", 30),
    ("Basic Psychic Energy", 20),
]

DECK_GRASS = [
    ("Sprigatito ex", 4),         # 200 HP, Scratch: C for 20
    ("Flutter Mane", 4),          # 90 HP, Hex Hurl: CCC for 90
    ("Koraidon", 2),
    ("Basic Grass Energy", 30),
    ("Basic Fighting Energy", 20),
]

# A Dragapult line deck to exercise effects (Phantom Dive spread, Recon Directive).
# Still a fixture, not a tournament list — no Trainers/draw support yet, so the
# evolution line completes only sometimes. Good enough to see effects fire.
# A more realistic Dragapult line deck WITH a Trainer engine. Rare Candy skips
# Drakloak, Buddy-Buddy Poffin fetches Dreepy, Cheren refuels. Still not a
# tournament list, but it actually functions — Dragapult attacks far sooner.
DECK_DRAGAPULT = [
    ("Dreepy", 4),
    ("Drakloak", 2),
    ("Dragapult ex", 3),
    ("Flutter Mane", 2),          # Basic attacker / opener
    ("Rare Candy", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Cheren", 4),
    ("Boss's Orders", 2),
    ("Basic Fire Energy", 16),
    ("Basic Psychic Energy", 19),
]


def load_test_decks(db: CardDB) -> tuple[list[Card], list[Card]]:
    return _expand(db, DECK_LIGHTNING), _expand(db, DECK_GRASS)


def load_dragapult_vs_lightning(db: CardDB) -> tuple[list[Card], list[Card]]:
    return _expand(db, DECK_DRAGAPULT), _expand(db, DECK_LIGHTNING)


# Mega Charizard X ex line: Charmander -> Charmeleon -> Mega Charizard X ex (360 HP,
# gives up 3 prizes). Inferno X discards Fire Energy for 90 each. Rare Candy skips
# Charmeleon. A real, currently-legal Stage 2 MEGA archetype.
DECK_CHARIZARD = [
    ("Charmander", 4),
    ("Charmeleon", 2),
    ("Mega Charizard X ex", 3),
    ("Flutter Mane", 2),          # Basic opener / attacker
    ("Rare Candy", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Cheren", 4),
    ("Boss's Orders", 2),
    ("Basic Fire Energy", 35),
]


def load_charizard_vs_dragapult(db: CardDB) -> tuple[list[Card], list[Card]]:
    return _expand(db, DECK_CHARIZARD), _expand(db, DECK_DRAGAPULT)


# --------------------------------------------------------------------------- #
# TOURNAMENT LISTS — the real 60-card decklists the validation milestone targets.
# Unlike the fixtures above, these are faithful copies of current Limitless lists
# (see docs/CARD_GAP_REPORT.md for sources). They will NOT play correctly until the
# effects/infra in docs/VALIDATION_MILESTONE.md are built — that's the point: the
# coverage test (tests/test_decklist_coverage.py) burns these down to zero gaps.
# Basic energy uses the engine's injected name ("Basic Fire Energy"); the printed
# lists just say "Fire Energy".
# --------------------------------------------------------------------------- #

# Dragapult ex (Dusknoir variant) — Justin Newdorf, 3rd, Regional Indianapolis,
# May 30 2026. limitlesstcg.com/decks/list/27610.
TOURNAMENT_DRAGAPULT = [
    # Pokémon (21)
    ("Dreepy", 4),
    ("Drakloak", 4),
    ("Dragapult ex", 3),
    ("Duskull", 2),
    ("Dusclops", 2),
    ("Dusknoir", 1),
    ("Fezandipiti ex", 1),
    ("Munkidori", 1),
    ("Budew", 1),
    ("Meowth ex", 1),
    ("Moltres", 1),
    # Trainer (31)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Crispin", 3),
    ("Dawn", 1),
    ("Buddy-Buddy Poffin", 4),
    ("Poké Pad", 4),
    ("Ultra Ball", 4),
    ("Crushing Hammer", 3),
    ("Night Stretcher", 2),
    ("Unfair Stamp", 1),
    ("Team Rocket's Watchtower", 2),
    # Energy (8)
    ("Basic Fire Energy", 4),
    ("Basic Psychic Energy", 3),
    ("Basic Darkness Energy", 1),
]

# Mega Charizard X/Y ex toolbox — Khaine, 3rd of 21, Ling TV ARENA (online),
# May 2026, post-rotation. play.limitlesstcg.com/.../khaine/decklist.
TOURNAMENT_CHARIZARD_XY = [
    # Pokémon (16)
    ("Dunsparce", 3),
    ("Dudunsparce", 2),
    ("Charmander", 3),
    ("Charmeleon", 1),
    ("Mega Charizard X ex", 2),
    ("Mega Charizard Y ex", 1),
    ("Oricorio ex", 2),
    ("Fezandipiti ex", 1),
    ("Fan Rotom", 1),
    # Trainer (33)
    ("Hilda", 3),
    ("Lillie's Determination", 3),
    ("Dawn", 3),
    ("Judge", 2),
    ("Boss's Orders", 2),
    ("Rare Candy", 3),
    ("Poké Pad", 3),
    ("Buddy-Buddy Poffin", 2),
    ("Energy Retrieval", 2),
    ("Night Stretcher", 2),
    ("Ultra Ball", 2),
    ("Switch", 1),
    ("Air Balloon", 1),
    ("Powerglass", 1),
    ("Battle Cage", 3),
    # Energy (11)
    ("Basic Fire Energy", 10),
    ("Enriching Energy", 1),
]

# name -> recipe, for the coverage test and future matchup runs.
TOURNAMENT_LISTS: dict[str, list[tuple[str, int]]] = {
    "dragapult": TOURNAMENT_DRAGAPULT,
    "charizard_xy": TOURNAMENT_CHARIZARD_XY,
}


def load_tournament_deck(db: CardDB, name: str) -> list[Card]:
    """Expand a registered tournament list into Card objects (validates 60 cards)."""
    return _expand(db, TOURNAMENT_LISTS[name])
