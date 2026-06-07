#!/usr/bin/env python3
"""
test_round_robin.py — the round-robin win-rate matrix (cli.py --round-robin).

Asserts the matrix is well-formed (symmetric win rates, empty diagonal, overall =
mean across opponents) and deterministic (same seed → identical matrix).

Run from project root:  python3 tests/test_round_robin.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli                                   # noqa: E402  (repo-root module)

POOL = "data/standard_pool.json"
DECKS = ["dragapult", "charizard_xy", "raging_bolt"]
GAMES = 12                                   # small but enough to be non-degenerate


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    res = cli.round_robin(DECKS, GAMES, agent="greedy", seed=0, pool=POOL)
    m, overall = res["matrix"], res["overall"]

    # 1. shape: every deck has a row; diagonal is None; off-diagonal is a number.
    for a in DECKS:
        check(m[a][a] is None, f"diagonal {a} vs {a} should be None")
        for b in DECKS:
            if a != b:
                check(isinstance(m[a][b], (int, float)), f"{a} vs {b} should be a win %")

    # 2. symmetry: a's win% vs b + b's win% vs a == 100 (decided games).
    for i, a in enumerate(DECKS):
        for b in DECKS[i + 1:]:
            check(abs(m[a][b] + m[b][a] - 100) < 1e-6,
                  f"win rates not complementary: {a} {m[a][b]} / {b} {m[b][a]}")

    # 3. overall = mean of a deck's win % across its opponents.
    for a in DECKS:
        opp = [m[a][b] for b in DECKS if b != a]
        check(abs(overall[a] - sum(opp) / len(opp)) < 1e-6,
              f"overall for {a} != mean of its row")

    # 4. determinism: same seed reproduces the exact matrix.
    res2 = cli.round_robin(DECKS, GAMES, agent="greedy", seed=0, pool=POOL)
    same = all(res2["matrix"][a][b] == m[a][b] for a in DECKS for b in DECKS)
    check(same, "round-robin not deterministic for a fixed seed")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — round-robin matrix: well-formed (symmetric, empty diagonal, correct "
          "overall) and deterministic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
