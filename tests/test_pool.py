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

    # 1. non-empty and sane size. Current 2026 pool is 1273. Bounds are tight
    #    enough to catch a broken/partial fetch, loose enough to absorb a few
    #    set releases. NOTE: a format rotation drops a big chunk of cards — when
    #    you change LEGAL_MARKS, re-baseline these bounds too.
    if not (1100 <= len(pool) <= 1800):
        fail(f"pool size {len(pool)} outside expected 1100-1800 range "
             f"(broken fetch? or time to re-baseline after a rotation?)")

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
            # 7b. evolution fields must be list-typed (engine iterates them)
            if not isinstance(c.get("evolvesTo", []), list):
                fail(f"{c['id']} ({c['name']}): evolvesTo is not a list")

        # 8. Trainers and Energy carry their effect in `rules` — empty means the
        #    card would do nothing in the engine. Verified non-empty across the
        #    current pool, so treat a violation as a real problem.
        if c["supertype"] in ("Trainer", "Energy") and not c.get("rules"):
            fail(f"{c['id']} ({c['name']}): {c['supertype']} with empty rules")

        # 9. every attack must at least have a name (engine keys moves by name)
        for atk in c.get("attacks", []):
            if not atk.get("name"):
                fail(f"{c['id']} ({c['name']}): attack with no name")

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
