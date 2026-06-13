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


# --------------------------------------------------------------------------- #
# Raging Bolt ex — a third functional archetype (core-stabilization milestone).
# Built to EXERCISE the new staple cards in live games: Carmine/Lacey/Kofu/Cyrano/
# Colress's Tenacity/Drayton/Lana's Aid (draw+search), Pokégear/Poké Ball/Dusk-style
# search, Energy Switch/Recycler/Sacred Ash (recovery+accel), Pokémon Catcher (gust),
# Master Ball (ACE SPEC), Klefki (Stick 'n' Draw). Raging Bolt ex's Bellowing Thunder
# discards Basic Energy for 70 each, so the deck runs a heavy Lightning/Fighting base.
# --------------------------------------------------------------------------- #
DECK_RAGING_BOLT = [
    # Pokémon (12)
    ("Raging Bolt ex", 4),
    ("Tapu Koko ex", 2),         # Linked Lightning — fast Lightning secondary attacker
    ("Hoothoot", 3),
    ("Noctowl", 2),
    ("Klefki", 1),
    # Supporters (10)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 1),
    ("Colress's Tenacity", 1),
    ("Kofu", 1),
    ("Drayton", 1),
    ("Lana's Aid", 1),
    # Items (23)
    ("Pokégear 3.0", 3),
    ("Poké Ball", 3),
    ("Buddy-Buddy Poffin", 3),
    ("Energy Switch", 2),
    ("Energy Recycler", 2),
    ("Pokémon Catcher", 2),
    ("Boss's Orders", 2),
    ("Ultra Ball", 2),
    ("Sacred Ash", 1),
    ("Master Ball", 1),          # ACE SPEC
    ("Switch", 1),
    ("Night Stretcher", 1),
    # Energy (15)
    ("Basic Lightning Energy", 8),
    ("Basic Fighting Energy", 7),
]


# --------------------------------------------------------------------------- #
# feature/more-cards — three more archetypes that exercise the new card effects
# in live games. Each is a legal 60 (validated in tests/test_decklist_coverage
# style; checked by tests/test_more_cards.py). Energy bases match the attackers'
# printed costs so they actually function under greedy.
# --------------------------------------------------------------------------- #

