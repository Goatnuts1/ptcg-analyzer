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
  types.py                  Decklist, OptimizationTarget, EvalResult
  core.py                   DeckOptimizer.optimize() — the generational loop
  deck_generator.py         DeckMutator — population + 1–4 random mutations,
                            with a legality-repair pass (copy/ACE-SPEC/mark caps)
  evaluator.py              evaluate_deck() — plays games, mirrors seats,
                            rejects illegal decks (0% + recorded errors)
  decklists.py              base decks, expanded from the engine DECKS registry
                            (pool-valid by construction)
  meta.py                   get_current_meta_targets() — the opponent sets
  report.py                 OptimizerReport — print_summary() + save_json()
  validation_runner.py      one-call driver for a meatier pass (NOT engine
                            validation — see its docstring)
tests/test_optimizer.py     smoke + integration tests (fast, MCTS off)
```

The loop (per generation): mutate the current best into a population → evaluate
each candidate → keep the highest win-rate → repeat.

`generate_population` keeps index 0 as the **unmutated incumbent**, and
`evaluate_deck` scores every candidate off the same fixed seed sequence, so the
incumbent is re-scored on exactly the games its challengers played. Two things
fall out of that and both are load-bearing:

- **Elitism is explicit.** A generation is only adopted if it *beats* the
  incumbent, so a run cannot drift sideways onto an equal-scoring mutant.
- **The baseline is free.** Generation 1's incumbent score IS the base deck's
  win rate, so every report carries `base_win_rate` and an `improvement` delta.
  Without it a final "62%" is unreadable — you can't tell an optimizer that
  found something from one that handed your list straight back. `print_summary`
  also prints the per-card diff against the base list, or says plainly that
  nothing changed.

## What the mutator is allowed to reach for

`DeckMutator.all_cards` is **not** the whole Standard pool — it is the union
of every recipe in the engine's `DECKS` registry, plus basic energy (~230 names
against a 1,300+ card pool). The pool is far wider than the set of cards whose
effects are actually implemented, and a card
with no registered effect is a blank in the sim: mutating toward the raw pool
just fills lists with vanilla bodies and reads that as a deck change. Widening
this set is the same work as implementing more effects, in that order.

Mutations: replace a random slot; swap in an ex/MEGA attacker (selected by
SUBTYPE, not by substring-matching the name); adjust one card's count up **or**
down; or bring in a card the list doesn't already play.

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
python3 optimize.py --deck mega_excadrill --target wildcard --fast --generations 4 --population 8

# MCTS-scored run against the current meta (slower — minutes-to-tens-of-minutes)
python3 optimize.py --deck dragapult_blaziken --target current-meta --generations 6 --population 10
```

| Flag | Meaning |
|---|---|
| `--deck` | registry starter (default `mega_excadrill`; also blaziken-pult, crustle, festival, grimmsnarl, fighting, dragapult, charizard) |
| `--target` | `current-meta` \| `mirror` \| `wildcard` — opponent set (`meta.py`) |
| `--generations` | how many evolution rounds |
| `--population` | candidates evaluated per generation |
| `--fast` | force GreedyAgent (no MCTS) — much faster, weaker play |
| `--output` | directory for the result JSON |

### Cost model

Per generation ≈ `num_games_per_matchup × population` games. MCTS at 40
iterations runs a few games/sec; greedy runs hundreds/sec.

`num_games_per_matchup` is the TOTAL per candidate: `evaluate_deck` **splits** it
across the opponent set (`num_games // len(opponents)`) rather than multiplying
by it. So adding an opponent does not lengthen the run — it thins the games
behind each matchup. The `current-meta` target's six opponents at 120 games mean
20 games per matchup, which is noisy; raise `num_games_per_matchup` rather than
trimming the field if you want tighter confidence.

## Tests

```bash
python3 tests/test_optimizer.py
```

Covers: sample decks are legal 60s; the mutator keeps ≥90% of mutations legal
and never introduces a card outside the implemented set; counts move in both
directions; the evaluator runs, scores in `[0,1]`, and rejects illegal decks; and
a tiny end-to-end `optimize()` produces a 60-card final deck plus a report whose
final win rate is never below its baseline. These prove **wiring**, not card-game
truth.

## Provenance

The original draft of this package was authored in a separate sandbox and bound
to an engine API that did not match this repo (wrong `play_game` signature,
name-list-vs-`Card` confusion, `MCTSAgent` import, non-pool card names, no
legality enforcement, multi-hour default game counts). It was rebuilt here
against the real `src/engine` API with those bugs fixed and the un-validated-
simulator caveat made load-bearing.
