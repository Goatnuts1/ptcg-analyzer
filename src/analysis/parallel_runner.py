#!/usr/bin/env python3
"""
parallel_runner.py — multiprocessing matchup runner (Phase 1, 2026-11).

Plays N games of deck1 vs deck2 across worker processes with DETERMINISTIC seeds and
writes per-game rows (CSV) plus a summary (JSON). Results depend only on
(deck1, deck2, agents, iters, base seed, game index) — never on the worker count or
scheduling — because every game's seed, seat and pilot RNGs are derived from its index
and rows are re-sorted by index before writing.

SEAT ORDER. The legacy `cli.run(mirror=True)` swaps which deck sits in seat 0 on odd
games, but seat 0 does NOT go first — setup_game flips a coin unless `first_player`
is passed — so "mirrored seats" never controlled the going-first edge. Here the
going-first player is set EXPLICITLY:
    --seat-order both   (default) even games: deck1 goes first; odd: deck2 goes first
    --seat-order deck1  deck1 always goes first
    --seat-order deck2  deck2 always goes first
    --seat-order coin   the engine's coin flip (recorded per game)
and the summary is broken down by who went first.

READ THIS BEFORE QUOTING A NUMBER: these are bot-vs-bot results under this engine's
rules coverage and these pilots. They are a RELATIVE signal (which list/line does
better than another under identical pilots), NOT a prediction of Live/tournament win
rates. Every summary carries that label.

Partial results: the summary JSON is rewritten every `--flush-every` finished games,
so a long MCTS run can be read (and reported) before it finishes.
"""

from __future__ import annotations

import csv
import json
import math
import multiprocessing as mp
import os
import random
import time
from typing import Optional

LABEL = ("relative bot-vs-bot signal under this engine and these pilots — "
         "NOT a prediction of Live/tournament win rates")

# per-process globals, filled by _init (fork: inherited; spawn: re-loaded)
_G: dict = {}


def _init(pool, deck1, deck2, agent1, agent2, iters1, iters2):
    from src.engine.cards import CardDB
    from src.engine.decks import load_deck
    db = CardDB.from_pool(pool)
    _G.update(db=db, d1=load_deck(db, deck1), d2=load_deck(db, deck2),
              agent1=agent1, agent2=agent2, iters1=iters1, iters2=iters2)


def _first_for(i: int, seat_order: str) -> Optional[int]:
    """Seat index (deck1 is always seat 0) that goes first in game i; None = coin."""
    if seat_order == "deck1":
        return 0
    if seat_order == "deck2":
        return 1
    if seat_order == "both":
        return i % 2
    return None


def _play(job):
    i, seed, first = job
    from cli import _make_agent
    from src.engine.run import play_game
    t0 = time.time()
    rng1, rng2 = random.Random(seed), random.Random(seed + 1_000_000)
    a1 = _make_agent(_G["agent1"], rng1, _G["iters1"])
    a2 = _make_agent(_G["agent2"], rng2, _G["iters2"])
    st = play_game(list(_G["d1"]), list(_G["d2"]), a1, a2, seed=seed, db=_G["db"],
                   first_player=first)
    went_first = first if first is not None else _first_mover(st)
    return {
        "game": i, "seed": seed,
        "first": "deck1" if went_first == 0 else "deck2",
        "winner": (None if st.winner is None else ("deck1", "deck2")[st.winner]),
        "turns": st.turn_number,
        "d1_prizes_left": len(st.players[0].prizes),
        "d2_prizes_left": len(st.players[1].prizes),
        "secs": round(time.time() - t0, 3),
    }


def _first_mover(st) -> Optional[int]:
    """Who went first in a coin-flip game: the log's first line names them."""
    for line in st.log:
        if "goes first" in line:
            return 0 if " A goes first" in line else 1
    return None


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def summarize(rows: list[dict], meta: dict) -> dict:
    def block(rs):
        n = len(rs)
        w1 = sum(r["winner"] == "deck1" for r in rs)
        w2 = sum(r["winner"] == "deck2" for r in rs)
        t = n - w1 - w2
        return {"games": n, "deck1_wins": w1, "deck2_wins": w2, "ties": t,
                "deck1_winrate": round(w1 / n, 4) if n else None,
                "deck1_winrate_ci95": wilson(w1, n),
                "avg_turns": round(sum(r["turns"] for r in rs) / n, 2) if n else None}
    return {
        "label": LABEL, **meta,
        "completed": len(rows),
        "overall": block(rows),
        "deck1_first": block([r for r in rows if r["first"] == "deck1"]),
        "deck2_first": block([r for r in rows if r["first"] == "deck2"]),
    }


