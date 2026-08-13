#!/usr/bin/env python3
"""
test_determinism.py — the engine MUST be 100% deterministic: the same seed produces
the exact same game, every time, in any process. If this breaks, every win rate the
simulator reports is worthless.

Two guards:
  1. IN-PROCESS — the same seed played twice yields an identical winner AND an
     identical move-by-move log (greedy and MCTS).
  2. CROSS-PROCESS / HASH-INDEPENDENCE — the same seed played in two separate Python
     processes with DIFFERENT PYTHONHASHSEED values yields byte-identical logs. This
     catches the classic nondeterminism bug: iterating a set/dict of objects whose
     order depends on per-process hash randomization.

Run from project root:  python3 tests/test_determinism.py
"""

import hashlib
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import load_deck
from src.engine.agents import GreedyAgent
from src.engine.mcts import MCTSAgent, ISMCTSAgent
from src.engine.game import setup_game, start_turn
from src.engine.run import finish_game, _resolve_tie

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make(agent, seed):
    """One agent of each kind, seeded identically — the shared factory used by both
    the in-process and the cross-process guard so they can't drift apart."""
    if agent == "mcts":
        return MCTSAgent(iterations=40, rollout="eval", rng=random.Random(seed),
                         search_plies=2)
    if agent == "mcts2":
        # Cross-turn ISMCTS. Deliberately exercised WITH tree reuse on (its default):
        # reuse carries statistics between decisions, so if it introduced any ordering
        # or rng divergence this is where it would show up.
        return ISMCTSAgent(iterations=25, rng=random.Random(seed), max_turn_hops=2)
    return GreedyAgent(random.Random(seed))


def _play(db, d1, d2, seed, agent="greedy"):
    da, dbk = load_deck(db, d1), load_deck(db, d2)
    st = setup_game(da, dbk, seed=seed, db=db)
    start_turn(st)
    finish_game(st, _make(agent, seed), _make(agent, seed))
    _resolve_tie(st)
    return st.winner, "\n".join(st.log)


# A tiny self-contained program for the cross-process guard: play one game and
# print "<winner> <md5-of-log>". Stdout is compared across hash seeds.
_SUBPROG = (
    "import sys,random,hashlib;"
    f"sys.path.insert(0,{REPO!r});"
    f"sys.path.insert(0,{os.path.join(REPO, 'tests')!r});"
    "from src.engine.cards import CardDB;"
    "from src.engine.decks import load_deck;"
    "from test_determinism import _make;"
    "from src.engine.game import setup_game,start_turn;"
    "from src.engine.run import finish_game,_resolve_tie;"
    "db=CardDB.from_pool('data/standard_pool.json');"
    "d1,d2,seed,ag=sys.argv[1],sys.argv[2],int(sys.argv[3]),sys.argv[4];"
    "st=setup_game(load_deck(db,d1),load_deck(db,d2),seed=seed,db=db);start_turn(st);"
    "finish_game(st,_make(ag,seed),_make(ag,seed));"
    "_resolve_tie(st);"
    "log='\\n'.join(st.log);"
    "print(st.winner, hashlib.md5(log.encode()).hexdigest())"
)


def _run_subproc(d1, d2, seed, hashseed, agent="greedy"):
    env = dict(os.environ, PYTHONHASHSEED=str(hashseed))
    out = subprocess.run([sys.executable, "-c", _SUBPROG, d1, d2, str(seed), agent],
                         cwd=REPO, env=env, capture_output=True, text=True)
    if out.returncode != 0:
        return f"ERROR: {out.stderr.strip()[-300:]}"
    return out.stdout.strip()


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    matchups = [("dragapult", "charizard_xy"), ("raging_bolt", "dragapult")]

    # 1. In-process: identical winner + identical log on a repeat (greedy).
    for d1, d2 in matchups:
        for seed in (0, 7, 42):
            w1, l1 = _play(db, d1, d2, seed)
            w2, l2 = _play(db, d1, d2, seed)
            check(w1 == w2 and l1 == l2,
                  f"greedy {d1} vs {d2} seed={seed}: repeat not identical "
                  f"(winners {w1}/{w2}, logs {'eq' if l1 == l2 else 'DIFFER'})")

    # 2. In-process: MCTS is deterministic too (same seed -> same game).
    w1, l1 = _play(db, "raging_bolt", "dragapult", 3, agent="mcts")
    w2, l2 = _play(db, "raging_bolt", "dragapult", 3, agent="mcts")
    check(w1 == w2 and l1 == l2,
          f"mcts repeat not identical (winners {w1}/{w2}, "
          f"logs {'eq' if l1 == l2 else 'DIFFER'})")

    # 2b. In-process: the cross-turn ISMCTS agent (mcts2) is deterministic too.
    #     It has two extra ways to go wrong that plain MCTS does not: the retained
    #     subtree (tree reuse) carries state BETWEEN decisions, and selection walks
    #     a per-node action set that must be ordered by semantic key rather than by
    #     dict iteration. Both are covered by replaying the same seed.
    w1, l1 = _play(db, "raging_bolt", "dragapult", 3, agent="mcts2")
    w2, l2 = _play(db, "raging_bolt", "dragapult", 3, agent="mcts2")
    check(w1 == w2 and l1 == l2,
          f"mcts2 (cross-turn ISMCTS) repeat not identical (winners {w1}/{w2}, "
          f"logs {'eq' if l1 == l2 else 'DIFFER'})")

    # 3. Cross-process / hash-independence: same seed, different PYTHONHASHSEED ->
    #    byte-identical result (md5 of the full log).
    for d1, d2 in matchups:
        a = _run_subproc(d1, d2, 123, hashseed=0)
        b = _run_subproc(d1, d2, 123, hashseed=1)
        c = _run_subproc(d1, d2, 123, hashseed="random")
        check(a == b == c and not a.startswith("ERROR"),
              f"{d1} vs {d2}: cross-process result varies with PYTHONHASHSEED "
              f"(0={a!r} 1={b!r} random={c!r}) — nondeterministic set/dict ordering")

    # 3b. Same guard for mcts2. This is the one that would catch an ISMCTS node
    #     iterating its children in dict order, or a UCB tie broken by whichever
    #     equal-valued child a set happened to yield first.
    a = _run_subproc("dragapult", "charizard_xy", 123, hashseed=0, agent="mcts2")
    b = _run_subproc("dragapult", "charizard_xy", 123, hashseed=1, agent="mcts2")
    c = _run_subproc("dragapult", "charizard_xy", 123, hashseed="random", agent="mcts2")
    check(a == b == c and not a.startswith("ERROR"),
          f"mcts2 cross-process result varies with PYTHONHASHSEED "
          f"(0={a!r} 1={b!r} random={c!r}) — unstable tie-break or dict ordering")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — determinism: same seed = identical game, in-process "
          "(greedy + MCTS + cross-turn ISMCTS) and cross-process "
          "(hash-seed-independent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
