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
import json
import sys
import urllib.request

# The regulation marks that are legal in the 2026 Standard format.
# When the format rotates again, you change ONE line here.
LEGAL_MARKS = {"H", "I", "J"}

RAW = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def list_set_codes():
    """Every set file lives at cards/en/<code>.json — sets.json lists the codes."""
    sets = fetch_json(f"{RAW}/sets/en.json")
    return [s["id"] for s in sets]


def is_standard_legal(card):
    """A card is in our pool only if BOTH checks pass.

    1. Its regulation mark is one of the currently legal letters.
    2. The data dump's own legality field agrees it's Standard legal.
       (Belt-and-suspenders: catches banned cards that still have a legal mark.)
    """
    mark = card.get("regulationMark")
    legal_field = card.get("legalities", {}).get("standard")
    return mark in LEGAL_MARKS and legal_field == "Legal"


def slim(card):
    """Keep only what an engine needs. The art, flavor text, prices, etc. are noise."""
    return {
        "id": card["id"],
        "name": card["name"],
        "supertype": card["supertype"],            # Pokemon / Trainer / Energy
        "subtypes": card.get("subtypes", []),      # Basic, Stage 2, ex, Supporter, Item...
        "hp": int(card["hp"]) if card.get("hp") else None,
        "types": card.get("types", []),
        "evolvesFrom": card.get("evolvesFrom"),
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
    for code in codes:
        try:
            cards = fetch_json(f"{RAW}/cards/en/{code}.json")
        except Exception as e:
            print(f"  skip {code}: {e}", file=sys.stderr)
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
    return pool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="standard_pool.json")
    args = ap.parse_args()

    print("Building Standard-legal pool (marks: %s)..." % ", ".join(sorted(LEGAL_MARKS)),
          file=sys.stderr)
    pool = build_pool()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    print(f"\nDone. {len(pool)} unique Standard-legal cards -> {args.out}", file=sys.stderr)


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
