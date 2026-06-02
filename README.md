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
| Data  | `src/fetch_standard_pool.py` — pull + filter, writes metadata sidecar | ✅ working |
| Data  | `tests/test_pool.py` — 9 invariant checks on the pool | ✅ working |
| Viz   | `viz/data_explorer.html` — card-data inspector + next-best-move demo | ✅ working |
| Engine | `src/engine/` — Card model, state, rules engine, agents, runner | ✅ v0 working |
| Engine | `tests/test_engine.py` — termination, prize, cost, agent-sanity checks | ✅ working |
| Effects | `src/engine/effects.py` — effect system + Dragapult line + Trainers | ✅ working |
| Effects | `tests/test_effects.py` — per-card effect validation (8 cards) | ✅ working |
| Agents | MCTS (replaces greedy heuristic) | ⏳ next |
| Validation | win rates vs published matchups | ◻ needs MCTS first |
| LLM   | self-healing card scripts, result synthesis | ◻ planned |

### Effect system (`effects.py`)

Hybrid design: reusable **primitives** + **registries** mapping a card's
attack/ability/Trainer to a hand-written effect. A `can_play` predicate gates
Trainer legality so the engine never offers a card that would do nothing.

Implemented + tested (8 cards):
- **Dragapult line:** Phantom Dive (200 + 6-counter bench spread), Recon
  Directive (dig 2 / take 1), plus enforced evolution timing.
- **Trainers:** Rare Candy (Basic→Stage 2 skip), Buddy-Buddy Poffin (fetch 2
  small Basics), Cheren (draw 3), Boss's Orders (gust a benched Pokémon up).

With the Trainer engine, the Dragapult deck functions: Rare Candy fires in ~28%
of greedy games and the fastest Phantom Dive is now **turn 3** (vs turn 7 before).

⚠️ **Win rates are still NOT trustworthy matchup numbers.** Current greedy-vs-greedy
has Dragapult at ~36% vs the fast Lightning fixture — but that reflects *weak
piloting* of a clunky Stage 2 deck, not the real matchup. A Stage 2 deck lives or
dies on sequencing, which a greedy agent can't do. Trustworthy percentages need
**MCTS** (next milestone), and each result validated against a published matchup.

**Validation rule:** no effect is trusted without a test asserting it matches the
printed card text exactly.

### Engine v0 — what works and what's stubbed

Run it: `python3 -m src.engine.run --games 1000` (≈2,000 games/sec, **zero tokens**).

**Faithful:** setup + mulligan, 6 prizes, coin-flip + first/second, turn loop,
draw, bench Basics, one energy/turn, evolution, retreat, attacks with base
damage, **typed energy-cost checking**, weakness (×2) / resistance, knockouts,
prize-taking, all three win conditions (prizes, no-Pokémon, deck-out).

**Stubbed (clean hooks, not yet real):** attack *effect text* (attacks do base
damage only), abilities, Trainer-card effects, special conditions
(poison/sleep/…), special-energy bonuses, variable `×`/`+` damage.

⚠️ **Win rates from v0 are NOT meaningful matchup numbers.** Effects are stubbed,
agents are weak, and the two decks are throwaway fixtures. The deliverable is a
*correct core loop*, proven by greedy beating random ~99%. Real percentages come
after effects + MCTS.

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
