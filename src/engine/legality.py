#!/usr/bin/env python3
"""
legality.py — the format / rotation framework. ONE source of truth for "what is
currently legal," so a future rotation is a one-line change here.

WHY THIS EXISTS: Standard legality is defined by a Pokémon card's regulation mark
(the tiny letter in the corner). Each year the oldest mark(s) rotate out. Before
this module that set lived only inside the data-fetch script, the manual-card
supplement bypassed it, and nothing validated a *deck* at runtime. Now:

  - `STANDARD_LEGAL_MARKS` is the single source of truth (imported by the fetcher
    AND used at runtime). ROTATION = edit this set, re-fetch the pool, re-run tests.
  - `validate_deck()` checks a 60-card list against the format: legal marks,
    the 4-copy rule, the 1-ACE-SPEC rule, and deck size. After a rotation it tells
    you EXACTLY which cards became illegal instead of failing silently.

This module has no engine imports on purpose (so the fetch script can import the
mark set cheaply). It duck-types cards: anything with `.is_basic_energy`,
`.regulation_mark`, and `.subtypes` works.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# THE FORMAT. Rotation lives here and nowhere else.
# --------------------------------------------------------------------------- #
# Standard 2026 season: marks H, I, J are legal; G and older have rotated out.
# To rotate (e.g. when H rotates out): change this to frozenset({"I", "J", "K"}),
# re-run `python3 src/fetch_standard_pool.py`, then run the tests — any registered
# deck that now contains an illegal card will fail loudly in test_legality.py.
STANDARD_LEGAL_MARKS = frozenset({"H", "I", "J"})

DECK_SIZE = 60
MAX_COPIES = 4          # of any single card by name — EXCEPT Basic Energy (unlimited)


def is_mark_legal(card, legal_marks=STANDARD_LEGAL_MARKS) -> bool:
    """Is this card legal in the given format? Basic Energy carries no regulation
    mark and is always legal; everything else must carry a currently-legal mark."""
    if getattr(card, "is_basic_energy", False):
        return True
    return card.regulation_mark in legal_marks


def validate_deck(db, recipe, legal_marks=STANDARD_LEGAL_MARKS) -> list[str]:
    """Return a list of legality violations for a deck `recipe` (list of
    (card_name, count)). An empty list means the deck is legal in `legal_marks`.

    Checks: every card exists in the pool, ≤4 copies of any non-Basic-Energy card,
    every card's regulation mark is legal (THE rotation check), ≤1 ACE SPEC card,
    and exactly 60 cards total.
    """
    violations: list[str] = []
    total = 0
    ace_specs = 0
    for name, count in recipe:
        total += count
        if name not in db:
            violations.append(f"{name!r}: not in the card pool")
            continue
        card = db.get(name)
        if not card.is_basic_energy and count > MAX_COPIES:
            violations.append(f"{name!r}: {count} copies (max {MAX_COPIES})")
        if not is_mark_legal(card, legal_marks):
            violations.append(
                f"{name!r}: regulation mark {card.regulation_mark!r} is not legal "
                f"(legal marks: {sorted(legal_marks)})")
        if "ACE SPEC" in card.subtypes:
            ace_specs += count
    if total != DECK_SIZE:
        violations.append(f"deck has {total} cards, expected {DECK_SIZE}")
    if ace_specs > 1:
        violations.append(f"{ace_specs} ACE SPEC cards (max 1 per deck)")
    return violations


def is_deck_legal(db, recipe, legal_marks=STANDARD_LEGAL_MARKS) -> bool:
    return not validate_deck(db, recipe, legal_marks)
