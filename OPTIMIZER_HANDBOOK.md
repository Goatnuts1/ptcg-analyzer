# Deck Optimizer — Handbook

An evolutionary outer loop that mutates decklists and scores each one by playing
simulated games on the deterministic engine. It hill-climbs toward higher win
rates against a chosen set of opponent decks.

## ⚠️ Read this first: what the numbers do and do not mean

**The optimizer's win-rates rest on the engine in `src/engine/`, and that engine
is NOT validated to tournament-grade fidelity.** Our own validation run put the
Dragapult-mirror sim at ~58% against a published ~84% — a real gap attributed to
agent strength, not card fidelity. On top of that, the optimizer runs MCTS at a
**reduced iteration budget** (`OPTIMIZER_MCTS_ITERATIONS = 40`, vs the engine
default 160) so a full evolutionary run finishes in minutes, not days. The agent
making the in-game decisions is therefore *weaker* than the full search.

Consequences:

- A reported win rate is **relative signal between candidate decks under a fixed,
  imperfect model** — not a prediction of real-world performance.
- Do **not** present optimizer output as "deck X wins Y% in Standard."
- Improvements found here are hypotheses to be checked against the validation
  pipeline and, ultimately, real results — not conclusions.

This caveat is repeated in `print_summary()`, in every saved JSON (`"caveat"`),
and in the package `__init__`. Keep it there.

## Architecture

```
optimize.py                 CLI entrypoint
src/optimizer/
  types.py                  Decklist, OptimizationTarget, EvalResult (+ a data-
                            container OptimizerReport, distinct from report.py's)
  core.py                   DeckOptimizer.optimize() — the generational loop
  deck_generator.py         DeckMutator — population + 1–4 random mutations,
                            with a legality-repair pass (copy/ACE-SPEC/mark caps)
  evaluator.py              evaluate_deck() — plays games, mirrors seats,
                            rejects illegal decks (0% + recorded errors)
  decklists.py              base decks, expanded from the engine's validated
                            TOURNAMENT_* recipes (pool-valid by construction)
  meta.py                   get_current_meta_targets() — the opponent sets
  report.py                 OptimizerReport — print_summary() + save_json()
tests/test_optimizer.py     smoke + integration tests (fast, MCTS off)
```

The loop (per generation): mutate the current best into a population → evaluate
each candidate → keep the highest win-rate → repeat.

## Decklist representation

Internally a deck is a **flat list of 60 card names with multiplicity**
(`["Dreepy", "Dreepy", ...]`). The evaluator expands names to engine `Card`
objects via `db.get()` and collapses to `(name, count)` recipes for legality
checks. Every name must exist in `data/standard_pool.json` — there is no
free-text card creation.

## Legality

`evaluate_deck` calls `validate_deck` and **scores any illegal deck 0%** with the
violations in `metadata["errors"]`, so selection pressure rejects them. The
mutator additionally repairs decks after mutating (caps copies at 4 except basic
energy, ≤1 ACE SPEC, legal marks only), so the vast majority of candidates are
legal before they're ever scored. Format = Standard marks `{H, I, J}`.

## Running

```bash
# Fast greedy sweep (recommended first pass — no MCTS, seconds-to-minutes)
python3 optimize.py --deck dragapult --target wildcard --fast --generations 4 --population 8

# MCTS-scored run against the current meta (slower — minutes-to-tens-of-minutes)
python3 optimize.py --deck charizard --target current-meta --generations 6 --population 10
```

| Flag | Meaning |
|---|---|
| `--deck` | `dragapult` \| `charizard` — starting list (from `decklists.py`) |
| `--target` | `current-meta` \| `mirror` \| `wildcard` — opponent set (`meta.py`) |
| `--generations` | how many evolution rounds |
| `--population` | candidates evaluated per generation |
| `--fast` | force GreedyAgent (no MCTS) — much faster, weaker play |
| `--output` | directory for the result JSON |

### Cost model

Per generation ≈ `num_games_per_matchup × population × len(opponent_decks)`
games. MCTS at 40 iterations runs a few games/sec; greedy runs hundreds/sec.
The `meta.py` targets ship with deliberately modest game counts — raise
`num_games_per_matchup` for tighter confidence intervals when you have the time.

## Tests

```bash
python3 tests/test_optimizer.py
```

Covers: sample decks are legal 60s; the mutator keeps ≥90% of mutations legal;
the evaluator runs, scores in `[0,1]`, and rejects illegal decks; and a tiny
end-to-end `optimize()` produces a 60-card final deck and a report. These prove
**wiring**, not card-game truth.

## Provenance

The original draft of this package was authored in a separate sandbox and bound
to an engine API that did not match this repo (wrong `play_game` signature,
name-list-vs-`Card` confusion, `MCTSAgent` import, non-pool card names, no
legality enforcement, multi-hour default game counts). It was rebuilt here
against the real `src/engine` API with those bugs fixed and the un-validated-
simulator caveat made load-bearing.
