# ptcg-analyzer — Project Directions & Routine Audit Guide

Last updated: 2026-08-24. Owner: Goatest1 (TCG Live handle).
Repo: https://github.com/Goatnuts1/ptcg-analyzer · Local: `~/dev/ptcg-analyzer`
Working branch: `feature/multihop-mcts` (ladder entries land here); PRs merge to `main`.

## What this project is

A deterministic Pokémon TCG deck simulator. The LLM is **never in the game loop** —
games are played by a CPU-only engine; the model only authors card scripts, heals
broken ones, reads aggregate stats, and writes reports. Every model output is
validated against the engine before it's trusted.

---

## Directory map

| Path | What lives there | Audit interest |
|---|---|---|
| `CLAUDE.md` | The project's ground truth: architecture rules, calibration doctrine, known limitations | **Read first.** Every claim elsewhere defers to this |
| `cli.py` | Entry point: matchups, round-robins, imports, replay, `--serve` web UI, `--futures` | Smoke-test target |
| `src/engine/` | The deterministic engine: `game.py`, `state.py`, `effects.py` (~176 card scripts), `agents.py`, `mcts.py`, `decks.py`, `legality.py` | Core correctness |
| `src/importers/` | `tcglive.py` (deck paste import), `tcglive_log.py` (battle-log parser, 100% line coverage on the live corpus) | External ground truth pipeline |
| `src/analysis/` | `futures.py` (rotation/trend scoring), ratings, reports, gap check | Feeds the meta scan |
| `src/learn/`, `src/optimizer/` + `optimize.py`, `OPTIMIZER_HANDBOOK.md` | Neural self-play experiments and the evolutionary decklist optimizer (outer loops; not part of the validated core) | Lower priority; results here are exploratory |
| `src/web/server.py` | Zero-dependency local web UI (`python3 cli.py --serve`) | Convenience layer |
| `data/` | `standard_pool.json` (1,305 cards; **gitignored, regenerated** by `src/fetch_standard_pool.py`) + `manual_cards.json` (tracked hand-added supplement) | Pool gaps live here |
| `decks/imported/` | Engine-format recipes written by the deck importer | User content |
| `tests/` | **103 standalone scripts** — run each as `python3 tests/test_*.py`; **pytest breaks on them by design** (module-scope exits) | The audit's backbone |
| `docs/` | All reports and logs (see below) | The paper trail |
| `saved_games/`, `optimizer_runs/`, `viz/` | Reproducible game saves, optimizer output, visualization scratch | Spot-check only |

## The documents that matter, in reading order

1. `CLAUDE.md` — architecture rules + the calibration doctrine (**read before quoting any win rate**).
2. `docs/META_GAUNTLET_2026-08.md` — the honest calibration failure: sim ~63% vs real 49.51% for the house deck. The most important number in the project.
3. `docs/BEST_DECK_2026-08.md` + `docs/matrix_2026-08_mcts2.json` — the 159-pairing strength matrix (mcts2@60, n=60, seed 2026) and its caveats.
4. `docs/LADDER_LOG.md` — every real TCG Live game, analyzed; the running ledger (38–31 as of this writing) and the Shaymin-variant experiment.
5. `docs/TCGLIVE_LOG_FIDELITY.md` — Findings 1–5 from parsing the real-game corpus (pool set-gaps, print ambiguity, client owner-mislabel bug, attack-name mismatch, invisible passive abilities).
6. `docs/META_SCAN_2026-08-*.md` + `docs/FUTURES_*.txt` — the twice-weekly scan output (Mon+Thu cloud routine opens PRs).
7. `docs/VALIDATION_RESULT.md` — card fidelity vs agent-strength separation (its "mcts2 not built" wording is stale; its verdict is not).

---

## Routine audit checklist

Run from the repo root. Expected results are stated so drift is visible.

**1. Test suite — all 103 must pass.** They are standalone scripts, NOT pytest:
```bash
for t in tests/test_*.py; do python3 "$t" > /dev/null 2>&1 || echo "FAIL: $t"; done; echo done
```
Expected: no FAIL lines. Any failure in `test_determinism.py` invalidates every
recorded win rate — treat as a stop-the-line event.

**2. Determinism spot check** (same seed ⇒ identical result):
```bash
python3 cli.py --deck1 dragapult --deck2 charizard_xy --games 20 --seed 42
python3 cli.py --deck1 dragapult --deck2 charizard_xy --games 20 --seed 42
```
Expected: byte-identical win counts across the two runs.

**3. Pool freshness + supplement integrity:**
```bash
python3 src/fetch_standard_pool.py   # regenerates data/standard_pool.json
python3 -c "import json; print(len(json.load(open('data/standard_pool.json'))))"
```
Expected: ≥1,305 cards; `data/manual_cards.json` entries survive the merge
(spot-check one, e.g. `Shaymin (DRI)`). Known open pool gaps (candidates for the
next `manual_cards.json` additions): Growing Grass Energy, Mega Skarmory ex,
Gengar (Mind Jack print).

**4. Registry sanity:**
```bash
python3 cli.py --list
```
Expected: all registered decks load; includes the two ladder-provenance lists
(`slowking_annihilape`, `mega_excadrill_shaymin`).

**5. Battle-log parser regression:**
```bash
python3 tests/test_tcglive_log.py
```
Expected: ALL PASS. (The raw ladder-log corpus itself is **never in the repo** —
opponents' handles are private; only reports and reconstructions are committed.)

**6. Automation health:** confirm the Mon/Thu meta-scan routine fired (a fresh
draft PR titled `meta-scan: <date>` on GitHub) and that draft PRs aren't piling
up unreviewed:
```bash
gh pr list --state open
```

**7. Docs-vs-reality drift:** the ledger line at the tail of `docs/LADDER_LOG.md`
must match the entry count; any sim number quoted in a new doc must carry its
pilot/calibration caveat (CLAUDE.md doctrine).

## Standing rules an audit should verify are still being followed

- **Determinism is a tested invariant** — never merged around.
- **No card text is ever invented**; pool/limitlesstcg is the authority, and
  disagreements are recorded in `TCGLIVE_LOG_FIDELITY.md`, not silently "fixed".
- **Win rates are always caveated**: greedy numbers are floors for combo decks,
  the matrix over-rates aggro, and the three known-bogus cells are flagged in
  `META_GAUNTLET_2026-08.md`.
- **Privacy**: raw battle logs (real ladder handles) stay out of git.
- Frozen defaults: `MCTSAgent` defaults are frozen (recorded numbers depend on
  them); matrix protocol is mcts2@60, n=60, seed 2026, mirrored seats.
