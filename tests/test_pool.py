#!/usr/bin/env python3
"""
test_pool.py — fast sanity checks on the built card pool.

Run AFTER fetch_standard_pool.py. These are the invariants that, if they break,
mean the data layer is lying to the engine. Cheap to run, catches rotation drift,
schema changes upstream, and accidental inclusion of illegal cards.

    python3 tests/test_pool.py            # checks data/standard_pool.json
    python3 tests/test_pool.py path.json  # check a specific file
"""

import json
import sys

LEGAL_MARKS = {"H", "I", "J"}
REQUIRED_KEYS = {"id", "name", "supertype", "subtypes", "regulationMark"}
SUPERTYPES = {"Pokémon", "Trainer", "Energy"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check(pool):
    fails = []

    def fail(msg):
        fails.append(msg)

    # 1. non-empty and sane size (rotation pools sit in the ~1000-1600 range;
    #    a tiny number means the fetch broke, a huge one means the filter broke)
    if not (800 <= len(pool) <= 2500):
        fail(f"pool size {len(pool)} outside expected 800-2500 range")

    seen_names = set()
    seen_ids = set()
    for c in pool:
        # 2. every card has the keys the engine reads
        missing = REQUIRED_KEYS - c.keys()
        if missing:
            fail(f"{c.get('id','?')}: missing keys {missing}")

        # 3. ONLY legal marks made it through (the whole point of the filter)
        if c.get("regulationMark") not in LEGAL_MARKS:
            fail(f"{c['id']}: illegal mark {c.get('regulationMark')!r} leaked into pool")

        # 4. supertype is one of the three real buckets
        if c.get("supertype") not in SUPERTYPES:
            fail(f"{c['id']}: unknown supertype {c.get('supertype')!r}")

        # 5. names de-duped (engine references by name)
        if c["name"] in seen_names:
            fail(f"duplicate name in pool: {c['name']}")
        seen_names.add(c["name"])

        # 6. ids unique
        if c["id"] in seen_ids:
            fail(f"duplicate id in pool: {c['id']}")
        seen_ids.add(c["id"])

        # 7. Pokemon must have HP and at least one way to act
        if c["supertype"] == "Pokémon":
            if not c.get("hp"):
                fail(f"{c['id']} ({c['name']}): Pokemon with no HP")
            if not c.get("attacks") and not c.get("abilities"):
                fail(f"{c['id']} ({c['name']}): Pokemon with no attacks or abilities")

    return fails


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/standard_pool.json"
    pool = load(path)
    fails = check(pool)
    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails[:25]:
            print("  -", f)
        if len(fails) > 25:
            print(f"  ... and {len(fails)-25} more")
        sys.exit(1)
    print(f"OK — {len(pool)} cards, all invariants hold.")


if __name__ == "__main__":
    main()
