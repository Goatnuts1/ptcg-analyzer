#!/usr/bin/env python3
"""
test_analysis.py — round-robin analysis helpers: Elo ratings, CSV/HTML export,
and the 'who would win' fun-mode summary (src/analysis/).

Run from project root:  python3 tests/test_analysis.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.ratings import compute_elo
from src.analysis import report


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # A clear strength order A > B > C, as a win-rate matrix.
    decks = ["A", "B", "C"]
    matrix = {
        "A": {"A": None, "B": 70, "C": 90},
        "B": {"A": 30, "B": None, "C": 70},
        "C": {"A": 10, "B": 30, "C": None},
    }
    overall = {"A": 80.0, "B": 50.0, "C": 20.0}

    # --- Elo ---
    elo = compute_elo(decks, matrix)
    check(elo["A"] > elo["B"] > elo["C"], f"Elo must rank A>B>C (got {elo})")
    check(abs(sum(elo.values()) / 3 - 1500) <= 1, f"Elo should mean-center on 1500 ({elo})")
    check(compute_elo(decks, matrix) == elo, "Elo must be deterministic")
    # Beating strong opponents should matter: A's edge over the field shows as a gap.
    check(elo["A"] - elo["C"] > 100, "clear strength gap should produce a clear Elo gap")

    # --- CSV ---
    csv = report.matrix_to_csv(decks, matrix, overall, elo)
    lines = csv.strip().splitlines()
    check(lines[0] == "deck,A,B,C,overall,elo", f"CSV header wrong: {lines[0]}")
    check(lines[1].startswith("A,,70,90,80.0,"), f"CSV row A wrong: {lines[1]}")
    check(len(lines) == 4, "CSV should have a header + 3 deck rows")

    # --- HTML ---
    html = report.matrix_to_html(decks, matrix, overall, elo, title="Test")
    check(html.startswith("<!doctype html>"), "HTML should be a standalone doc")
    check("<title>Test</title>" in html, "HTML should carry the title")
    for d in decks:
        check(f">{d}<" in html, f"HTML should mention deck {d}")
    check("70%" in html and "background:" in html, "HTML should color-code win %")

    # --- who_would_win ---
    s = report.who_would_win("gardevoir", "fire", w1=72, w2=28, ties=0, games=100)
    check("gardevoir wins about 7 out of 10" in s, f"favorite/odds wrong:\n{s}")
    check("🏆" in s, "should name a winner with a trophy")
    even = report.who_would_win("a", "b", w1=51, w2=49, ties=0, games=100)
    check("coin flip" in even, "near-even should read as a coin flip")
    blow = report.who_would_win("a", "b", w1=95, w2=5, ties=0, games=100)
    check("blowout" in blow and "a wins about 10 out of 10" in blow, "lopsided should be a blowout")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — analysis: Elo ranks + mean-centers + is deterministic; CSV/HTML export "
          "well-formed; who-would-win names the favorite with sensible flavor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