# Mega Gardevoir ex (Psychic): Ralts -> Kirlia -> Mega Gardevoir ex (Overflowing
# Wishes accel + Mega Symphonia scaling), backed by Basic Psychic ex attackers
# (Mega Diancie, Iron Crown, Latias).
DECK_GARDEVOIR = [
    # Pokémon (16)
    ("Ralts", 4),
    ("Kirlia", 4),
    ("Mega Gardevoir ex", 3),
    ("Mega Diancie ex", 2),
    ("Iron Crown ex", 2),
    ("Latias ex", 1),
    # Supporters (12)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 2),
    ("Kofu", 1),
    ("Drayton", 1),
    ("Boss's Orders", 3),
    # Items (17)
    ("Rare Candy", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Ultra Ball", 3),
    ("Poké Pad", 2),
    ("Pokégear 3.0", 2),
    ("Switch", 1),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (15)
    ("Basic Psychic Energy", 15),
]

# Colorless toolbox: Lugia / Snorlax / Cyclizar / Mega Kangaskhan / Terapagos —
# all attack with Colorless-cost moves, so a single basic-energy base powers them.
DECK_COLORLESS = [
    # Pokémon (10)
    ("Lugia ex", 4),
    ("Snorlax ex", 2),
    ("Cyclizar ex", 2),
    ("Mega Kangaskhan ex", 1),
    ("Terapagos ex", 1),
    # Supporters (11)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 2),
    ("Kofu", 2),
    ("Boss's Orders", 2),
    # Items (22)
    ("Buddy-Buddy Poffin", 4),
    ("Ultra Ball", 4),
    ("Poké Pad", 3),
    ("Pokégear 3.0", 3),
    ("Energy Switch", 2),
    ("Switch", 2),
    ("Night Stretcher", 2),
    ("Sacred Ash", 1),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (17)
    ("Basic Water Energy", 17),  # Colorless costs accept any type
]

# Fire: Reshiram (Scorching Fire) / Volcanion (Scorching Cyclone) / Ethan's Ho-Oh
# (Shining Feathers heal), heavy Fire base with recovery.
DECK_FIRE = [
    # Pokémon (9)
    ("Reshiram ex", 4),
    ("Volcanion ex", 3),
    ("Ethan's Ho-Oh ex", 2),
    # Supporters (11)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 1),
    ("Crispin", 2),              # Basic-energy accel
    ("Boss's Orders", 3),
    # Items (20)
    ("Buddy-Buddy Poffin", 3),
    ("Ultra Ball", 3),
    ("Poké Pad", 2),
    ("Pokégear 3.0", 3),
    ("Energy Switch", 2),
    ("Energy Recycler", 2),
    ("Switch", 2),
    ("Sacred Ash", 2),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (20)
    ("Basic Fire Energy", 20),
]


# --------------------------------------------------------------------------- #
# feature/more-decks — four more archetypes (Fighting / Dark / Metal / Water) so
# the round-robin meta matrix stays meaningful. Each a legal 60, energy base
# matched to its attackers' costs.
# --------------------------------------------------------------------------- #

# Fighting (Mega Lucario): Riolu -> Mega Lucario ex (Aura Jab discard-accel),
# with Regirock (Regi Charge accel + Giant Rock anti-Stage2), Iron Boulder, Koraidon.
DECK_FIGHTING = [
    # Pokémon (11) — A/B tuned: maxed Lucario line (4/4) for consistency and cut
    # Koraidon ex (its Kaiser Tackle needs Fire, dead in a mono-Fighting deck).
    # +8pts overall vs the old build, and flips gardevoir from 33% to favorable.
    ("Mega Lucario ex", 4),
    ("Riolu", 4),
    ("Regirock ex", 2),
    ("Iron Boulder ex", 1),
    # Supporters (10)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 2),
    ("Boss's Orders", 3),
    # Items (22)
    ("Buddy-Buddy Poffin", 4),
    ("Ultra Ball", 3),
    ("Pokégear 3.0", 3),
    ("Crispin", 3),
    ("Poké Pad", 2),
    ("Energy Switch", 2),
    ("Sacred Ash", 2),
    ("Switch", 2),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (17)
    ("Basic Fighting Energy", 17),
]

# Dark (Mega Absol): Terminal Period finisher + Claw of Darkness disruption, with
# Darkrai ex (plain hitter) and Munkidori (Adrena-Brain counter-shift).
DECK_DARK = [
    # Pokémon (9)
    ("Mega Absol ex", 3),
    ("Darkrai ex", 3),
    ("Munkidori", 3),
    # Supporters (10)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 2),
    ("Boss's Orders", 3),
    # Items (22)
    ("Buddy-Buddy Poffin", 3),
    ("Ultra Ball", 3),
    ("Pokégear 3.0", 3),
    ("Crispin", 3),
    ("Poké Pad", 2),
    ("Energy Switch", 2),
    ("Night Stretcher", 2),
    ("Switch", 2),
    ("Sacred Ash", 1),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (19)
    ("Basic Darkness Energy", 19),
]

# Metal (Mega Mawile): Gobble Down (prize-scaling) + Huge Bite, with Hop's Zacian
# (Insta-Strike bench snipe), Genesect (plain), Klefki (Stick 'n' Draw).
DECK_METAL = [
    # Pokémon (10)
    ("Mega Mawile ex", 3),
    ("Hop's Zacian ex", 3),
    ("Genesect ex", 2),
    ("Klefki", 2),
    # Supporters (11)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 3),
    ("Boss's Orders", 3),
    # Items (22)
    ("Buddy-Buddy Poffin", 4),
    ("Ultra Ball", 3),
    ("Pokégear 3.0", 3),
    ("Crispin", 3),
    ("Poké Pad", 2),
    ("Energy Switch", 2),
    ("Switch", 2),
    ("Sacred Ash", 2),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (17)
    ("Basic Metal Energy", 17),
]

# Water (Dondozo / Lapras): Avenging Billow + Dynamic Dive bruiser, Lapras Power
# Splash (energy-scaling), Keldeo backup.
DECK_WATER = [
    # Pokémon (10)
    ("Dondozo ex", 3),
    ("Lapras ex", 3),
    ("Keldeo ex", 2),
    ("Hoothoot", 2),
    # Supporters (11)
    ("Carmine", 3),
    ("Lacey", 2),
    ("Cyrano", 3),
    ("Boss's Orders", 3),
    # Items (22)
    ("Buddy-Buddy Poffin", 3),
    ("Ultra Ball", 3),
    ("Pokégear 3.0", 3),
    ("Crispin", 3),
    ("Poké Pad", 2),
    ("Energy Switch", 2),
    ("Switch", 2),
    ("Sacred Ash", 2),
    ("Night Stretcher", 1),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (17)
    ("Basic Water Energy", 17),
]


# --------------------------------------------------------------------------- #
# Unified deck registry for the CLI. Friendly name -> recipe. Covers the real
# tournament lists and the playable archetypes; fixtures stay out (they're for
# engine tests, not matchups).
# --------------------------------------------------------------------------- #
# Mega Greninja ex (Water, Stage 2 MEGA) — the snipe/spread board-control deck.
# Froakie -> Frogadier -> Mega Greninja ex (Rare Candy skips Frogadier). Mortal
# Shuriken places 60 on any opponent Pokémon each turn (discarding a Basic Water from
# hand), so the deck runs a heavy Water base + recovery (Energy Recycler / Night
# Stretcher) to keep feeding it; Ninja Spinner returns Water to hand to refuel it.
DECK_GRENINJA = [
    # Pokémon (10) — 4 Mega Greninja for setup consistency (A/B tested: +5% vs a 3-of)
    ("Froakie", 4),
    ("Frogadier", 2),
    ("Mega Greninja ex", 4),
    # Supporters (11)
    ("Carmine", 4),
    ("Lacey", 2),
    ("Cyrano", 2),
    ("Boss's Orders", 3),
    # Items (23)
    ("Rare Candy", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Ultra Ball", 4),
    ("Poké Pad", 3),
    ("Switch", 2),
    ("Night Stretcher", 2),
    ("Energy Recycler", 2),
    ("Sacred Ash", 1),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (16)
    ("Basic Water Energy", 16),
]

DECKS: dict[str, list[tuple[str, int]]] = {
    "dragapult": TOURNAMENT_DRAGAPULT,
    "charizard_xy": TOURNAMENT_CHARIZARD_XY,
    "raging_bolt": DECK_RAGING_BOLT,
    "gardevoir": DECK_GARDEVOIR,
    "colorless": DECK_COLORLESS,
    "fire": DECK_FIRE,
    "fighting": DECK_FIGHTING,
    "dark": DECK_DARK,
    "metal": DECK_METAL,
    "water": DECK_WATER,
    "greninja": DECK_GRENINJA,
}


def load_deck(db: CardDB, name: str) -> list[Card]:
    """Expand any registered deck by friendly name (validates the 60-card rule)."""
    if name not in DECKS:
        raise KeyError(f"unknown deck {name!r}; choose from: {', '.join(sorted(DECKS))}")
    return _expand(db, DECKS[name])
