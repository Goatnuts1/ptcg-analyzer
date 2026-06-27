"""generate.py — CLI: fill the replay buffer from parallel self-play.

  python3 -m src.learn.generate --games 5000 --workers 8 --decks all

Spreads games over NUM_WORKERS processes (default 8 — the M5 Air is fanless, so we
leave headroom; plan §7a). Each worker writes its own atomic gzip shards into the hot
buffer (no cross-process write contention); the parent then flushes sealed shards out to
the T7 archive (skipped without error if the drive is unplugged) and prints buffer stats.

Determinism: a base seed expands to per-game seeds, so a run is fully reproducible.
"""
from __future__ import annotations

import argparse
import itertools
import random
import time
from concurrent.futures import ProcessPoolExecutor

from src.engine.cards import CardDB

from . import buffer, config
from .buffer import ShardWriter
from .encoder import Vocab
from .selfplay import all_deck_ids, generate_batch


def _worker(args) -> tuple[int, int]:
    """One worker: generate games for its assigned (pairing, seeds) jobs; write shards.

    Returns (games, records). Re-loads the pool per process (CardDB isn't shared across
    process boundaries); cheap relative to the games it then plays.
    """
    wid, pool_path, jobs, agent_kind = args
    db = CardDB.from_pool(pool_path)
    vocab = Vocab.from_db(db)
    writer = ShardWriter(config.BUFFER_DIR, tag=f"w{wid:02d}")
    games = records = 0
    for deck_a, deck_b, seeds in jobs:
        recs = generate_batch(deck_a, deck_b, seeds, db, vocab, agent_kind)
        for r in recs:
            writer.write(r)
        games += len(seeds)
        records += len(recs)
    writer.close()
    return games, records


def _plan_jobs(deck_ids: list[str], n_games: int, base_seed: int, n_workers: int):
    """Build round-robin (deck_a, deck_b, [seeds]) jobs, one bucket per worker."""
    pairs = [(a, b) for i, a in enumerate(deck_ids) for b in deck_ids[i:]]  # incl. mirror
    rng = random.Random(base_seed)
    # assign each game a (pair, seed); round-robin pairs so the meta is covered evenly
    games = []
    pair_cycle = itertools.cycle(pairs)
    for _ in range(n_games):
        a, b = next(pair_cycle)
        games.append((a, b, rng.randint(0, 2**31 - 1)))
    # group by pair, then split into worker buckets
    buckets: list[list] = [[] for _ in range(n_workers)]
    for idx, (a, b, s) in enumerate(games):
        buckets[idx % n_workers].append((a, b, [s]))
    return buckets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=2000, help="total self-play games")
    ap.add_argument("--workers", type=int, default=config.NUM_WORKERS)
    ap.add_argument("--agent", default="greedy", choices=["greedy", "random", "mcts"])
    ap.add_argument("--decks", default="all", help="'all' or comma-separated deck ids")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--pool", default=config.DEFAULT_POOL)
    ap.add_argument("--no-flush", action="store_true", help="skip archiving to the T7")
    args = ap.parse_args()

    config.ensure_dirs()
    deck_ids = all_deck_ids() if args.decks == "all" else args.decks.split(",")
    buckets = _plan_jobs(deck_ids, args.games, args.seed, args.workers)

    print(f"self-play: {args.games} games · {args.workers} workers · agent={args.agent} · "
          f"{len(deck_ids)} decks")
    print(f"  hot buffer : {config.BUFFER_DIR}")
    print(f"  archive    : {config.ARCHIVE_DIR}  ({'mounted' if config.archive_available() else 'NOT mounted'})")

    t0 = time.time()
    work = [(w, args.pool, buckets[w], args.agent) for w in range(args.workers)]
    total_games = total_records = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for g, r in ex.map(_worker, work):
            total_games += g
            total_records += r
    dt = time.time() - t0

    print(f"generated {total_games} games -> {total_records} records in {dt:.1f}s "
          f"({total_games/max(dt,1e-9):.0f} games/s, {total_records/max(total_games,1):.1f} rec/game)")

    if not args.no_flush:
        moved, ok = buffer.flush_to_archive()
        print(f"archive flush: {'moved '+str(moved)+' shards to T7' if ok else 'T7 not mounted — kept hot'}")

    st = buffer.buffer_stats()
    print(f"buffer: {st['hot_shards']} hot shards ({st['hot_bytes']/1e6:.1f} MB) · "
          f"{st['archive_shards']} archived ({st['archive_bytes']/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
