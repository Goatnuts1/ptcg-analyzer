#!/usr/bin/env python3
"""
gap_check.py — heuristic triage for "does this deck's card text actually have
code behind it?"

This is NOT proof of correctness — a flagged item may already be covered by a
generic engine fallback (e.g. plain fixed damage needs no entry), and an
unflagged item could still have a subtly wrong implementation (that's what
tests/test_effects.py is for). It's a conservative first pass so a pasted
decklist doesn't get simulated with silently-inert cards, matching the
deck-playbook pipeline's step 2 ("gap-check card implementation").

What each supertype is checked against — these have to match where the engine
ACTUALLY implements each kind of card, or the gate both cries wolf and goes blind:

  Pokémon      — an ability/attack is flagged if it has non-empty effect text but
                 no ABILITY_EFFECTS / PASSIVE_ABILITIES / ATTACK_EFFECTS handler.
  Trainer      — flagged unless it has a TRAINER_EFFECTS entry OR (being a Stadium
                 or a Pokémon Tool) it is listed in STADIUM_IMPLEMENTED /
                 TOOL_IMPLEMENTED. Purely PASSIVE Stadiums and Tools are
                 deliberately implemented at engine chokepoints and never appear in
                 TRAINER_EFFECTS — Team Rocket's Watchtower (ability suppression),
                 Battle Cage, Gravity Mountain, Cynthia's Power Weight (+70 HP),
                 Brave Bangle, Lucky Helmet. Checking TRAINER_EFFECTS alone
                 false-flagged every one of them.
  Basic Energy — never flagged.
  Special Energy — flagged unless it is in SPECIAL_ENERGY_IMPLEMENTED or its only
                 rule is a plain "it provides <Type> Energy" line that the pool's
                 `types` field already encodes (so provided_types() handles it with
                 no code). Skipping Special Energy wholesale was a blind spot: a
                 card whose text is a real rider or a conditional provision clause
                 (Neo Upper Energy's "if attached to a Stage 2... provides every
                 type of Energy but provides only 2 Energy at a time") sat in a deck
                 doing nothing and this gate reported the deck clean.
"""

from __future__ import annotations

import re

from src.engine import effects as fx

# Reminder/boilerplate rules that are not card behavior.
_BOILERPLATE = (
    re.compile(r"^You may play any number of Item cards during your turn\.$"),
    re.compile(r"^You may play only 1 Supporter card during your turn\.$"),
    re.compile(r"^You can't have more than 1 ACE SPEC card in your deck\.$"),
    re.compile(r"^ACE SPEC:"),
    re.compile(r"^You may attach any number of Pok.mon Tools"),
    re.compile(r"^You may play only 1 Stadium card during your turn\."),
)

# "As long as this card is attached to a Pokémon, it provides <Type> Energy." — the
# whole behavior of a plain Special Energy, already carried by the pool's `types`.
_PLAIN_PROVISION = re.compile(
    r"^As long as this card is attached to a Pok.mon, "
    r"it provides \w+ Energy\.$"
)


def _behavior_rules(card) -> list[str]:
    """The card's rules text with reminder boilerplate stripped."""
    out = []
    for r in card.rules or ():
        r = " ".join(r.split())          # collapse the pool's stray \n / double spaces
        if any(p.match(r) for p in _BOILERPLATE):
            continue
        out.append(r)
    return out


def _special_energy_is_plain(card) -> bool:
    """True when the card's only behavior is providing its printed type — which
    InPlayPokemon.provided_types() already does off the pool's `types` field, so no
    handler is needed and flagging it would be a false positive."""
    rules = _behavior_rules(card)
    return bool(card.types) and len(rules) == 1 and bool(_PLAIN_PROVISION.match(rules[0]))


def check_deck_implementation(recipe: list[tuple[str, int]], db) -> list[dict]:
    """`recipe` is [(card_name, qty), ...]. Returns a list of flagged gaps, each
    {"card", "qty", "kind": "attack"|"ability"|"trainer"|"energy", "name", "text"}."""
    flagged: list[dict] = []
    seen_cards = set()

    for name, qty in recipe:
        if name not in db or name in seen_cards:
            continue
        seen_cards.add(name)
        card = db.get(name)

        if card.is_trainer:
            handled = (name in fx.TRAINER_EFFECTS
                       or ("Stadium" in card.subtypes and name in fx.STADIUM_IMPLEMENTED)
                       or ("Pokémon Tool" in card.subtypes and name in fx.TOOL_IMPLEMENTED))
            if not handled:
                flagged.append({
                    "card": name, "qty": qty, "kind": "trainer", "name": name,
                    "text": "(no TRAINER_EFFECTS / STADIUM_IMPLEMENTED / "
                            "TOOL_IMPLEMENTED entry)",
                })
            continue

        if card.is_energy:
            if card.is_basic_energy:
                continue
            if (name not in fx.SPECIAL_ENERGY_IMPLEMENTED
                    and not _special_energy_is_plain(card)):
                flagged.append({
                    "card": name, "qty": qty, "kind": "energy", "name": name,
                    "text": " | ".join(_behavior_rules(card))
                            or "(no SPECIAL_ENERGY_IMPLEMENTED entry)",
                })
            continue

        if not card.is_pokemon:
            continue

        for ab in card.abilities:
            key = (name, ab.name)
            if key not in fx.ABILITY_EFFECTS and key not in fx.PASSIVE_ABILITIES:
                flagged.append({
                    "card": name, "qty": qty, "kind": "ability",
                    "name": ab.name, "text": ab.text,
                })

        for atk in card.attacks:
            key = (name, atk.name)
            if atk.text and key not in fx.ATTACK_EFFECTS:
                flagged.append({
                    "card": name, "qty": qty, "kind": "attack",
                    "name": atk.name, "text": atk.text,
                })

    return flagged