def run_parallel(deck1: str, deck2: str, games: int, agent1: str = "greedy",
                 agent2: Optional[str] = None, iters1: int = 120,
                 iters2: Optional[int] = None, seed: int = 0, workers: int = 0,
                 seat_order: str = "both", pool: str = "data/standard_pool.json",
                 out: Optional[str] = None, flush_every: int = 200,
                 chunksize: int = 0, quiet: bool = False) -> dict:
    agent2 = agent2 or agent1
    iters2 = iters2 if iters2 is not None else iters1
    workers = workers or os.cpu_count() or 1
    jobs = [(i, seed + i, _first_for(i, seat_order)) for i in range(games)]
    meta = {"deck1": deck1, "deck2": deck2, "agent1": agent1, "agent2": agent2,
            "iters1": iters1, "iters2": iters2, "base_seed": seed, "games_requested": games,
            "seat_order": seat_order, "workers": workers, "pool": pool,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    csv_path = json_path = None
    if out:
        root, ext = os.path.splitext(out)
        csv_path, json_path = root + ".csv", root + ".json"
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    rows: list[dict] = []
    t0 = time.time()

    def flush(final=False):
        if not json_path:
            return
        rs = sorted(rows, key=lambda r: r["game"])
        summ = summarize(rs, {**meta, "elapsed_s": round(time.time() - t0, 1),
                              "finished": final})
        tmp = json_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(summ, f, indent=2)
        os.replace(tmp, json_path)
        with open(csv_path + ".tmp", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["game", "seed", "first", "winner", "turns",
                                              "d1_prizes_left", "d2_prizes_left", "secs"])
            w.writeheader()
            w.writerows(rs)
        os.replace(csv_path + ".tmp", csv_path)

    ctx = mp.get_context("fork")
    cs = chunksize or (1 if agent1 in ("mcts", "mcts2") or agent2 in ("mcts", "mcts2")
                       else max(1, min(64, games // (workers * 8) or 1)))
    with ctx.Pool(workers, initializer=_init,
                  initargs=(pool, deck1, deck2, agent1, agent2, iters1, iters2)) as p:
        for r in p.imap_unordered(_play, jobs, chunksize=cs):
            rows.append(r)
            if len(rows) % flush_every == 0:
                flush()
                if not quiet:
                    print(f"  {len(rows)}/{games} games ({time.time() - t0:.0f}s)",
                          flush=True)
    rows.sort(key=lambda r: r["game"])
    flush(final=True)
    return summarize(rows, {**meta, "elapsed_s": round(time.time() - t0, 1),
                            "finished": True})


def format_summary(s: dict) -> str:
    def line(tag, b):
        if not b["games"]:
            return f"  {tag:<14} (no games)"
        lo, hi = b["deck1_winrate_ci95"]
        return (f"  {tag:<14} n={b['games']:>6}  {s['deck1']} {b['deck1_winrate']:6.1%} "
                f"[{lo:.1%}–{hi:.1%}]  ties {b['ties']}  avg turns {b['avg_turns']}")
    pil = s["agent1"] if s["agent1"] == s["agent2"] else f"{s['agent1']} vs {s['agent2']}"
    return "\n".join([
        f"{s['deck1']} vs {s['deck2']} — {s['completed']} games ({pil}, seed {s['base_seed']}, "
        f"seat order {s['seat_order']}, {s['workers']} workers, {s['elapsed_s']}s)",
        line("overall", s["overall"]),
        line(f"{s['deck1']} first"[:14], s["deck1_first"]),
        line(f"{s['deck2']} first"[:14], s["deck2_first"]),
        f"  [{LABEL}]",
    ])
