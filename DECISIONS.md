# DECISIONS

Running log of engineering decisions. Format: decision · alternatives · why · risk · date.

## 2026-11-04 — main health fixes (`fix/main-health`)

1. **`cli.py --list` crash: drop the function-local `from src.engine.decks import DECKS`
   inside the `--futures` branch.** The local import made `DECKS` a local name for all of
   `main()`, so every non-futures path that read `DECKS` raised `UnboundLocalError`.
   *Alternatives:* `global DECKS`; rename the local. *Why:* the module already imports
   `DECKS` at top level; the local import was redundant. Same fix as on
   `feature/multihop-mcts`. *Risk:* none found.
2. **`test_toucannon_deck.py`: widen the liveness seed window 40 → 120.** The rare
   Area Zero Underdepths Bench-shrink line stopped firing in the first 40 greedy games
   after a pool rebuild; the clause is unit-tested elsewhere. *Alternatives:* force the
   line with a constructed state. *Why:* matches the branch fix (73e0382), keeps the
   test a liveness check. *Risk:* liveness tests depend on the pool, which is built
   from upstream data at build time, so any future rebuild can shift trajectories again.
3. **torch-dependent tests (`test_arena.py`, `test_train.py`) skip cleanly when
   torch/numpy are absent** — `pytest.importorskip` under pytest, `SKIP` + exit 0 as a
   script (the suite is script-style, not pytest). *Why:* the core engine is stdlib-only;
   the learning stack is optional. *Risk:* a CI without torch never exercises those tests;
   run them from the Trainer venv.
4. **Added `tests/run_all.py`**, a stdlib runner reporting PASS/SKIP/FAIL. *Why:* no
   single command ran the suite. *Risk:* none.

## RISKS
- `data/standard_pool.json` is gitignored and rebuilt from upstream data; test results
  and sim trajectories are reproducible only for the same pool build.
