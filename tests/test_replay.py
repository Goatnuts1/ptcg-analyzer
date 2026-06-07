#!/usr/bin/env python3
"""
test_replay.py — game save/load for battle replay.

Asserts: a saved game (1) writes a well-formed JSON record, (2) round-trips, and
(3) re-simulates from its seed to a byte-identical log — i.e. the saved file is a
FAITHFUL, replayable battle (which only holds because the engine is deterministic).

Run from project root:  python3 tests/test_replay.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli                                   # noqa: E402  (repo-root module)
from src.engine.cards import CardDB          # noqa: E402

POOL = "data/standard_pool.json"


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    gid = "_test_replay_tmp"
    path = os.path.join(cli.SAVE_DIR, f"{gid}.json")
    try:
        cli.save_game("dragapult", "raging_bolt", "greedy", seed=99, game_id=gid, pool=POOL)

        # 1. file written + well-formed record
        check(os.path.exists(path), "save_game should write the JSON file")
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        for key in ("format_version", "game_id", "deck1", "deck2", "agent",
                    "seed", "winner_seat", "winner_deck", "turns", "log"):
            check(key in rec, f"saved record missing key {key!r}")
        check(rec["deck1"] == "dragapult" and rec["deck2"] == "raging_bolt",
              "saved decks should match what was played")
        check(len(rec["log"]) > 0, "saved log should be non-empty")

        # 2. winner_deck is consistent with winner_seat
        if rec["winner_seat"] is None:
            check(rec["winner_deck"] is None, "tie should have winner_deck None")
        else:
            expected = (rec["deck1"], rec["deck2"])[rec["winner_seat"]]
            check(rec["winner_deck"] == expected,
                  f"winner_deck {rec['winner_deck']!r} != seat→deck {expected!r}")

        # 3. faithful replay: re-simulate from the saved recipe -> identical log
        db = CardDB.from_pool(POOL)
        st = cli._play_one(db, rec["deck1"], rec["deck2"], rec["agent"], rec["seed"])
        check(st.log == rec["log"],
              "re-simulation from the saved seed must reproduce the exact log")
        check(st.winner == rec["winner_seat"],
              "re-simulation must reproduce the same winner")
    finally:
        if os.path.exists(path):
            os.remove(path)

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — replay: save writes a faithful, reproducible game record; "
          "re-simulation from the saved seed matches byte-for-byte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
