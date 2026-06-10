#!/usr/bin/env python3
"""
tcglive.py — import a Pokémon TCG Live deck export into the engine's recipe format.

TCG Live's "Copy Deck List" / export produces plain text like:

    Pokémon: 9
    3 Mega Gardevoir ex MEG 50
    4 Ralts SVI 84
    2 Kirlia SVI 85

    Trainer: 30
    4 Iono PAL 185
    3 Boss's Orders PAL 172

    Energy: 12
    8 Psychic Energy SVE 5
    4 Basic Fire Energy

    Total Cards: 60

This module turns that into `[(card_name, qty), ...]` matched against the live
`CardDB`, and reports what matched / what's missing. It is deliberately robust:

  - section headers ("Pokémon: 9", "Trainer:", "Energy:", "Total Cards: 60") are skipped
  - a trailing set code + collector number ("MEG 50", "PAL 172", "PR-SV 44") is stripped
  - bare lines without a set code ("4 Gardevoir ex") work too
  - quantity may be "4 ", "4x ", or "x4 "
  - energy is normalised ("Psychic Energy" / "Basic Psychic Energy" -> "Basic Psychic Energy")
  - matching is case- AND accent-insensitive ("poke ball" -> "Poké Ball")
  - blank lines, "# comments", and unparseable lines are skipped (and reported as warnings)

Nothing here touches the game engine beyond reading card names, so it has no effect
on determinism or play.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field

BASIC_ENERGY_TYPES = ("Grass", "Fire", "Water", "Lightning",
                      "Psychic", "Fighting", "Darkness", "Metal")

# A section header / total line: "Pokémon: 9", "Trainer", "Energy: 12", "Total Cards: 60".
_HEADER_RE = re.compile(
    r"^\s*(?:pok[eé]mon|trainers?|energy|total\s*cards?)\s*:?\s*\d*\s*$", re.IGNORECASE)

# "<qty> <name>" with an optional x ("4 ", "4x ", "x4 ").
_LINE_RE = re.compile(r"^\s*x?\s*(\d+)\s*x?\s+(.+?)\s*$", re.IGNORECASE)

# A trailing "SETCODE NUMBER" suffix: "MEG 50", "PAL 172", "SVI 84", "PR-SV 44", "sv1 5".
_SETCODE_RE = re.compile(r"\s+[A-Za-z]{1,5}(?:-[A-Za-z]{1,4})?\s+\d+[A-Za-z]?$")

# "(Basic) <Type> Energy" -> canonical "Basic <Type> Energy".
_ENERGY_RE = re.compile(
    r"^(?:basic\s+)?(" + "|".join(BASIC_ENERGY_TYPES) + r")\s+energy$", re.IGNORECASE)


@dataclass
class ImportResult:
    """The outcome of importing a deck list."""
    recipe: list[tuple[str, int]] = field(default_factory=list)    # matched (canonical_name, qty)
    missing: list[tuple[str, int]] = field(default_factory=list)   # (raw_name, qty) not in the DB
    by_type: dict[str, int] = field(default_factory=dict)          # supertype -> matched qty
    total: int = 0            # total quantity across every parsed card line
    matched_total: int = 0    # total quantity that matched the DB
    warnings: list[str] = field(default_factory=list)              # unparseable lines, etc.


def _fold(s: str) -> str:
    """Lowercase + strip accents, for forgiving name matching ('Poké' == 'poke')."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _normalize_energy(name: str) -> str:
    """'Psychic Energy' / 'Basic Psychic Energy' -> 'Basic Psychic Energy'."""
    m = _ENERGY_RE.match(name.strip())
    return f"Basic {m.group(1).capitalize()} Energy" if m else name


def _candidates(raw: str) -> list[str]:
    """Ordered candidate canonical names to try for a raw deck-list name. We try the
    name as-is AND with the set code stripped (and energy-normalised forms of each),
    so a wrong strip can still fall back to an exact match."""
    raw = raw.strip()
    bases = [raw]
    stripped = _SETCODE_RE.sub("", raw).strip()
    if stripped and stripped != raw:
        bases.append(stripped)
    out, seen = [], set()
    for b in bases:
        for cand in (b, _normalize_energy(b)):
            key = _fold(cand)
            if key and key not in seen:
                seen.add(key)
                out.append(cand)
    return out


def parse_line(line: str):
    """Parse one line -> (qty:int, raw_name:str) or None if it isn't a card line."""
    line = line.strip()
    if not line or line.startswith("#") or _HEADER_RE.match(line):
        return None
    m = _LINE_RE.match(line)
    if not m:
        return ("unparseable", line)        # sentinel for a warning
    return (int(m.group(1)), m.group(2).strip())


def import_deck(text: str, db) -> ImportResult:
    """Parse TCG Live export `text` and match each card against `db` (a CardDB)."""
    by_fold = {_fold(n): n for n in db.names()}
    res = ImportResult()
    merged: dict[str, int] = {}             # canonical_name -> qty (merges split lines)

    for raw_line in text.splitlines():
        parsed = parse_line(raw_line)
        if parsed is None:
            continue
        qty, name = parsed
        if qty == "unparseable":
            res.warnings.append(f"could not parse line: {name!r}")
            continue

        res.total += qty
        canon = None
        for cand in _candidates(name):
            canon = by_fold.get(_fold(cand))
            if canon:
                break
        if canon:
            merged[canon] = merged.get(canon, 0) + qty
            res.matched_total += qty
            supertype = db.get(canon).supertype
            res.by_type[supertype] = res.by_type.get(supertype, 0) + qty
        else:
            display = _SETCODE_RE.sub("", name).strip() or name   # drop the set code for display
            res.missing.append((display, qty))

    res.recipe = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))
    return res


def format_summary(res: ImportResult, deck_name: str) -> str:
    """A human-readable import summary."""
    lines = [f'TCG Live import: "{deck_name}"']
    lines.append(f"  Total cards parsed: {res.total}")
    lines.append(f"  Matched: {res.matched_total}/{res.total} "
                 f"({len(res.recipe)} distinct cards)")
    if res.by_type:
        by = "  ·  ".join(f"{n} {t}" for t, n in sorted(res.by_type.items()))
        lines.append(f"  By type: {by}")
    if res.missing:
        miss_total = sum(q for _, q in res.missing)
        lines.append(f"  Missing ({miss_total} card(s) not in the current pool):")
        for name, qty in res.missing:
            lines.append(f"    - {qty} {name}")
    else:
        lines.append("  Missing: none — every card resolved ✓")
    for w in res.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)


def save_deck(res: ImportResult, deck_name: str,
              out_dir: str = "decks/imported") -> str:
    """Write the imported deck to decks/imported/<name>.json and return the path.

    The `recipe` field is the engine's deck format — `[[card_name, qty], ...]` — so a
    fully-matched, legal import can be dropped straight into a DECKS entry later."""
    os.makedirs(out_dir, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", deck_name).strip("_") or "imported_deck"
    path = os.path.join(out_dir, f"{safe}.json")
    record = {
        "name": deck_name,
        "source": "tcglive",
        "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_cards": res.total,
        "matched": res.matched_total,
        "by_type": res.by_type,
        "recipe": [[name, qty] for name, qty in res.recipe],
        "missing": [[name, qty] for name, qty in res.missing],
        "warnings": res.warnings,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    return path
