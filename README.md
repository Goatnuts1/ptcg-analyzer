# ptcg-analyzer

A Pokémon TCG deck analyzer. The long-term goal is an all-day, token-cheap
simulator that runs game scenarios to tune decks and find edges. This repo
currently contains **the data layer** — the foundation everything else reads from.

## Architecture (the one rule)

The LLM is **not** in the game loop. A deterministic engine plays the games
(zero tokens, pure CPU). The model only authors card scripts, self-heals on
errors, and synthesizes results. The engine is always the source of truth.

```
  [Card DB]  ->  fetch_standard_pool.py  ->  data/standard_pool.json
                                                  |
                                                  v
                              (next) deterministic engine + agents
                                                  |
                                                  v
                              (later) LLM heal / synthesize / online review
```

## What's built

| Stage | Component | Status |
|-------|-----------|--------|
| Data  | `src/fetch_standard_pool.py` — pull + filter Standard-legal cards | ✅ working |
| Data  | `tests/test_pool.py` — invariant checks on the pool | ✅ working |
| Engine | card schema + state machine | ⏳ next |
| Agents | heuristic policy, then MCTS | ◻ planned |
| LLM   | self-healing card scripts, result synthesis | ◻ planned |

## Quick start

```bash
python3 src/fetch_standard_pool.py --out data/standard_pool.json   # build pool
python3 tests/test_pool.py                                          # validate it
```

Last build: **1,273 unique Standard-legal cards** (marks H / I / J,
2026 season). Re-run the fetch whenever a new set releases.

## Data source

Official dump: `PokemonTCG/pokemon-tcg-data` (no API key, works offline after
first pull). Live API alternative documented at the bottom of the fetch script.

## When the format rotates

Change one line in `src/fetch_standard_pool.py`:
```python
LEGAL_MARKS = {"H", "I", "J"}   # update to the new legal marks, re-run fetch + test
```
The test's size bounds may also need a nudge; everything else is automatic.
