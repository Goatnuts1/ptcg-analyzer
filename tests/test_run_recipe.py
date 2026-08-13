#!/usr/bin/env python3
"""
test_run_recipe.py — cli.run_recipe() (a raw (name,qty) recipe on side A, for a
freshly imported deck that isn't registered in DECKS) must produce byte-identical
win/loss/tie counts to cli.run() (a registered deck name on both sides) when given
the SAME underlying recipe, same seed, same agent. If these ever diverge, the
web UI's import-and-simulate flow is silently miscounting wins.

Run: python3 tests/test_run_recipe.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli
from src.engine.decks import DECKS


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    pool = "data/standard_pool.json"

    # no_vacancy's raw recipe, used as an "ad-hoc" deck the same way an
    # imported deck's saved recipe would be.
    recipe_a = DECKS["no_vacancy"]

    via_name = cli.run("no_vacancy", "dragapult", games=20, agent="greedy",
                        seed=1, mirror=True, pool=pool)
    via_recipe = cli.run_recipe(recipe_a, "dragapult", games=20, agent="greedy",
                                 seed=1, mirror=True, pool=pool)
    check(via_name == via_recipe,
          f"run() vs run_recipe() diverged: {via_name} != {via_recipe}")

    # Also check with mirroring off, and a different seed, to make sure the
    # equivalence isn't a coincidence of one specific seed/mirror combo.
    via_name2 = cli.run("innkeeper", "dragapult", games=15, agent="greedy",
                         seed=42, mirror=False, pool=pool)
    via_recipe2 = cli.run_recipe(DECKS["innkeeper"], "dragapult", games=15,
                                  agent="greedy", seed=42, mirror=False, pool=pool)
    check(via_name2 == via_recipe2,
          f"run() vs run_recipe() diverged (no mirror, seed 42): {via_name2} != {via_recipe2}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_run_recipe.py: all checks passed (run_recipe matches run() exactly)")


if __name__ == "__main__":
    main()
