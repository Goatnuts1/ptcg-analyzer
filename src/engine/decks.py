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
    # Pokémon (14) — A/B tuned: pure Mega Gardevoir line (4 of the Stage 2 for
    # consistency) + Mega Diancie ex, dropping Iron Crown/Latias. Mega Symphonia
    # scales with Psychic Energy on ALL your Pokémon, so going all-in on the
    # Overflowing-Wishes accel + a heavy Energy base hits much harder (+7pts overall).
    ("Ralts", 4),
    ("Kirlia", 4),
    ("Mega Gardevoir ex", 4),
    ("Mega Diancie ex", 2),
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
    # Energy (17)
    ("Basic Psychic Energy", 17),
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

# Beedrill ex (Grass swarm) — added after a live game where it hard-countered the
# fighting deck. Weedle -> Kakuna -> Beedrill ex (Rare Candy skips Kakuna); Rumbling
# Bees scales 110× per Beedrill in play, and the line rebuilds via Night Stretcher /
# Sacred Ash / Poffin. A fast 2-prize swarm — the kind of deck the closed sim lacked.
# (Grand Tree's evolve-accel and Forest of Vitality are out of scope, so this build is
# a touch slower than the real one — a conservative estimate of the matchup.)
DECK_BEEDRILL = [
    # Pokémon (10)
    ("Weedle", 4),
    ("Kakuna", 2),
    ("Beedrill ex", 4),
    # Supporters (11)
    ("Carmine", 4),
    ("Lacey", 2),
    ("Cyrano", 2),
    ("Boss's Orders", 3),
    # Items (25)
    ("Rare Candy", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Ultra Ball", 4),
    ("Poké Pad", 3),
    ("Pokégear 3.0", 3),
    ("Night Stretcher", 2),
    ("Sacred Ash", 2),
    ("Switch", 2),
    ("Master Ball", 1),          # ACE SPEC
    # Energy (14)
    ("Basic Grass Energy", 14),
]

# Crustle wall-toolbox ("No Vacancy") — Dwebble/Crustle (Mysterious Rock Inn walls
# vs opponent's ex) backed by Milotic ex (Sparkling Scales wall vs Tera) and
# Cornerstone Mask Ogerpon ex (Cornerstone Stance wall vs Abilities), Budew/Munkidori
# for Psychic utility, Bloodmoon Ursaluna ex as the prize-discount finisher. Heavy
# hammer/disruption suite (Crushing Hammer/Enhanced Hammer/Special Red Card/Eri)
# on top of the Poffin/Night Stretcher recovery engine. Grass/Water/Darkness base.
DECK_NO_VACANCY = [
    # Pokémon (16)
    ("Dwebble", 3),
    ("Crustle", 3),
    ("Feebas", 2),
    ("Milotic ex", 2),
    ("Cornerstone Mask Ogerpon ex", 1),
    ("Budew", 2),
    ("Munkidori", 2),
    ("Bloodmoon Ursaluna ex", 1),
    # Trainers (30)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Eri", 2),
    ("Unfair Stamp", 1),          # ACE SPEC
    ("Crushing Hammer", 4),
    ("Enhanced Hammer", 3),
    ("Buddy-Buddy Poffin", 4),
    ("Night Stretcher", 2),
    ("Special Red Card", 2),
    ("Ultra Ball", 2),            # flex — search
    ("Switch", 2),                # flex — retreat utility
    ("Poké Pad", 1),              # flex — search
    # Energy (14)
    ("Basic Grass Energy", 5),
    ("Basic Water Energy", 5),
    ("Basic Darkness Energy", 4),
]

# Crustle wall-toolbox variant ("Innkeeper") — same wall core, doubled up on
# Ogerpon/Budew/Eri for a more disruption-heavy, less prize-race-dependent build;
# swaps Unfair Stamp for Scoop Up Cyclone (bounce-and-reset the wall/finisher) and
# drops the Bloodmoon Ursaluna ex finisher line entirely.
DECK_INNKEEPER = [
    # Pokémon (17)
    ("Dwebble", 3),
    ("Crustle", 3),
    ("Feebas", 2),
    ("Milotic ex", 2),
    ("Cornerstone Mask Ogerpon ex", 2),
    ("Budew", 3),
    ("Munkidori", 2),
    # Trainers (29)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 2),
    ("Eri", 3),
    ("Scoop Up Cyclone", 1),      # ACE SPEC
    ("Crushing Hammer", 4),
    ("Enhanced Hammer", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Night Stretcher", 2),
    ("Special Red Card", 2),
    ("Ultra Ball", 2),            # flex — search
    ("Switch", 1),                # flex — retreat utility
    # Energy (14)
    ("Basic Grass Energy", 5),
    ("Basic Water Energy", 5),
    ("Basic Darkness Energy", 4),
]

# --------------------------------------------------------------------------- #
# Clefairy / Mega Kangaskhan ex (James Kowalski's NAIC 2026-winning list) and a
# trap-leaning variant. "Telepathic Psychic Energy" does not resolve in the pool
# (not yet fetched/implemented) — substituted with 1 extra Basic Psychic Energy
# per the fallback instruction, noted here and in the validation report.
# --------------------------------------------------------------------------- #
DECK_CLEFAIRY_STOCK = [
    # Pokémon (22)
    ("Mega Kangaskhan ex", 4),
    ("Meowth ex", 4),
    ("Lillie's Clefairy ex", 4),
    ("Latias ex", 3),
    ("Wellspring Mask Ogerpon ex", 2),
    ("Fezandipiti ex", 2),
    ("Moltres", 1),
    ("Chien-Pao", 1),
    ("Koraidon ex (ASC)", 1),
    # Trainer (28)
    ("Crispin", 4),
    ("Boss's Orders", 3),
    ("Ciphermaniac's Codebreaking", 2),
    ("Cyrano", 1),
    ("Ultra Ball", 4),
    ("Dusk Ball", 4),
    ("Wondrous Patch", 3),
    ("Prime Catcher", 1),
    ("Lillie's Pearl", 2),
    ("Area Zero Underdepths", 4),
    # Energy (10) — SUBSTITUTION: "Telepathic Psychic Energy" not in pool;
    # replaced 1x with Basic Psychic Energy (5 total instead of printed 4+1).
    ("Basic Psychic Energy", 5),
    ("Basic Water Energy", 2),
    ("Basic Fighting Energy", 2),
    ("Basic Fire Energy", 1),
]

# Trap variant: same shell, Latias ex 3->2 and Chien-Pao 1->3, Koraidon ex 1->0.
DECK_CLEFAIRY_MODIFIED = [
    # Pokémon (22)
    ("Mega Kangaskhan ex", 4),
    ("Meowth ex", 4),
    ("Lillie's Clefairy ex", 4),
    ("Latias ex", 2),
    ("Wellspring Mask Ogerpon ex", 2),
    ("Fezandipiti ex", 2),
    ("Moltres", 1),
    ("Chien-Pao", 3),
    # Trainer (28) — identical to clefairy_stock
    ("Crispin", 4),
    ("Boss's Orders", 3),
    ("Ciphermaniac's Codebreaking", 2),
    ("Cyrano", 1),
    ("Ultra Ball", 4),
    ("Dusk Ball", 4),
    ("Wondrous Patch", 3),
    ("Prime Catcher", 1),
    ("Lillie's Pearl", 2),
    ("Area Zero Underdepths", 4),
    # Energy (10) — same substitution as clefairy_stock
    ("Basic Psychic Energy", 5),
    ("Basic Water Energy", 2),
    ("Basic Fighting Energy", 2),
    ("Basic Fire Energy", 1),
]

# --------------------------------------------------------------------------- #
# Cornerstone Box — NOT a tournament list; a deck-guide build (same provenance
# class as `doublade`), authored specifically as an anti-clefairy_stock tech
# piece. No real "Cornerstone Stance" archetype exists at time of writing
# (confirmed via research: TWM 112 appears only as a rare 1-of tech inside real
# Crustle lists at NAIC 2026, never as a core piece — the best-finishing real
# Crustle pilot actually cut it). The thesis: Cornerstone Mask Ogerpon ex's
# Cornerstone Stance ("Prevent all damage from attacks done to this Pokémon by
# your opponent's Pokémon that have an Ability") no-sells nearly every real
# clefairy_stock attacker, since Mega Kangaskhan ex (Run Errand), Latias ex
# (Skyliner), Fezandipiti ex (Flip the Script), and Meowth ex (Last-Ditch
# Catch) all carry named Abilities. Its blind spot: Wellspring Mask Ogerpon ex,
# Moltres, and Koraidon ex (ASC) have no Ability and can still damage it.
# Regirock ex and Iron Boulder ex (both real Basic Fighting ex, both already
# implemented) round out the attack line for matchups where the wall alone
# isn't the win condition; Kieran's flat +30 vs ex/V matters here because
# literally all 22 of clefairy_stock's Pokémon are "ex". All three Pokémon are
# Basic — no evolution tax, same Big-Basics philosophy as the deck it targets.
# --------------------------------------------------------------------------- #
DECK_CORNERSTONE_BOX = [
    # Pokémon (12)
    ("Cornerstone Mask Ogerpon ex", 4),
    ("Regirock ex", 4),
    ("Iron Boulder ex", 4),
    # Trainer (30)
    ("Ultra Ball", 4),
    ("Dusk Ball", 4),
    ("Crispin", 4),
    ("Boss's Orders", 4),
    ("Kieran", 4),
    ("Special Red Card", 2),
    ("Night Stretcher", 2),
    ("Team Rocket's Petrel", 2),
    ("Area Zero Underdepths", 3),
    ("Precious Trolley", 1),
    # Energy (18)
    ("Basic Fighting Energy", 18),
]

# --------------------------------------------------------------------------- #
# The Vault — max-denial No Vacancy variant. Same Dwebble/Crustle/Milotic ex
# wall core as no_vacancy/innkeeper, but leans harder into denial: Lillie's
# Determination + Eri draw/disruption, a max Crushing Hammer + Enhanced Hammer
# energy-denial suite, and Special Red Card for hand disruption, with
# Bloodmoon Ursaluna ex as the prize-discount finisher.
# --------------------------------------------------------------------------- #
DECK_THE_VAULT = [
    # Pokémon (17)
    ("Dwebble", 3),
    ("Crustle", 3),
    ("Feebas", 2),
    ("Milotic ex", 2),
    ("Cornerstone Mask Ogerpon ex", 1),
    ("Budew", 3),
    ("Munkidori", 2),
    ("Bloodmoon Ursaluna ex", 1),
    # Trainer (29)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Eri", 3),
    ("Crushing Hammer", 4),
    ("Enhanced Hammer", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Night Stretcher", 2),
    ("Special Red Card", 2),
    ("Ultra Ball", 1),
    ("Switch", 1),
    ("Poké Pad", 1),
    # Energy (14)
    ("Basic Grass Energy", 5),
    ("Basic Water Energy", 5),
    ("Basic Darkness Energy", 4),
]

# --------------------------------------------------------------------------- #
# Alakazam / Dudunsparce (MEG "Psychic Draw"/"Powerful Hand") — from research
# List 1 (Cerys Jones, 1st, Regional Indianapolis). "Telepathic Psychic Energy"
# does not resolve in the pool — substituted with Basic Psychic Energy (the
# printed "Psychic Energy (MEE)" basic is likewise mapped to the engine's
# injected "Basic Psychic Energy"), noted here and in the validation report.
# --------------------------------------------------------------------------- #
DECK_ALAKAZAM = [
    # Pokémon (22)
    ("Abra", 4),
    ("Kadabra", 4),
    ("Alakazam", 3),
    ("Dunsparce", 3),
    ("Dudunsparce", 3),
    ("Fezandipiti ex", 1),
    ("Dedenne", 1),
    ("Elgyem", 1),
    ("Genesect", 1),
    ("Psyduck", 1),
    # Trainer (32)
    ("Dawn", 4),
    ("Hilda", 3),
    ("Boss's Orders", 2),
    ("Lana's Aid", 1),
    ("Buddy-Buddy Poffin", 4),
    ("Poké Pad", 4),
    ("Rare Candy", 3),
    ("Enhanced Hammer", 2),
    ("Sacred Ash", 1),
    ("Night Stretcher", 1),
    ("Handheld Fan", 2),
    ("Lucky Helmet", 1),
    ("Nighttime Mine", 4),
    # Energy (6) — SUBSTITUTION: "Telepathic Psychic Energy" x4 and the printed
    # basic "Psychic Energy" x1 both map to Basic Psychic Energy (5 total).
    ("Basic Psychic Energy", 5),
    ("Enriching Energy", 1),
]

# --------------------------------------------------------------------------- #
# Starmie/Greninja Water toolbox ("Ninja and the Stars") — Mega Starmie ex
# (Jetting Blow bench-poke / Nebula Beam wall-piercing finisher) backed by Mega
# Greninja ex (Mortal Shuriken spread), Meowth ex (Search or Not) and
# Fezandipiti ex (Flip the Script) for utility, on a Surfing Beach + Hilda +
# Lillie's Determination + Poké Pad draw/search Water base. Adapted from a
# PokeBeach forum primer decklist to what's implemented in this pool.
#
# Primer list only sums to 42 (13 Pokemon + 17 Trainer + 12 Energy). Per task
# instructions, added 18 flex copies of already-implemented/already-in-list
# cards to reach exactly 60, preferring Poke Pad/Boss's Orders/Buddy-Buddy
# Poffin/Ultra Ball/extra Basic Water Energy (respecting the 4-copy max):
#   - Poke Pad is already at 4 (max) -> could not add more.
#   - Boss's Orders 3 -> 4 (+1, now at max).
#   - Buddy-Buddy Poffin 0 -> 4 (+4, new staple search-a-Basic support card).
#   - Ultra Ball 0 -> 4 (+4, new staple search).
#   - Basic Water Energy 9 -> 18 (+9, remainder, to round out the energy base).
# +1+4+4+9 = 18 added, exactly closing the 42 -> 60 gap.
# "Ignition Energy" DOES resolve in the pool (rsv10pt5-86, mark I) so it is
# used as printed — no substitution needed.
# --------------------------------------------------------------------------- #
DECK_STARMIE_TOOLBOX = [
    # Pokemon (13)
    ("Staryu", 2),
    ("Mega Starmie ex", 2),
    ("Froakie", 3),
    ("Frogadier", 2),
    ("Mega Greninja ex", 2),
    ("Meowth ex", 1),
    ("Fezandipiti ex", 1),
    # Trainer (26) — 17 from the primer list + flex additions (see note above)
    ("Surfing Beach", 3),
    ("Lillie's Determination", 4),
    ("Poké Pad", 4),
    ("Boss's Orders", 4),          # printed 3 + 1 flex (now at 4-copy max)
    ("Hilda", 3),
    ("Buddy-Buddy Poffin", 4),     # flex addition
    ("Ultra Ball", 4),             # flex addition
    # Energy (21) — 12 from the primer list + 9 flex Basic Water Energy
    ("Basic Water Energy", 18),    # printed 9 + 9 flex
    ("Ignition Energy", 3),
]


# --------------------------------------------------------------------------- #
# Slowking (Psychic toolbox) — Ross Cawthon, 4th place, NAIC 2026.
# Slowking's Seek Inspiration copies an attack from a discarded Pokémon (v0:
# base damage only, per effects.py's documented limitation), backed by Mega
# Kangaskhan ex (Run Errand draw + Rapid-Fire Combo), Latias ex (Skyliner free
# retreat + Eon Blade), Kyurem (Trifrost), Metagross (Luster Blast), Zeraora
# (Strong Volt / Shocking Knuckle), Lillie's Clefairy ex and Fezandipiti ex for
# utility. Wondrous Patch reattaches a discarded Basic Psychic Energy; Brave
# Bangle/Lucky Helmet are Tools; Academy at Night is played for the Stadium slot
# (its once-per-turn top-deck effect is not modeled — see effects.py notes).
# --------------------------------------------------------------------------- #
DECK_SLOWKING = [
    # Pokémon (20)
    ("Slowpoke", 4),
    ("Slowking", 3),
    ("Mega Kangaskhan ex", 3),
    ("Latias ex", 2),
    ("Kyurem", 2),
    ("Metagross", 2),
    ("Meowth ex", 1),
    ("Zeraora", 1),
    ("Lillie's Clefairy ex", 1),
    ("Fezandipiti ex", 1),
    # Trainer (29)
    ("Lillie's Determination", 4),
    ("Ciphermaniac's Codebreaking", 4),
    ("Poké Pad", 4),
    ("Ultra Ball", 4),
    ("Wondrous Patch", 3),
    ("Night Stretcher", 2),
    ("Secret Box", 1),           # ACE SPEC
    ("Switch", 1),
    ("Brave Bangle", 1),         # Pokémon Tool
    ("Lucky Helmet", 1),         # Pokémon Tool
    ("Academy at Night", 4),     # Stadium
    # Energy (11)
    ("Telepathic Psychic Energy", 4),
    ("Basic Psychic Energy", 4),
    ("Boomerang Energy", 3),
]

# --------------------------------------------------------------------------- #
# Slowking / Mega Slowbro ex — a Pitch Black (legal 2026-07-31) front-run graft
# onto the Slowking shell above. Slowpoke is the shared Basic for BOTH lines,
# so this is a matchup-dependent choice (Seek Inspiration toolbox vs. a 330 HP
# tank with a KO-proof retaliation) off the same 4 copies, same Psychic energy
# base — no new energy types needed. Only real diff from DECK_SLOWKING: Kyurem
# and Metagross drop 2->1 each (pure Seek Inspiration copy-fodder redundancy)
# to fund 2 Mega Slowbro ex. Shellnado Spin (180, KO-proof 12-counter
# retaliation on the attacker next turn) is implemented and unit-tested
# (tests/test_shellnado_spin.py) but NOT yet livefire-verified in a real
# seeded game — do that before trusting a sim number here.
# --------------------------------------------------------------------------- #
DECK_SLOWKING_SLOWBRO = [
    # Pokémon (20)
    ("Slowpoke", 4),
    ("Slowking", 3),
    ("Mega Slowbro ex", 2),
    ("Mega Kangaskhan ex", 3),
    ("Latias ex", 2),
    ("Kyurem", 1),
    ("Metagross", 1),
    ("Meowth ex", 1),
    ("Zeraora", 1),
    ("Lillie's Clefairy ex", 1),
    ("Fezandipiti ex", 1),
    # Trainer (29)
    ("Lillie's Determination", 4),
    ("Ciphermaniac's Codebreaking", 4),
    ("Poké Pad", 4),
    ("Ultra Ball", 4),
    ("Wondrous Patch", 3),
    ("Night Stretcher", 2),
    ("Secret Box", 1),           # ACE SPEC
    ("Switch", 1),
    ("Brave Bangle", 1),         # Pokémon Tool
    ("Lucky Helmet", 1),         # Pokémon Tool
    ("Academy at Night", 4),     # Stadium
    # Energy (11)
    ("Telepathic Psychic Energy", 4),
    ("Basic Psychic Energy", 4),
    ("Boomerang Energy", 3),
]

# --------------------------------------------------------------------------- #
# Slowking / Annihilape — a LADDER-OBSERVED list (reconstructed from two logged
# TCG Live games vs. DECK_MEGA_EXCADRILL, 2026-08; player "Sfender07"), NOT a
# tournament finish — read its win rates with that provenance in mind. Same Seek
# Inspiration engine as DECK_SLOWKING, but the toolbox adds Annihilape (Destined
# Fight: both Actives are Knocked Out — an effect-KO that ignores HP and converts
# a 1-prize Slowking into a 3-prize Mega trade) and the list leans on the
# Academy at Night + Seek Inspiration combo explicitly seen in the logs: the
# Stadium's once-per-turn top-decks the toolbox piece, Seek Inspiration discards
# it. Smoochum's Delightful Kiss stocks Psychic Energy from the deck; Trifrost
# (110×3) sweeps 110-HP benches. Slots not visible in the logs are filled with
# the DECK_SLOWKING staple suite (Ultra Ball / Night Stretcher / Switch).
# --------------------------------------------------------------------------- #
DECK_SLOWKING_ANNIHILAPE = [
    # Pokémon (18)
    ("Slowpoke", 4),
    ("Slowking", 3),
    ("Smoochum", 2),
    ("Latias ex", 2),
    ("Meowth ex", 1),
    ("Fezandipiti ex", 1),
    ("Kyurem", 2),
    ("Metagross (CRI)", 2),        # Metallic Hammer print — the one the logs discard
    ("Annihilape", 1),
    # Trainer (25)
    ("Hilda", 4),
    ("Poké Pad", 4),
    ("Ciphermaniac's Codebreaking", 3),
    ("Ultra Ball", 4),
    ("Academy at Night", 4),       # Stadium — the Seek Inspiration top-deck feeder
    ("Boss's Orders", 2),
    ("Switch", 2),
    ("Night Stretcher", 2),
    # Energy (17)
    ("Telepathic Psychic Energy", 4),
    ("Basic Psychic Energy", 13),
]


# --------------------------------------------------------------------------- #
# Mega Excadrill / Shaymin — the anti-Slowking counter-build of
# DECK_MEGA_EXCADRILL (same Metal engine, same provenance caveat: the base list
# is faithful, this variant is a sim experiment, no tournament finish). Three
# swaps, each aimed at a documented Slowking line:
#   +2 Shaymin (DRI)      — Flower Curtain: Trifrost can no longer touch benched
#                           Metang/Beldum/Drilbur (non-Rule-Box); the published
#                           counter to the archetype.
#   +1 Gravity Mountain   — a second counter-Stadium to bump Academy at Night
#                           and break the top-deck -> Seek Inspiration loop.
#   −1 Ethan's Pichu, −1 Special Red Card, −1 Jumbo Ice Cream to fund it.
# --------------------------------------------------------------------------- #
DECK_MEGA_EXCADRILL_SHAYMIN = [
    # Pokémon (19)
    ("Beldum", 4),
    ("Metang", 4),
    ("Metagross (CRI)", 2),
    ("Drilbur", 3),
    ("Mega Excadrill ex", 2),
    ("Genesect ex", 2),
    ("Shaymin (DRI)", 2),
    # Trainer (24)
    ("Team Rocket's Petrel", 4),
    ("Boss's Orders", 3),
    ("Kieran", 2),
    ("Lillie's Determination", 2),
    ("Team Rocket's Transceiver", 4),
    ("Energy Recycler", 2),
    ("Jumbo Ice Cream", 1),
    ("Ultra Ball", 1),
    ("Buddy-Buddy Poffin", 1),
    ("Precious Trolley", 1),      # ACE SPEC
    ("Air Balloon", 1),           # Pokémon Tool
    ("Gravity Mountain", 2),      # Stadium
    # Energy (17)
    ("Basic Metal Energy", 17),
]


# --------------------------------------------------------------------------- #
# Ogerpon Box — Toshiyuki Otake, 1st place, Japan Championships 2026.
# Teal Mask Ogerpon ex (Teal Dance ability accel + Myriad Leaf Shower) leads a
# Grass/Fighting-costed toolbox: Wellspring Mask Ogerpon ex (Sob / Torrential
# Pump), Lillie's Clefairy ex, Latias ex, Meowth ex, Pecharunt, Mega Kangaskhan
# ex, Munkidori, Fezandipiti ex and Chi-Yu (Allure / Ground Melter, Stadium
# synergy) for utility/disruption. Bug Catching Set + Ultra Ball find the
# Basics; Area Zero Underdepths and Tera Orb round out the Stadium/Tool slots
# (Underdepths' 8-Bench-for-Tera effect is not modeled — see effects.py notes).
# --------------------------------------------------------------------------- #
DECK_OGERPON_BOX = [
    # Pokémon (18)
    ("Teal Mask Ogerpon ex", 4),
    ("Lillie's Clefairy ex", 2),
    ("Latias ex", 2),
    ("Meowth ex", 2),
    ("Pecharunt", 2),
    ("Mega Kangaskhan ex", 2),
    ("Munkidori", 1),
    ("Fezandipiti ex", 1),
    ("Chi-Yu", 1),
    ("Wellspring Mask Ogerpon ex", 1),
    # Trainer (27)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Ciphermaniac's Codebreaking", 1),
    ("N's Plan", 1),
    ("Energy Switch", 4),
    ("Ultra Ball", 4),
    ("Bug Catching Set", 4),
    ("Night Stretcher", 1),
    ("Unfair Stamp", 1),         # ACE SPEC
    ("Tera Orb", 1),             # Pokémon Tool
    ("Area Zero Underdepths", 3),  # Stadium
    # Energy (15)
    ("Basic Grass Energy", 11),
    ("Prism Energy", 4),
]

# --------------------------------------------------------------------------- #
# Crustle Standalone — a SIMPLIFIED-BUT-FAITHFUL-CORE version of the real
# Crustle/Cornerstone shell (Elmar Tresp's Prague Regional runner-up), built
# ONLY from already-implemented cards (checked against TRAINER_EFFECTS in
# effects.py first). Dwebble -> Crustle (Mysterious Rock Inn wall + Superb
# Scissors) alongside Cornerstone Mask Ogerpon ex (Cornerstone Stance wall +
# Demolish) and Mega Kangaskhan ex (Run Errand draw + Rapid-Fire Combo) share a
# Grass/Fighting energy base matching the real list's colors — Grass for
# Crustle's attack, Fighting for Cornerstone's, Colorless (any type) for
# Kangaskhan's. This is NOT the tournament list: it's missing its specific
# tech trainers (e.g. any not-yet-implemented ACE SPECs/Tools/Stadiums from the
# real build), which aren't implemented in this engine yet. Trainer/Energy
# fill (50 cards), chosen from the staple suite specified for this deck:
#   Lillie's Determination 4, Boss's Orders 3, Ultra Ball 4, Buddy-Buddy
#   Poffin 4, Poké Pad 4, Hilda 3, Colress's Tenacity 2, Pokégear 3.0 3,
#   Night Stretcher 2, Switch 2, Energy Switch 2  (= 33 Trainers)
#   + Basic Grass Energy 10, Basic Fighting Energy 7  (= 17 Energy)
#   33 + 17 = 50; + 10 Pokémon = 60.
# --------------------------------------------------------------------------- #
DECK_CRUSTLE_STANDALONE = [
    # Pokémon (10)
    ("Dwebble", 4),
    ("Crustle", 3),
    ("Mega Kangaskhan ex", 2),
    ("Cornerstone Mask Ogerpon ex", 1),
    # Trainer (33)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Ultra Ball", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Poké Pad", 4),
    ("Hilda", 3),
    ("Colress's Tenacity", 2),
    ("Pokégear 3.0", 3),
    ("Night Stretcher", 2),
    ("Switch", 2),
    ("Energy Switch", 2),
    # Energy (17)
    ("Basic Grass Energy", 10),
    ("Basic Fighting Energy", 7),
]


# --------------------------------------------------------------------------- #
# Crustle (modernized) — Dwebble/Crustle/Kangaskhan/Cornerstone Ogerpon shell.
# Hero's Cape, Mist Energy, Spiky Energy, Crushing Hammer as the non-ex-chip
# package. Milotic ex used to sit in the 11th Pokémon slot as a Tera wall
# (Sparkling Scales) but the 60 had no Feebas and no Rare Candy, so it could
# never enter play. Replaced with a 4th Crustle (2026-08-24). The Aug 17
# mcts2 matrix was measured on the old 3 Crustle + 1 Milotic list; treat those
# cells as the brick-in version.
# --------------------------------------------------------------------------- #
DECK_CRUSTLE_MODERN = [
    # Pokémon (11)
    ("Dwebble", 4),
    ("Crustle", 4),
    ("Mega Kangaskhan ex", 2),
    ("Cornerstone Mask Ogerpon ex", 1),
    # Trainer (33)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Ultra Ball", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Poké Pad", 4),
    ("Hilda", 3),
    ("Pokégear 3.0", 3),
    ("Night Stretcher", 2),
    ("Switch", 1),
    ("Energy Switch", 2),
    ("Hero's Cape", 1),          # ACE SPEC
    ("Crushing Hammer", 2),
    # Energy (16)
    ("Basic Grass Energy", 5),
    ("Basic Fighting Energy", 4),
    ("Mist Energy", 4),
    ("Spiky Energy", 3),
]


# --------------------------------------------------------------------------- #
# Mega Excadrill ex (Pitch Black-era Metal) — matches the REAL 2nd/416 "Tournament
# of Doom" tournament list exactly, including print (Ap3XxX9941's decklist on
# Limitless). Drilbur -> Mega Excadrill ex (340 HP, 3-prize Mega; Undermine mills
# 2, Maximum Drilling hits 200 / 330 once it has 2 Energy past its [M][M][M]
# cost) is the payoff; Drilbur itself is the real PBL 46 print (Call for Family
# benches up to 2 Basics, Dig Claws a plain 50 — NOT the ability-bearing
# "Drilbur (TEF)" this engine also carries for other builds; that print isn't
# what the tournament list ran). Beldum -> Metang -> "Metagross (CRI)" is the
# Energy engine and secondary attacker: Metang's Metal Maker digs the top 4 for
# Basic Metal Energy and attaches them, then Metagross (the real CRI 61 print,
# NOT the plain "Metagross" used elsewhere in this engine's other decks) either
# repositions with M Bounce Back (60 + force the opponent to switch out) or
# closes with Metallic Hammer (150, optionally discard 3 Metal Energy for +150
# = 300) — a real synergy with the list's own 2x Energy Recycler, which
# recurs exactly what Metallic Hammer just discarded. Genesect ex is the
# consistency Basic (Metallic Signal fetches 2 Evolution Metal Pokémon; Protect
# Charge hits 150 and takes 30 less next turn), Ethan's Pichu is a free-attack
# opener that draws.
#
# Trainers: Team Rocket's Petrel (any Trainer) + 4 Team Rocket's Transceiver
# (fetches Petrel) is the search spine, Boss's Orders/Kieran the gust/+30 push,
# Lillie's Determination the reset draw, Energy Recycler + Jumbo Ice Cream the
# recovery/heal, and Precious Trolley (the single ACE SPEC) the one-card Bench
# explosion. Air Balloon offsets Mega Excadrill ex's retreat 4; Gravity Mountain
# is a −30 HP Stadium that hurts opposing Stage 2s (nothing in THIS list is a
# Stage 2 except Metagross — a real, deliberate cost of the card).
# --------------------------------------------------------------------------- #
DECK_MEGA_EXCADRILL = [
    # Pokémon (18)
    ("Beldum", 4),
    ("Metang", 4),
    ("Metagross (CRI)", 2),
    ("Drilbur", 3),
    ("Mega Excadrill ex", 2),
    ("Genesect ex", 2),
    ("Ethan's Pichu", 1),
    # Trainer (25)
    ("Team Rocket's Petrel", 4),
    ("Boss's Orders", 3),
    ("Kieran", 2),
    ("Lillie's Determination", 2),
    ("Team Rocket's Transceiver", 4),
    ("Energy Recycler", 2),
    ("Jumbo Ice Cream", 2),
    ("Ultra Ball", 1),
    ("Special Red Card", 1),
    ("Buddy-Buddy Poffin", 1),
    ("Precious Trolley", 1),      # ACE SPEC
    ("Air Balloon", 1),           # Pokémon Tool
    ("Gravity Mountain", 1),      # Stadium
    # Energy (17)
    ("Basic Metal Energy", 17),
]


DECK_CYNTHIA_GARCHOMP = [
    # The real 1st-of-374 list (angeellg098, Tournament of Doom, via Limitless). A
    # Cynthia's-name-matters deck: Cynthia's Gabite's Champion's Call finds any piece,
    # Cynthia's Roserade's Cheer On to Glory adds +30 to every Cynthia's attack, and
    # Cynthia's Garchomp ex's Draconic Buster hits 260 (+30/+30 boosts) for [F][F].
    # Pokémon (20)
    ("Cynthia's Roselia", 4),
    ("Cynthia's Roserade", 4),
    ("Cynthia's Gible", 4),
    ("Cynthia's Gabite", 4),
    ("Cynthia's Garchomp ex", 3),
    ("Cynthia's Spiritomb", 1),
    # Trainer (32)
    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Hilda", 2),
    ("Kieran", 1),
    ("Judge", 1),
    ("Surfer", 1),
    ("Buddy-Buddy Poffin", 4),
    ("Poké Pad", 4),
    ("Fighting Gong", 3),
    ("Night Stretcher", 2),
    ("Premium Power Pro", 2),
    ("Cynthia's Power Weight", 3),      # Pokémon Tool
    ("Team Rocket's Watchtower", 2),    # Stadium
    # Energy (8)
    ("Basic Fighting Energy", 4),
    ("Rocky Fighting Energy", 3),
    ("Neo Upper Energy", 1),            # ACE SPEC
]


# --------------------------------------------------------------------------- #
# "Hide 'n' Sneak" — Joseph Anderson's build, the community-rated strongest Pitch
# Black-era Ghost list. The whole deck is a discard-pile engine: Shuppet (PBL),
# Banette (PBL), Poltchageist (PBL) and Sinistcha (PBL) all carry the Hide 'n'
# Sneak Ability ("Prevent all effects of your opponent's Pokémon's attacks and
# Abilities done to this Pokémon"), and the two payoffs COUNT them in the discard:
# Dhelmise (PBL)'s Vengeful Anchor is 30 for [P] but 170 at 4+, and Sinistcha
# (PBL)'s Matcha Spin drops 4 counters on EVERY opposing Pokémon at 6+. So Gwynn,
# Ultra Ball and Prism Tower aren't just draw — throwing your own Pokémon away IS
# the combo. Dunsparce (JTG) / Dudunsparce is the draw engine (Trading Places
# pivots the opener out for free), Lillie's Clefairy ex the scaling attacker,
# Patrat (CRI) a Watchful Eye counter-move lock (blank Munkidori's Adrena-Brain),
# Flutter Mane the Ability lock, and Bloodmoon Ursaluna ex the late-game closer.
#
# PRINT COLLISIONS — every Pokémon below with a "(SET)" suffix is a DIFFERENT card
# from the same-named entry the pool already had, so both are kept and the deck
# names the print it actually plays (Metagross (CRI) / Drilbur (TEF) precedent):
#   Shuppet (PBL) 50HP + Hide 'n' Sneak vs pool "Shuppet" (JTG, 60HP, Spooky Shot);
#   Banette (PBL) 80HP + Puppet Pull vs pool "Banette" (JTG, 90HP, Cursed Words);
#   Dhelmise (PBL) Psychic 140HP vs pool "Dhelmise" (TEF, GRASS, 130HP, Steel Anchor);
#   Poltchageist (PBL) Hide 'n' Sneak vs pool "Poltchageist" (TWM, bench-only
#     "Storehouse Hideaway" + Hook);
#   Sinistcha (PBL) Matcha Spin vs pool "Sinistcha" (TWM, no Ability, Cursed Drop);
#   Patrat (CRI) Watchful Eye vs pool "Patrat" (White Flare, no Ability, Procurement);
#   Dunsparce (JTG) Trading Places vs pool "Dunsparce" (TEF, Gnaw/Dig) — the TEF
#     print is left untouched under the bare name because charizard_xy and
#     alakazam_deck both play it.
# Flutter Mane, Dudunsparce, Prism Tower and Legacy Energy matched the pool exactly
# and are used as-is.
# --------------------------------------------------------------------------- #
DECK_HIDE_N_SNEAK = [
    # Pokémon (24)
    ("Shuppet (PBL)", 4),
    ("Banette (PBL)", 3),
    ("Dhelmise (PBL)", 4),
    ("Dunsparce (JTG)", 3),
    ("Dudunsparce", 2),
    ("Poltchageist (PBL)", 2),
    ("Sinistcha (PBL)", 1),
    ("Lillie's Clefairy ex", 2),
    ("Patrat (CRI)", 1),
    ("Flutter Mane", 1),
    ("Bloodmoon Ursaluna ex", 1),
    # Trainer (29)
    ("Lillie's Determination", 4),
    ("Gwynn", 3),
    ("Boss's Orders", 3),
    ("Kieran", 1),
    ("Poké Pad", 4),
    ("Ultra Ball", 4),
    ("Buddy-Buddy Poffin", 2),
    ("Night Stretcher", 2),
    ("Pokégear 3.0", 2),
    ("Air Balloon", 1),           # Pokémon Tool
    ("Prism Tower", 3),           # Stadium
    # Energy (7)
    ("Telepathic Psychic Energy", 4),
    ("Basic Psychic Energy", 2),
    ("Legacy Energy", 1),         # ACE SPEC
]


# --------------------------------------------------------------------------- #
# TOUCANNON — Felipe Canales' 11-1 list (Tournament of Doom, via Limitless).
#
# The plan: a Stage 2 Colorless beatdown that scales off BOARD WIDTH. Feather Rondo is
# "[C] 60+, 20 more for each Benched Pokémon (both yours and your opponent's)" — one
# Energy, and every extra body on either side is +20. Area Zero Underdepths raises YOUR
# Bench cap to 8 whenever you have a Tera Pokémon in play (the Ogerpon ex pair, Latias
# ex is not Tera — the Ogerpons and Lillie's Clefairy ex are the enablers to check), so
# the deck deliberately over-benches to push Feather Rondo past 200. Hoothoot/Noctowl
# is the Trainer engine: Jewel Seeker fires on EVOLVE and only with a Tera Pokémon in
# play, which is the second reason the Tera count matters. Iron Leaves ex is the
# surprise-attacker plan B (Rapid Vernier benches it, switches it in and pulls Energy
# across for an immediate 180 Prism Edge).
#
# PRINT COLLISION: "Hoothoot (SCR)" is the Stellar Crown 114 print (Triple Stab). The
# pool's bare "Hoothoot" is sv5-126 (Temporal Forces, Silent Wing), a DIFFERENT card
# that DECK_RAGING_BOLT and DECK_WATER play — both entries are correct, and this list
# must name the suffixed one. Pikipek / Trumbeak / Toucannon are brand new to the pool
# (me5 66/67/68) so they keep their bare names, and Noctowl / Iron Leaves ex are NOT
# collisions (the pool's Promo prints carry text identical to SCR 115 / TEF 25).
# --------------------------------------------------------------------------- #
DECK_TOUCANNON = [
    # Pokémon (23)
    ("Pikipek", 3),
    ("Trumbeak", 2),
    ("Toucannon", 3),
    ("Hoothoot (SCR)", 3),        # SCR 114 print — NOT the pool's bare TEF Hoothoot
    ("Noctowl", 3),
    ("Teal Mask Ogerpon ex", 2),  # Tera — turns on Area Zero's 8-Bench + Jewel Seeker
    ("Fezandipiti ex", 1),
    ("Fan Rotom", 1),
    ("Wellspring Mask Ogerpon ex", 1),   # Tera
    ("Lillie's Clefairy ex", 1),
    ("Latias ex", 1),
    ("Iron Leaves ex", 1),
    ("Meowth ex", 1),
    ("Moltres", 1),
    # Trainer (28)
    ("Boss's Orders", 3),
    ("Lillie's Determination", 3),
    ("Crispin", 2),
    ("Judge", 1),
    ("Kieran", 1),
    ("Hilda", 1),
    ("Ultra Ball", 4),
    ("Poké Pad", 3),
    ("Night Stretcher", 2),
    ("Buddy-Buddy Poffin", 2),
    ("Rare Candy", 1),
    ("Energy Switch", 1),
    ("Area Zero Underdepths", 3),        # Stadium
    # Energy (9)
    ("Basic Grass Energy", 5),
    ("Basic Water Energy", 1),
    ("Legacy Energy", 1),                # ACE SPEC
    ("Basic Fire Energy", 1),
    ("Basic Psychic Energy", 1),
]


# --------------------------------------------------------------------------- #
# MEGA GARDEVOIR (REAL LIST) — Anar Guliyev, Regional Utrecht.
#
# PROVENANCE, honestly: this is a WEAK source — a 310th-place finish, and the only
# real tournament list found for the archetype. It is registered as `gardevoir_real`
# NEXT TO, not instead of, the engine's built `gardevoir` archetype, which stays the
# strong tuned baseline. Read its win rates as "what this specific list does", not as
# "what Mega Gardevoir is worth".
#
# The plan: Ralts -> Kirlia -> Mega Gardevoir ex (Rare Candy / Grand Tree skipping the
# Stage 1), with Overflowing Wishes accelerating a Basic Psychic Energy onto every
# Benched Pokémon and Mega Symphonia scaling off the Psychic Energy that lands there.
# Around it sit three secondary attackers with completely different clocks: Mega Diancie
# ex (Garland Ray's 120× energy-discard burst, protected by Diamond Coat's flat −30),
# Azumarill ex (Bubble Gathering hoovers every loose Energy off the board onto itself,
# then Energized Balloon pays 60 + 40 per Psychic Energy attached), and Zacian, a
# one-card 140 finisher the moment the opponent is down to 3 Prizes.
#
# NO PRINT COLLISIONS in this list — every entry is the pool's existing card:
#   Marill (sv5-64) IS the TEF 64 print with Ball Roll (the ASC 83 "Hide/Flop" print in
#     the brief is a DIFFERENT card; the pool's is the one this engine plays).
#   Zacian (me2-45) IS PFL 45 (Limit Break), Mega Diancie ex (me2-41) IS PFL 41
#     (Diamond Coat + Garland Ray), Flutter Mane / Dudunsparce / the Trainers all match.
# The one genuine gap was Azumarill ex (ASC 84), which is NOT in the upstream dump at
# all — added to data/manual_cards.json and merged into the pool.
# --------------------------------------------------------------------------- #
DECK_MEGA_GARDEVOIR_REAL = [
    # Pokémon (18)
    ("Ralts", 3),
    ("Kirlia", 2),
    ("Mega Gardevoir ex", 2),
    ("Munkidori", 2),
    ("Latias ex", 2),
    ("Marill", 1),
    ("Azumarill ex", 1),
    ("Fezandipiti ex", 1),
    ("Zacian", 1),
    ("Meowth ex", 1),
    ("Lillie's Clefairy ex", 1),
    ("Mega Diancie ex", 1),
    # Trainer (30)
    ("Lillie's Determination", 4),
    ("Colress's Tenacity", 4),
    ("Wally's Compassion", 3),
    ("Boss's Orders", 2),
    ("Judge", 2),
    ("Pokégear 3.0", 4),
    ("Wondrous Patch", 3),
    ("Ultra Ball", 3),
    ("Rare Candy", 2),
    ("Grand Tree", 1),           # Stadium, ACE SPEC
    ("Jamming Tower", 1),        # Stadium
    ("Mystery Garden", 1),       # Stadium
    # Energy (12)
    ("Basic Psychic Energy", 7),
    ("Telepathic Psychic Energy", 3),
    ("Prism Energy", 2),
]


# --------------------------------------------------------------------------- #
# DOUBLADE / AEGISLASH (Perfect Order Metal) — a DECK-GUIDE build.
#
# PROVENANCE, honestly: this is NOT a proven tournament list. It is a deck-guide
# recipe for the new Perfect Order Aegislash line, registered so the engine can play
# and measure it. Read its win rates as "what this specific guide build does", not as
# "what Aegislash is worth" and not as a placement-backed list — nothing here finished
# anywhere, because the line is new.
#
# THE PLAN: Doublade's Weaponized Swords ([C][C], 60× ) does 60 damage for every
# Honedge / Doublade / Aegislash you REVEAL from hand — revealed, not discarded, so the
# same cards keep paying every single turn. That is why the line is 4/4/4: the copies
# are simultaneously the evolution line AND the ammunition, and a hand holding four of
# them is a 240-damage two-Energy attack that never runs out. Aegislash is the closer
# (Metal Slash, 230, then it can't attack for a turn — so it trades one big turn for a
# quiet one), with Slash (80) as the filler attack on the off turn.
#
# THE SUPPORT: Steven's Beldum -> Steven's Metang -> Steven's Metagross ex, with 2 Rare
# Candy specifically to skip the single Steven's Metang (verified: Steven's Metang's
# printed evolvesFrom is "Steven's Beldum" and Steven's Metagross ex's is "Steven's
# Metang", so effects._evolution_chain_basic walks ex -> Metang -> Beldum and Rare Candy
# works on the line). Metagross ex's X-Boot then attaches Basic Energy straight out of
# the deck, and Genesect ex's Metallic Signal digs the Evolution Metal Pokémon out.
# The Trainer engine is the Team Rocket one: 4 Petrel (search any Trainer) + 4
# Transceiver (search a Team Rocket Supporter) + Team Rocket's Factory, whose draw-2 is
# switched on by having played a Team Rocket Supporter that turn.
#
# HONEST NOTE ON THE 5 BASIC PSYCHIC ENERGY: this list has NO Psychic Pokémon, and
# X-Boot's Basic [P] Energy half may only be attached to a [P] Pokémon (see the reading
# spelled out in effects._x_boot). So in THIS list X-Boot fetches the Metal half only,
# and the Psychic Energy is here purely as Colorless payment for Weaponized Swords
# ([C][C]) / Slash ([C][C][C]) / Metal Slash's three Colorless. That is a property of
# the guide recipe as given, recorded rather than silently "fixed".
# --------------------------------------------------------------------------- #
DECK_DOUBLADE = [
    # Pokémon (21)
    ("Honedge", 4),
    ("Doublade", 4),
    ("Aegislash", 4),
    ("Fezandipiti ex", 1),
    ("Genesect ex", 2),
    ("Steven's Beldum", 3),
    ("Steven's Metang", 1),
    ("Steven's Metagross ex", 2),
    # Trainer (29)
    ("Team Rocket's Petrel", 4),
    ("Team Rocket's Transceiver", 4),
    ("Lillie's Determination", 3),
    ("Dawn", 2),
    ("Boss's Orders", 2),
    ("Poké Pad", 2),
    ("Night Stretcher", 2),
    ("Rare Candy", 2),
    ("Air Balloon", 2),          # Pokémon Tool
    ("Buddy-Buddy Poffin", 1),
    ("Energy Recycler", 1),
    ("Sacred Ash", 1),
    ("Brave Bangle", 1),         # Pokémon Tool
    ("Precious Trolley", 1),     # ACE SPEC
    ("Team Rocket's Factory", 1),  # Stadium
    # Energy (10)
    ("Basic Metal Energy", 5),
    ("Basic Psychic Energy", 5),
]



# --------------------------------------------------------------------------- #
# Dragapult Blaziken — Jon Webb, 6th place, NAIC 2026 New Orleans (Limitless
# list 28253). TOURNAMENT provenance. The 4th most-played archetype in the live
# PBL metagame (5.99% share, 52.79% real WR) and the build that beat the house
# mega_excadrill on ladder 2026-08-16 (docs/LADDER_LOG.md): Phantom Dive spread
# + Blaziken ex's Seething Spirit discard-Energy acceleration, with every KO
# against an all-Fire-weak Metal board doubled by Weakness.
DECK_DRAGAPULT_BLAZIKEN: list[tuple[str, int]] = [
    ("Dreepy", 4),
    ("Drakloak", 4),
    ("Dragapult ex", 2),
    ("Torchic", 2),
    ("Combusken", 1),
    ("Blaziken ex", 2),
    ("Munkidori", 2),
    ("Lillie's Clefairy ex", 1),
    ("Fezandipiti ex", 1),
    ("Meowth ex", 1),
    ("Budew", 1),
    ("Chi-Yu", 1),
    ("Shaymin (DRI)", 1),

    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Crispin", 2),
    ("Dawn", 1),
    ("Buddy-Buddy Poffin", 4),
    ("Ultra Ball", 4),
    ("Poké Pad", 3),
    ("Night Stretcher", 2),
    ("Rare Candy", 2),
    ("Special Red Card", 1),
    ("Unfair Stamp", 1),      # ACE SPEC
    ("Area Zero Underdepths", 1),
    ("Team Rocket's Watchtower", 1),

    ("Basic Fire Energy", 3),
    ("Basic Psychic Energy", 3),
    ("Basic Darkness Energy", 2),
]

# --------------------------------------------------------------------------- #
# Festival Lead — "Dreamjew", 1st place 12-0-1, online (Limitless play
# tournament 6a5a5085…). ONLINE-EVENT provenance (weaker than a Regional; the
# archetype itself is the 3rd most-played in the live meta at 6.75%). Engine:
# Dipplin's Do the Wave (20× bench) used TWICE per turn via Festival Lead +
# Festival Grounds, pumped by Gladion's Final Battle (+80 non-Rule-Box) and
# Brave Bangle (+30 vs ex) — a 1-prize attacker printing 200–400 a turn.
# Thwackey's Boom Boom Groove is the universal tutor; Rabsca walls the bench.
DECK_FESTIVAL_LEAD: list[tuple[str, int]] = [
    ("Grookey", 4),
    ("Thwackey", 4),
    ("Applin (SCR)", 3),      # print collision: vanilla SCR print, not TWM
    ("Dipplin", 3),
    ("Goldeen", 2),
    ("Seaking (PRE)", 2),     # print collision: the Festival Lead print
    ("Rellor", 1),
    ("Rabsca", 1),

    ("Lillie's Determination", 4),
    ("Gladion's Final Battle", 3),
    ("Boss's Orders", 2),
    ("Kieran", 1),
    ("Lana's Aid", 1),
    ("Buddy-Buddy Poffin", 4),
    ("Poké Pad", 4),
    ("Night Stretcher", 2),
    ("Ultra Ball", 2),
    ("Bug Catching Set", 2),
    ("Switch", 1),
    ("Secret Box", 1),        # ACE SPEC
    ("Air Balloon", 2),
    ("Brave Bangle", 2),
    ("Festival Grounds", 3),
    ("Forest of Vitality", 1),

    ("Basic Grass Energy", 5),
]

# --------------------------------------------------------------------------- #
# Grimmsnarl Froslass — Andrew Choi, 128th place, NAIC 2026 New Orleans
# (Limitless list 28345). WEAK tournament provenance (the archetype is 4.66% of
# the live meta; read win rates accordingly). Engine: Punk Up floods Basic
# Darkness onto Marnie's Pokémon the turn Grimmsnarl ex evolves (usually via
# Rare Candy), Shadow Bullet snipes 180+30, and Froslass ×2 chips every
# Ability-holder at every Pokémon Checkup while Munkidori relocates the
# self-damage. Spikemuth Gym is the archetype's own consistency Stadium.
DECK_GRIMMSNARL_FROSLASS: list[tuple[str, int]] = [
    ("Munkidori", 4),
    ("Marnie's Impidimp", 3),
    ("Marnie's Morgrem", 2),
    ("Marnie's Grimmsnarl ex", 3),
    ("Snorunt", 2),
    ("Froslass", 2),
    ("Budew", 1),
    ("Tatsugiri", 1),
    ("Yveltal", 1),

    ("Lillie's Determination", 4),
    ("Team Rocket's Petrel", 4),
    ("Boss's Orders", 3),
    ("Iris's Fighting Spirit", 1),
    ("Poké Pad", 4),
    ("Buddy-Buddy Poffin", 3),
    ("Night Stretcher", 3),
    ("Rare Candy", 2),
    ("Energy Switch", 1),
    ("Special Red Card", 1),
    ("Secret Box", 1),        # ACE SPEC
    ("Air Balloon", 1),
    ("Spikemuth Gym", 4),

    ("Basic Darkness Energy", 9),
]

# Andrew Hedrick's WORLD CHAMPIONSHIP 2026 winning list (San Francisco, Aug 28–30,
# 1st place, 14-2-0) — STRONGEST provenance in the registry: the deck that won the
# whole format. Dragapult ex control-aggro: Phantom Dive spread + Munkidori counter
# movement, a heavy disruption suite (4 Crushing Hammer, Special Red Card, Unfair
# Stamp, Budew Item-lock), Risky Ruins to tax the opponent's Basics, and Rosa's
# Encouragement as the from-behind refuel. Source: labs.limitlesstcg.com/0071
# (player 0103). Set codes in the source list are display noise; names are exact.
DECK_DRAGAPULT_WORLDS: list[tuple[str, int]] = [
    ("Dreepy", 4),
    ("Drakloak", 4),
    ("Dragapult ex", 3),
    ("Munkidori", 2),
    ("Budew", 2),
    ("Dunsparce (JTG)", 1),
    ("Dudunsparce", 1),
    ("Meowth ex", 1),
    ("Fezandipiti ex", 1),

    ("Lillie's Determination", 4),
    ("Boss's Orders", 3),
    ("Crispin", 2),
    ("Rosa's Encouragement", 1),
    ("Poké Pad", 4),
    ("Crushing Hammer", 4),
    ("Buddy-Buddy Poffin", 4),
    ("Night Stretcher", 3),
    ("Ultra Ball", 3),
    ("Unfair Stamp", 1),      # ACE SPEC
    ("Special Red Card", 1),
    ("Risky Ruins", 2),

    ("Basic Fire Energy", 3),
    ("Basic Darkness Energy", 3),
    ("Basic Psychic Energy", 3),
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
    "beedrill": DECK_BEEDRILL,
    "no_vacancy": DECK_NO_VACANCY,
    "innkeeper": DECK_INNKEEPER,
    "clefairy_stock": DECK_CLEFAIRY_STOCK,
    "clefairy_modified": DECK_CLEFAIRY_MODIFIED,
    "cornerstone_box": DECK_CORNERSTONE_BOX,
    "the_vault": DECK_THE_VAULT,
    "alakazam_deck": DECK_ALAKAZAM,
    "starmie_toolbox": DECK_STARMIE_TOOLBOX,
    "slowking": DECK_SLOWKING,
    "slowking_slowbro": DECK_SLOWKING_SLOWBRO,
    "ogerpon_box": DECK_OGERPON_BOX,
    "crustle_standalone": DECK_CRUSTLE_STANDALONE,
    "crustle_modern": DECK_CRUSTLE_MODERN,
    "mega_excadrill": DECK_MEGA_EXCADRILL,
    "cynthia_garchomp": DECK_CYNTHIA_GARCHOMP,
    "hide_n_sneak": DECK_HIDE_N_SNEAK,
    "toucannon": DECK_TOUCANNON,
    "gardevoir_real": DECK_MEGA_GARDEVOIR_REAL,
    "doublade": DECK_DOUBLADE,
    "slowking_annihilape": DECK_SLOWKING_ANNIHILAPE,
    "mega_excadrill_shaymin": DECK_MEGA_EXCADRILL_SHAYMIN,
    "dragapult_blaziken": DECK_DRAGAPULT_BLAZIKEN,
    "festival_lead": DECK_FESTIVAL_LEAD,
    "grimmsnarl_froslass": DECK_GRIMMSNARL_FROSLASS,
    "dragapult_worlds": DECK_DRAGAPULT_WORLDS,
}


def load_deck(db: CardDB, name: str) -> list[Card]:
    """Expand any registered deck by friendly name (validates the 60-card rule)."""
    if name not in DECKS:
        raise KeyError(f"unknown deck {name!r}; choose from: {', '.join(sorted(DECKS))}")
    return _expand(db, DECKS[name])
