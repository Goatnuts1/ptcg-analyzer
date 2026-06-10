#!/usr/bin/env python3
"""
cli.py — run a head-to-head between two decks and report win rates.

    python3 cli.py --deck1 dragapult --deck2 raging_bolt --games 5000
    python3 cli.py --deck1 raging_bolt --deck2 charizard_xy --games 1000 --agent mcts

Decks are referenced by name from the registry in src/engine/decks.py (run with
--list to see them). Seats are mirrored by default (each deck goes first in half
the games) so the win rate isn't skewed by the going-first advantage. Everything
is deterministic: the same --seed reproduces the exact same set of games.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time

import sys

from src.engine.cards import CardDB
from src.engine.decks import DECKS, load_deck
from src.engine.agents import RandomAgent, GreedyAgent
from src.engine.run import play_game
from src.importers.tcglive import import_deck, format_summary, save_deck
from src.analysis.ratings import compute_elo
from src.analysis.report import matrix_to_csv, matrix_to_html, who_would_win

SAVE_DIR = "saved_games"
SAVE_FORMAT = 1


def _make_agent(kind: str, rng: random.Random, iters: int = 120):
    if kind == "random":
        return RandomAgent(rng)
    if kind == "mcts":
        from src.engine.mcts import MCTSAgent
        return MCTSAgent(iterations=iters, rollout="eval", rng=rng, search_plies=2)
    return GreedyAgent(rng)


def _play_one(db, deck1, deck2, agent, seed):
    """Play a single game, deck1 in seat 0 (fixed orientation = reproducible)."""
    rng_a, rng_b = random.Random(seed), random.Random(seed + 1_000_000)
    st = play_game(load_deck(db, deck1), load_deck(db, deck2),
                   _make_agent(agent, rng_a), _make_agent(agent, rng_b),
                   seed=seed, db=db)
    return st


def save_game(deck1, deck2, agent, seed, game_id, pool):
    """Play one game and save the full record (recipe + step log) to JSON. Because
    the engine is deterministic, the recipe (decks/agent/seed) reproduces the game
    exactly — the saved file is both a readable record and a replayable battle."""
    db = CardDB.from_pool(pool)
    st = _play_one(db, deck1, deck2, agent, seed)
    winner_deck = None if st.winner is None else (deck1, deck2)[st.winner]
    record = {
        "format_version": SAVE_FORMAT,
        "game_id": game_id,
        "deck1": deck1, "deck2": deck2,
        "agent": agent, "seed": seed,
        "winner_seat": st.winner,
        "winner_deck": winner_deck,
        "turns": st.turn_number,
        "log": st.log,
    }
    os.makedirs(SAVE_DIR, exist_ok=True)
    path = os.path.join(SAVE_DIR, f"{game_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    result = "tie" if winner_deck is None else f"{winner_deck} wins"
    print(f"Saved game '{game_id}' -> {path}")
    print(f"  {deck1} vs {deck2} (agent={agent}, seed={seed}) — {result} "
          f"in {st.turn_number} turns, {len(st.log)} steps")


_STEP_RE = re.compile(r"^T(\d+) P(\d+): (.*)$", re.S)


def replay_game(path, pool):
    """Load a saved game and print it step by step, grouped by turn. If the decks
    are still in the registry, re-simulate from the seed and confirm the log matches
    (a faithful-replay integrity check)."""
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except FileNotFoundError:
        print(f"No saved game at {path!r}")
        return
    except json.JSONDecodeError as e:
        print(f"{path!r} is not a valid saved game: {e}")
        return

    d1, d2 = rec.get("deck1"), rec.get("deck2")
    print(f"Replaying '{rec.get('game_id', '?')}': {d1} vs {d2}  "
          f"(agent={rec.get('agent')}, seed={rec.get('seed')})")
    print("=" * 64)
    last_turn = None
    for i, line in enumerate(rec.get("log", []), 1):
        m = _STEP_RE.match(line)
        if m:
            turn, player, msg = m.group(1), m.group(2), m.group(3)
            if turn != last_turn:
                print(f"\n── Turn {turn} ──")
                last_turn = turn
            print(f"  {i:>3}. P{player}: {msg}")
        else:
            print(f"  {i:>3}. {line}")
    print("=" * 64)
    wd = rec.get("winner_deck")
    result = "tie" if wd is None else f"{wd} wins"
    print(f"Result: {result} in {rec.get('turns')} turns ({len(rec.get('log', []))} steps)")

    # Integrity check: re-run deterministically and confirm the saved log reproduces.
    if d1 in DECKS and d2 in DECKS and rec.get("agent") and rec.get("seed") is not None:
        db = CardDB.from_pool(pool)
        st = _play_one(db, d1, d2, rec["agent"], rec["seed"])
        if st.log == rec.get("log"):
            print("✓ verified: re-simulated from seed — log matches (faithful replay)")
        else:
            print("⚠ WARNING: re-simulation does NOT match the saved log "
                  "(engine changed since save, or the file was edited)")


def run(deck1: str, deck2: str, games: int, agent: str, seed: int,
        mirror: bool, pool: str, iters: int = 120) -> dict:
    db = CardDB.from_pool(pool)
    load_deck(db, deck1)            # validate names up front (raises with a helpful msg)
    load_deck(db, deck2)

    d1_wins = d2_wins = ties = 0
    for i in range(games):
        s = seed + i
        # mirror: on odd games deck2 takes seat 0 (goes first) so neither deck keeps
        # the first-turn edge. Track wins by DECK identity, not seat.
        swap = mirror and (i % 2 == 1)
        name_a, name_b = (deck2, deck1) if swap else (deck1, deck2)
        deck_a, deck_b = load_deck(db, name_a), load_deck(db, name_b)
        rng_a, rng_b = random.Random(s), random.Random(s + 1_000_000)
        st = play_game(deck_a, deck_b, _make_agent(agent, rng_a, iters),
                       _make_agent(agent, rng_b, iters), seed=s, db=db)
        if st.winner is None:
            ties += 1
        else:
            winner_name = (name_a, name_b)[st.winner]
            if winner_name == deck1:
                d1_wins += 1
            else:
                d2_wins += 1
    return {"d1_wins": d1_wins, "d2_wins": d2_wins, "ties": ties}


def round_robin(decks: list[str], games: int, agent: str, seed: int, pool: str,
                iters: int = 120) -> dict:
    """Play every deck against every other deck and return a win-rate matrix.

    matrix[a][b] = a's win % vs b (decided games only). overall[a] = a's mean win %
    across all opponents — a meta tier ranking. Deterministic by `seed`."""
    n = len(decks)
    matrix = {a: {b: None for b in decks} for a in decks}
    for i in range(n):
        for j in range(i + 1, n):
            a, b = decks[i], decks[j]
            r = run(a, b, games, agent, seed, mirror=True, pool=pool, iters=iters)
            decided = r["d1_wins"] + r["d2_wins"]
            a_pct = 100 * r["d1_wins"] / decided if decided else 50.0
            matrix[a][b] = a_pct
            matrix[b][a] = 100 - a_pct
    overall = {a: (sum(v for v in matrix[a].values() if v is not None)
                   / max(1, n - 1)) for a in decks}
    return {"matrix": matrix, "overall": overall, "decks": decks}


def print_round_robin(res: dict, games: int, agent: str, seed: int, elo: dict) -> None:
    decks, matrix, overall = res["decks"], res["matrix"], res["overall"]
    w = max(len(d) for d in decks)
    pairs = len(decks) * (len(decks) - 1) // 2
    print(f"\nRound-robin — {len(decks)} decks, {pairs} matchups × {games} games "
          f"({agent}, mirrored seats, seed {seed})")
    print("Cell = row deck's win % vs column deck.\n")
    header = " " * (w + 2) + "".join(f"{d[:8]:>9}" for d in decks) + f"{'OVERALL':>10}"
    print(header)
    for a in decks:
        row = f"{a:<{w}}  "
        for b in decks:
            row += "      —  " if a == b else f"{matrix[a][b]:>8.0f}%"
        row += f"{overall[a]:>9.1f}%"
        print(row)
    print("\nTier ranking (Elo from win rates — rewards beating strong decks):")
    for rank, (a, r) in enumerate(sorted(elo.items(), key=lambda kv: -kv[1]), 1):
        print(f"  {rank:>2}. {a:<{w}}  Elo {r:<5}  ({overall[a]:.1f}% overall)")


def _export_matrix(res: dict, elo: dict, path: str, agent: str, games: int) -> None:
    """Write the round-robin matrix to a .csv or .html file (format inferred by extension)."""
    decks, matrix, overall = res["decks"], res["matrix"], res["overall"]
    if path.lower().endswith(".html") or path.lower().endswith(".htm"):
        title = f"Deck meta matrix ({agent}, {games} games/pair)"
        content = matrix_to_html(decks, matrix, overall, elo, title=title)
    else:
        content = matrix_to_csv(decks, matrix, overall, elo)
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\nExported matrix -> {path}")


def who_would_win_cmd(args) -> None:
    """'Who would win?' — a quick, friendly single-matchup readout (no jargon)."""
    d1, d2 = args.who_would_win
    games = args.games if args.games != 1000 else 200
    try:
        r = run(d1, d2, games, args.agent, args.seed, mirror=True, pool=args.pool,
                iters=args.iters if args.iters else 120)
    except KeyError as e:
        print(e)
        return
    print()
    print(who_would_win(d1, d2, r["d1_wins"], r["d2_wins"], r["ties"], games))


def import_tcglive(args) -> None:
    """Read a TCG Live deck export (stdin or --from-file), match it against the pool,
    print a summary + legality, and save it to decks/imported/<name>.json."""
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            text = f.read()
    else:
        if sys.stdin.isatty():
            print("Paste your Pokémon TCG Live deck export, then press Ctrl-D:\n")
        text = sys.stdin.read()
    if not text.strip():
        print("No deck list provided.")
        return

    db = CardDB.from_pool(args.pool)
    res = import_deck(text, db)
    name = args.name or "imported_deck"
    print(format_summary(res, name))

    # Legality check when every card resolved (4-copy rule, 1 ACE SPEC, 60 cards).
    if res.recipe and not res.missing:
        from src.engine.legality import validate_deck
        violations = validate_deck(db, res.recipe)
        print("  Legal ✓ (60 cards, copy + ACE SPEC rules OK)" if not violations
              else "  Legality: " + "; ".join(violations))

    path = save_deck(res, name)
    print(f"\nSaved -> {path}")
    if res.missing:
        print("  (Missing cards are recorded in the file; fill them in or pick legal "
              "substitutes before playing.)")


def main():
    ap = argparse.ArgumentParser(description="Run N games between two decks; report win rates.")
    ap.add_argument("--deck1", help="first deck name (see --list)")
    ap.add_argument("--deck2", help="second deck name (see --list)")
    ap.add_argument("--games", type=int, default=1000, help="number of games (default 1000)")
    ap.add_argument("--agent", choices=["greedy", "random", "mcts"], default="greedy",
                    help="agent piloting both decks (default greedy; mcts is far slower "
                         "but pilots combo/setup decks much more fairly)")
    ap.add_argument("--iters", type=int, default=0,
                    help="MCTS iterations (default 120 for single matchups, 50 for "
                         "--round-robin); higher = stronger + slower")
    ap.add_argument("--seed", type=int, default=0, help="base RNG seed (deterministic)")
    ap.add_argument("--no-mirror", action="store_true",
                    help="don't mirror seats (deck1 always goes first)")
    ap.add_argument("--pool", default="data/standard_pool.json")
    ap.add_argument("--list", action="store_true", help="list available decks and exit")
    ap.add_argument("--save-game", metavar="GAME_ID",
                    help="play ONE game (--deck1/--deck2/--agent/--seed) and save it to "
                         f"{SAVE_DIR}/<GAME_ID>.json")
    ap.add_argument("--replay", metavar="PATH",
                    help="load a saved game JSON and print it step by step")
    ap.add_argument("--round-robin", action="store_true",
                    help="play every deck vs every deck; print a win-rate matrix + Elo ranking")
    ap.add_argument("--export", metavar="PATH",
                    help="with --round-robin: write the matrix to a .csv or .html file")
    ap.add_argument("--who-would-win", nargs=2, metavar=("DECK1", "DECK2"),
                    help="fun, plain-language readout of who wins between two decks")
    ap.add_argument("--import-deck", action="store_true",
                    help="import a pasted Pokémon TCG Live deck export (reads stdin)")
    ap.add_argument("--from-file", metavar="PATH",
                    help="with --import-deck: read the deck list from a file instead of stdin")
    ap.add_argument("--name", metavar="NAME", help="name for an imported deck")
    args = ap.parse_args()

    # --- fun mode: who would win between two decks? ---
    if args.who_would_win:
        who_would_win_cmd(args)
        return

    # --- import mode: parse a TCG Live deck export into the engine's recipe ---
    if args.import_deck:
        import_tcglive(args)
        return

    # --- replay mode: load and print a saved battle ---
    if args.replay:
        replay_game(args.replay, args.pool)
        return

    # --- round-robin mode: the whole meta at a glance ---
    if args.round_robin:
        decks = sorted(DECKS)
        pairs = len(decks) * (len(decks) - 1) // 2
        if args.agent == "mcts":
            # MCTS is the fairer pilot for combo/setup decks (greedy over-rates simple
            # aggro by ~14pt — see README "Reading the matrix"). It's much slower, so
            # use a lighter default game/iter count for the full sweep.
            games = args.games if args.games != 1000 else 24
            iters = args.iters if args.iters else 50
            print(f"(MCTS round-robin: {pairs} matchups × {games} games at {iters} iters — "
                  f"slow but pilots combo decks fairly. Lower --games/--iters for speed.)")
        else:
            games = args.games if args.games != 1000 else 200
            iters = args.iters if args.iters else 120
        res = round_robin(decks, games, args.agent, args.seed, args.pool, iters=iters)
        elo = compute_elo(decks, res["matrix"])
        print_round_robin(res, games, args.agent, args.seed, elo)
        if args.export:
            _export_matrix(res, elo, args.export, args.agent, games)
        return

    # --- save mode: play one game (fixed orientation) and persist it ---
    if args.save_game:
        if not (args.deck1 and args.deck2):
            print("--save-game needs --deck1 and --deck2.")
            return
        try:
            save_game(args.deck1, args.deck2, args.agent, args.seed, args.save_game, args.pool)
        except KeyError as e:
            print(e)
        return

    if args.list or not (args.deck1 and args.deck2):
        print("Available decks:")
        for name in sorted(DECKS):
            print(f"  {name}")
        if not args.list:
            print("\nUsage: python3 cli.py --deck1 <name> --deck2 <name> --games 5000")
        return

    t0 = time.time()
    r = run(args.deck1, args.deck2, args.games, args.agent, args.seed,
            mirror=not args.no_mirror, pool=args.pool,
            iters=args.iters if args.iters else 120)
    dt = time.time() - t0
    n = args.games
    seats = "deck1 first" if args.no_mirror else "mirrored seats"
    print(f"\n{args.deck1} vs {args.deck2} — {n} games ({args.agent}, {seats}, seed {args.seed})")
    print(f"  {args.deck1:<16} {r['d1_wins']:>6}  {r['d1_wins'] / n:6.1%}")
    print(f"  {args.deck2:<16} {r['d2_wins']:>6}  {r['d2_wins'] / n:6.1%}")
    print(f"  {'ties':<16} {r['ties']:>6}  {r['ties'] / n:6.1%}")
    print(f"  {n / dt:,.0f} games/sec  ({dt:.1f}s, 0 tokens)")


if __name__ == "__main__":
    main()
