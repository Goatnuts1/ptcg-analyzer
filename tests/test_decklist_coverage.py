#!/usr/bin/env python3
"""
test_decklist_coverage.py — the validation-milestone coverage SNAPSHOT.

This is the executable form of docs/CARD_GAP_REPORT.md. It classifies every card
in both registered tournament lists and asserts the live state matches a recorded
manifest. It is GREEN when the code matches the documented gap, and RED only when
reality DRIFTS — which is always a real signal:

  - a regression: a card that was `implemented` silently falls back to vanilla
    (it reappears in needs-effect) — anti-flattery guard;
  - unrecorded progress: you implemented an effect but didn't update the manifest
    (it leaves needs-effect) — reminds you to record it + its test;
  - implemented-without-a-test: a card is in a registry but has no named test
    that mentions it — `implemented` may NEVER mean "in the registry but untested".

So "all tests green = trustworthy" stays a clean signal: there is no red-by-design
test here. When an effect lands, move its card from EXPECTED_NEEDS_EFFECT into
IMPLEMENTED_BY (with the test that covers it). When EXPECTED_NEEDS_EFFECT is empty,
both lists are fully faithful.

Run from project root:  python3 tests/test_decklist_coverage.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import TOURNAMENT_LISTS, load_tournament_deck
from src.engine.effects import (ATTACK_EFFECTS, ABILITY_EFFECTS, TRAINER_EFFECTS,
                                 STADIUM_IMPLEMENTED, TOOL_IMPLEMENTED,
                                 PASSIVE_ABILITIES, SPECIAL_ENERGY_IMPLEMENTED)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Generic reminder text on Trainers/Energy that is NOT a card effect.
_GENERIC = {
    "You may play any number of Item cards during your turn.",
    "You may play only 1 Supporter card during your turn.",
}

# Registry-implemented cards still blocked by a missing engine subsystem render as
# implemented* and count as NOT done. Empty now (Tera + MEGA both modeled).
INFRA_CAVEATS: dict[str, str] = {}

# --------------------------------------------------------------------------- #
# THE RECORDED GAP. Update these two together as effects land. The test asserts
# the LIVE classification matches them exactly.
# --------------------------------------------------------------------------- #

# Distinct cards (across both decks) that still need an effect. len() = burndown.
EXPECTED_NEEDS_EFFECT = frozenset({
    "Crushing Hammer",
    "Dunsparce", "Duskull",
    "Fan Rotom",
    "Meowth ex", "Moltres",
    "Oricorio ex",
    "Team Rocket's Watchtower", "Unfair Stamp",
    # §2.1 draw/search engine, §2.7 KO/damage engine, §2.6 Special Conditions all
    # landed -> see IMPLEMENTED_BY. §2.6 completed Dusknoir (Shadow Bind), Munkidori
    # (Mind Bend), Budew (Itchy Pollen).
})

# A card may only be counted `implemented` if it is listed here WITH the test
# file(s) that cover it AND whose name appears in at least one of them. This is
# the teeth behind "every effect ships with a test" — the snapshot refuses to
# call a registry-only-but-untested card done.
IMPLEMENTED_BY = {
    "Dragapult ex":        ["tests/test_effects.py", "tests/test_stadium.py"],  # Phantom Dive + Tera
    "Drakloak":            ["tests/test_effects.py"],                           # Recon Directive
    "Rare Candy":          ["tests/test_effects.py", "tests/test_mega.py"],
    "Buddy-Buddy Poffin":  ["tests/test_effects.py"],
    "Boss's Orders":       ["tests/test_effects.py"],
    "Mega Charizard X ex": ["tests/test_effects.py", "tests/test_mega.py"],     # Inferno X + 3-prize/no-turn-end
    "Battle Cage":         ["tests/test_stadium.py"],                           # passive via chokepoint
    # §2.1 draw/search engine
    "Poké Pad":            ["tests/test_search.py"],
    "Ultra Ball":          ["tests/test_search.py"],
    "Hilda":               ["tests/test_search.py"],
    "Dawn":                ["tests/test_search.py"],
    "Night Stretcher":     ["tests/test_search.py"],
    "Energy Retrieval":    ["tests/test_search.py"],
    "Switch":              ["tests/test_search.py"],
    "Lillie's Determination": ["tests/test_search.py"],
    "Judge":               ["tests/test_search.py"],
    "Crispin":             ["tests/test_search.py"],
    "Dudunsparce":         ["tests/test_search.py"],   # Run Away Draw
    # §2.7 KO/damage engine
    "Dusclops":            ["tests/test_ko_engine.py"],   # Cursed Blast (+ vanilla attack)
    "Fezandipiti ex":      ["tests/test_ko_engine.py"],   # Flip the Script + Cruel Arrow
    "Mega Charizard Y ex": ["tests/test_ko_engine.py"],   # Explosion Y
    # §2.6 Special Conditions completed these (ability/KO in test_ko_engine, rider in test_conditions)
    "Munkidori":           ["tests/test_ko_engine.py", "tests/test_conditions.py"],  # Adrena-Brain + Mind Bend
    "Dusknoir":            ["tests/test_ko_engine.py", "tests/test_conditions.py"],  # Cursed Blast + Shadow Bind
    "Budew":               ["tests/test_conditions.py"],                            # Itchy Pollen
    # §2.8 Tools + §2.10 Special Energy + passive Agile
    "Air Balloon":         ["tests/test_tools.py"],
    "Powerglass":          ["tests/test_tools.py"],
    "Charmander":          ["tests/test_tools.py"],   # Agile (passive retreat)
    "Enriching Energy":    ["tests/test_tools.py"],
}


def _effect_text(card) -> str:
    if card.is_energy:
        return " | ".join(r for r in card.rules if r not in _GENERIC) or "(special energy)"
    if card.is_trainer:
        return " | ".join(r for r in card.rules if r not in _GENERIC) or "(no text)"
    bits = []
    for ab in card.abilities:
        bits.append(f"[Ability] {ab.name}: {ab.text}")
    for a in card.attacks:
        if a.text.strip() or a.damage_suffix in ("×", "+"):
            bits.append(f"[{a.name}] {a.text or ('variable damage ' + a.damage_suffix)}".strip())
    return " | ".join(bits)


def classify(card) -> tuple[str, str]:
    """(status, note). status in {vanilla-ok, implemented, implemented*, needs-effect}."""
    if card.is_basic_energy:
        return "vanilla-ok", ""
    if card.is_energy:
        if card.name in SPECIAL_ENERGY_IMPLEMENTED:
            return "implemented", ""
        return "needs-effect", _effect_text(card)
    if card.is_trainer:
        if (card.name in TRAINER_EFFECTS or card.name in STADIUM_IMPLEMENTED
                or card.name in TOOL_IMPLEMENTED):
            return "implemented", ""
        return "needs-effect", _effect_text(card)
    if card.is_pokemon:
        meaningful_abilities = list(card.abilities)
        meaningful_attacks = [a for a in card.attacks
                              if a.text.strip() or a.damage_suffix in ("×", "+")]
        if not meaningful_abilities and not meaningful_attacks:
            return "vanilla-ok", ""
        unimpl = []
        for ab in meaningful_abilities:
            if ((card.name, ab.name) not in ABILITY_EFFECTS
                    and (card.name, ab.name) not in PASSIVE_ABILITIES):
                unimpl.append(f"[Ability] {ab.name}")
        for a in meaningful_attacks:
            if (card.name, a.name) not in ATTACK_EFFECTS:
                unimpl.append(f"[{a.name}]")
        if unimpl:
            return "needs-effect", " ".join(unimpl)
        if card.name in INFRA_CAVEATS:
            return "implemented*", INFRA_CAVEATS[card.name]
        return "implemented", ""
    return "needs-effect", f"(unhandled supertype {card.supertype})"


def main():
    db = CardDB.from_pool("data/standard_pool.json")
    fails = []

    actual_needs, actual_impl, actual_vanilla = set(), set(), set()
    for deck_name, recipe in TOURNAMENT_LISTS.items():
        cards = load_tournament_deck(db, deck_name)   # Test A: loads + totals 60
        if len(cards) != 60:
            fails.append(f"{deck_name}: {len(cards)} cards, expected 60")
        for name, _count in recipe:
            status, _ = classify(db.get(name))
            if status in ("needs-effect", "implemented*"):
                actual_needs.add(name)
            elif status == "implemented":
                actual_impl.add(name)
            else:
                actual_vanilla.add(name)

    # --- Snapshot: needs-effect set must match the recorded gap exactly. ---
    new_gaps = actual_needs - EXPECTED_NEEDS_EFFECT          # regressions / newly-found
    recorded_done = EXPECTED_NEEDS_EFFECT - actual_needs     # progress to record
    if new_gaps:
        fails.append("cards became needs-effect but aren't in EXPECTED_NEEDS_EFFECT "
                     f"(regression or new gap): {sorted(new_gaps)}")
    if recorded_done:
        fails.append("cards left needs-effect — record them: move into IMPLEMENTED_BY "
                     f"and drop from EXPECTED_NEEDS_EFFECT: {sorted(recorded_done)}")

    # --- Teeth: no card is `implemented` without a named test that mentions it. ---
    for name in sorted(actual_impl):
        refs = IMPLEMENTED_BY.get(name)
        if not refs:
            fails.append(f"{name!r} classified implemented but has no IMPLEMENTED_BY test entry")
            continue
        covered = False
        for rel in refs:
            path = os.path.join(_REPO, rel)
            if not os.path.exists(path):
                fails.append(f"{name!r}: test file {rel} is missing")
                continue
            with open(path, encoding="utf-8") as f:
                if name in f.read():
                    covered = True
        if not covered:
            fails.append(f"{name!r}: none of its test files {refs} mention it")
    # stale manifest entries (listed implemented but not actually implemented)
    stale = set(IMPLEMENTED_BY) - actual_impl
    if stale:
        fails.append(f"IMPLEMENTED_BY has stale entries (no longer implemented): {sorted(stale)}")

    # --- Report ---
    total_nonvanilla = len(actual_needs) + len(actual_impl)
    print(f"Coverage snapshot (both tournament lists):")
    print(f"  implemented+tested : {len(actual_impl)}  {sorted(actual_impl)}")
    print(f"  needs-effect       : {len(actual_needs)} of {total_nonvanilla} non-vanilla "
          f"distinct cards still to build")
    print(f"  vanilla-ok         : {len(actual_vanilla)} (no code needed)")

    if fails:
        print(f"\nFAIL ({len(fails)} drift issue(s)) — the code no longer matches the "
              f"recorded gap:")
        for f in fails:
            print("  -", f)
        return 1
    remaining = len(EXPECTED_NEEDS_EFFECT)
    if remaining:
        print(f"\nOK — matches the recorded gap. {remaining} card-effects remain to reach "
              f"full faithfulness (milestone in progress, not yet complete).")
    else:
        print("\nOK — both tournament lists fully faithful. Milestone complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
