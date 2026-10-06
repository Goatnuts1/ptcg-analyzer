#!/usr/bin/env python3
"""
fetch_standard_pool.py  —  the data layer for the deck analyzer.

WHAT IT DOES (eli15):
  Pokemon prints every card with a tiny letter in the corner: the "regulation
  mark". The game's Standard format only allows certain letters. Right now (2026
  season) the legal letters are H, I, and J. Everything G and older is retired.

  This script downloads the official card database, keeps ONLY the Standard-legal
  cards, strips it down to the fields a game engine actually needs, and saves a
  clean JSON file you can load instantly without hitting the network again.

TWO SOURCES (pick one):
  1. GitHub data dump  (PokemonTCG/pokemon-tcg-data) — no API key, works offline
     after one clone. This is what this script uses by default.
  2. Live API (api.pokemontcg.io) — same data, queryable, needs internet each run.
     A free API key raises your rate limit. Example query is shown at the bottom.

USAGE:
  python3 fetch_standard_pool.py                 # build from the GitHub dump
  python3 fetch_standard_pool.py --out pool.json # choose output path
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

# The set of legal regulation marks is the SINGLE SOURCE OF TRUTH in
# engine/legality.py — imported here so the fetcher and the runtime deck-legality
# checks can never drift. Rotation = edit STANDARD_LEGAL_MARKS there, then re-run.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.legality import STANDARD_LEGAL_MARKS as LEGAL_MARKS

RAW = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def list_set_codes():
    """Every set file lives at cards/en/<code>.json — sets.json lists the codes."""
    sets = fetch_json(f"{RAW}/sets/en.json")
    return [s["id"] for s in sets]


def is_standard_legal(card):
    """A card is in our pool if its regulation mark is one of the currently legal
    letters.

    Used to require the data dump's own `legalities.standard == "Legal"` too, as a
    belt-and-suspenders check meant to catch a card banned outright despite a legal
    mark. Dropped it (meta-scan 2026-09-03): the upstream dump's `legalities` field
    lags real tournament legality by set — as of this date it flags 112 of "Mega
    Evolution — Perfect Order" (me3)'s 124 mark-J cards "Not Legal", including
    Mega Starmie ex and Telepathic Psychic Energy, both of which are real,
    tournament-played Standard cards (Perfect Order released 2026-03-27, well past
    any post-release legality delay) — a false-negative that silently broke
    `gardevoir_real`/`starmie_toolbox`/`greninja`. And per the official 2026 rotation
    announcement, Standard currently has ZERO individually banned cards — rotation
    (regulation mark) is the only exclusion mechanism in play — so the second check
    had no real bans left to catch and was pure downside. Mark alone is the correct
    single source of truth until that changes; a genuine future ban needs its own
    explicit handling (this schema has no "Banned" value to key off — only "Legal"/
    "Not Legal" — so a ban would need to be listed by name, not inferred from here).
    """
    mark = card.get("regulationMark")
    return mark in LEGAL_MARKS


def safe_hp(value):
    """HP is usually a clean integer string, but don't assume it. Some oddball
    prints or upstream data hiccups could be non-numeric; degrade to None rather
    than crash the whole pull on one bad card."""
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def slim(card):
    """Keep only what an engine needs. The art, flavor text, prices, etc. are noise."""
    return {
        "id": card["id"],
        "name": card["name"],
        "supertype": card["supertype"],            # Pokemon / Trainer / Energy
        "subtypes": card.get("subtypes", []),      # Basic, Stage 2, ex, Supporter, Item...
        "hp": safe_hp(card.get("hp")),
        "types": card.get("types", []),
        "evolvesFrom": card.get("evolvesFrom"),    # what this evolves up from
        "evolvesTo": card.get("evolvesTo", []),    # what this can become (evolution planning)
        "abilities": card.get("abilities", []),    # name + text
        "attacks": card.get("attacks", []),        # name, cost, damage, text
        "rules": card.get("rules", []),            # Trainer/Energy effect text
        "weaknesses": card.get("weaknesses", []),
        "resistances": card.get("resistances", []),
        "retreatCost": card.get("retreatCost", []),
        "regulationMark": card.get("regulationMark"),
    }


def build_pool():
    pool, seen = [], set()
    codes = list_set_codes()
    failed = []
    for code in codes:
        try:
            cards = fetch_json(f"{RAW}/cards/en/{code}.json")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as e:
            # A failed set means a SILENTLY INCOMPLETE pool — the exact failure
            # mode that makes a stale/partial pool look healthy. Track it loudly
            # instead of swallowing it.
            print(f"  !! FAILED {code}: {e}", file=sys.stderr)
            failed.append(code)
            continue
        kept = 0
        for c in cards:
            if not is_standard_legal(c):
                continue
            # De-dupe by name: many sets reprint the same card. The engine cares
            # about the card, not which set the art came from.
            if c["name"] in seen:
                continue
            seen.add(c["name"])
            pool.append(slim(c))
            kept += 1
        if kept:
            print(f"  {code}: +{kept}", file=sys.stderr)

    # Merge the hand-maintained supplement: Standard-legal cards the upstream dump
    # hasn't published yet (newer Mega-era cards needed for current tournament
    # lists). Deduped by name, so if upstream later ships them, upstream WINS and
    # the supplement entry is silently dropped — at which point it can be deleted
    # from data/manual_cards.json. This keeps the pool reproducible from source.
    #
    # PRINT_OVERRIDES is the escape hatch from that rule (meta-scan 2026-09-03):
    # upstream started shipping its OWN bare-name "Drilbur" (Temporal Forces
    # sv5-85, ability Dig Dig Dig) after the manual "Drilbur" entry (Pitch Black
    # pbl-46, Call for Family — PBL isn't in the upstream dump at all) was already
    # the name every deck/test in this repo means by bare "Drilbur". Letting
    # upstream win here wouldn't be the same card gaining upstream coverage (the
    # normal, safe case this rule exists for) — it'd silently swap the tournament
    # print for an unrelated one under the same name. The TEF print keeps its own
    # explicit "Drilbur (TEF)" manual entry, so both prints are reachable.
    # "Rocky Fighting Energy" and "Telepathic Psychic Energy" join Drilbur for a
    # different reason: the upstream Energy-supertype JSON has no "types" field at
    # all (what a Special Energy provides lives only in its free-text `rules`), so
    # letting upstream's copy win would silently zero out InPlayPokemon.provided_types()
    # for both — they'd still exist in the pool, just unable to pay any cost. The
    # manual entries carry the type explicitly, exactly like every other Special
    # Energy this engine reads generically instead of by hardcoded name.
    # "Alakazam" is the same shape as Drilbur: sv6-82 (mark H, "Strange Hacking" /
    # "Psychic") is processed before me1-56 (mark I, "Psychic Draw" ability +
    # "Powerful Hand" attack — the print `alakazam_deck` and its Regional-provenance
    # relatives actually run) in set order, so upstream's earlier print would win the
    # bare name and silently swap out the attack every one of those decks needs.
    # "Staryu" (me3-20) is a same-print fixup, not a collision: upstream's own copy
    # is otherwise fine but ships an empty evolvesTo (Mega Starmie ex's evolvesFrom
    # is populated, so nothing in the engine's own evolution matching — which reads
    # ONLY the evolving card's evolvesFrom — actually breaks; this just restores the
    # informational back-link the data-integrity tests check).
    PRINT_OVERRIDES = {"Drilbur", "Rocky Fighting Energy", "Telepathic Psychic Energy",
                        "Alakazam", "Staryu"}
    for c in load_manual_supplement():
        overriding = c["name"] in PRINT_OVERRIDES and c["name"] in seen
        if c["name"] in seen and not overriding:
            print(f"  manual: skip {c['name']!r} (now in upstream)", file=sys.stderr)
            continue
        # Respect rotation: a manual card whose mark has rotated out is dropped,
        # exactly like an upstream card would be. (Keeps the supplement honest when
        # LEGAL_MARKS changes — no zombie cards lingering past rotation.)
        if c.get("regulationMark") not in LEGAL_MARKS:
            print(f"  manual: skip {c['name']!r} (mark {c.get('regulationMark')!r} "
                  f"not legal)", file=sys.stderr)
            continue
        if overriding:
            # Replace, don't duplicate: drop the upstream print this name already
            # resolved to before adding the manual one back under the same name.
            pool[:] = [p for p in pool if p["name"] != c["name"]]
            print(f"  manual: override {c['name']!r} (upstream print replaced)",
                  file=sys.stderr)
        seen.add(c["name"])
        pool.append(slim(c))
        print(f"  manual: +1 {c['name']!r}", file=sys.stderr)

    return pool, codes, failed


def load_manual_supplement():
    """Tracked cards missing from the upstream dump. Path is resolved relative to
    this script (repo_root/data/manual_cards.json), so it works regardless of cwd.
    Returns [] if the file is absent."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, os.pardir, "data", "manual_cards.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="standard_pool.json")
    args = ap.parse_args()

    print("Building Standard-legal pool (marks: %s)..." % ", ".join(sorted(LEGAL_MARKS)),
          file=sys.stderr)
    pool, codes, failed = build_pool()

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)

    # Metadata sidecar: a small provenance file written next to the pool so you
    # (and the engine) can tell at a glance when it was built, from how many sets,
    # and whether the pull was complete. Answers "is this pool fresh / trustworthy?"
    from collections import Counter
    meta_path = args.out.rsplit(".", 1)[0] + "_meta.json"
    meta = {
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "legal_marks": sorted(LEGAL_MARKS),
        "card_count": len(pool),
        "by_supertype": dict(Counter(c["supertype"] for c in pool)),
        "sets_total": len(codes),
        "sets_failed": failed,
        "complete": not failed,
        "source": RAW,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(pool)} unique Standard-legal cards -> {args.out}", file=sys.stderr)
    print(f"Metadata -> {meta_path}", file=sys.stderr)
    if failed:
        # Non-zero exit so a CI step or your session-start ritual can catch it.
        print(f"\nWARNING: {len(failed)} set(s) failed to download: {failed}\n"
              f"The pool is INCOMPLETE. Re-run before trusting it.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# SAME THING VIA THE LIVE API (alternative to the GitHub dump):
#
#   import requests
#   r = requests.get(
#       "https://api.pokemontcg.io/v2/cards",
#       params={"q": 'regulationMark:H OR regulationMark:I OR regulationMark:J',
#               "pageSize": 250},
#       headers={"X-Api-Key": "YOUR_FREE_KEY"},  # optional, raises rate limit
#   )
#   cards = r.json()["data"]
#
# The query language is field:value. Useful filters:
#   types:Fire            subtypes:ex            hp:[200 TO *]
#   name:"Dragapult ex"   set.id:sv9
# ---------------------------------------------------------------------------
