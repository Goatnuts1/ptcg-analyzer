# ptcg-analyzer

A Pokémon TCG deck analyzer: an all-day, token-cheap simulator that plays game
scenarios to tune decks and find edges. A deterministic engine plays full legal
games on CPU only — **zero tokens, zero LLM in the game loop.**

## Architecture (the one rule)

The LLM is **not** in the game loop. A deterministic engine plays the games (zero
tokens, pure CPU). The model only authors card scripts from card text, self-heals
when the engine throws, and synthesizes aggregate results. The engine is always
the source of truth, and every effect ships with a test asserting it matches the
printed card text.

```
  [Card DB]  ->  fetch_standard_pool.py  ->  data/standard_pool.json
                                                  |
                                                  v
                          deterministic engine + agents  ->  cli.py (win rates,
                                                  |             save / replay)
                                                  v
                          (later) LLM heal / synthesize / online review
```

## Quick start

You need Python 3. No third-party packages are required to run the simulator.

**Step 1 — build the card pool** (run once):

```bash
python3 src/fetch_standard_pool.py --out data/standard_pool.json
```

**Step 2 — see which decks are available:**

```bash
python3 cli.py --list
```

**Step 3 — run a matchup** (any two deck names from Step 2):

```bash
python3 cli.py --deck1 dragapult --deck2 charizard_xy --games 1000
```

This prints each deck's win rate. Use `--games 5000` for a tighter number.

**Step 4 — see the whole meta at once** (every deck vs every deck):

```bash
python3 cli.py --round-robin --games 200
```

This prints a win-rate matrix and a tier ranking across all decks.

**Step 5 (optional) — save a single battle and replay it:**

```bash
python3 cli.py --deck1 dragapult --deck2 raging_bolt --seed 42 --save-game myrun
python3 cli.py --replay saved_games/myrun.json
```

### Good to know

- Matchups mirror seats (so neither deck gets the going-first advantage).
- Everything is **deterministic**: the same `--seed` always gives the same result.
- `--agent` chooses the player: `greedy` (default, fast), `random`, or `mcts`
  (stronger but much slower).
- A saved game records the full battle; replaying it re-runs from the seed and
  confirms it reproduces exactly.

## What's built

| Area | Component | Status |
|------|-----------|--------|
| Data | `src/fetch_standard_pool.py` + `data/manual_cards.json` supplement | ✅ 1,276 cards (marks H/I/J) |
| Engine | `src/engine/` — Card model, state, rules engine, agents, runner | ✅ full legal games |
| Engine | Stadiums + bench chokepoints (Battle Cage / Tera), Special Conditions, Tools, Special Energy, MEGA 3-prize, self-KO prizes, ability suppression | ✅ implemented + tested |
| Determinism | same seed = byte-identical game (in-process **and** cross-process) | ✅ `tests/test_determinism.py` |
| Effects | `src/engine/effects.py` — primitives + registries, **~78 cards** each tested vs card text | ✅ working |
| Decks | `dragapult`, `charizard_xy` (tournament lists) + `raging_bolt`, `gardevoir`, `colorless`, `fire`, `fighting`, `dark`, `metal`, `water` (10 total) | ✅ `DECKS` registry |
| Agents | greedy (+ general fallbacks), EvalAgent (1-ply), eval-MCTS (multi-turn negamax) | ✅ working |
| CLI | `cli.py` — matchups, `--round-robin` (win-rate matrix), `--save-game`, `--replay`, `--list` | ✅ working |
| Validation | win rate vs published Limitless matchup | ✅ run — see findings below |
| LLM | self-healing card scripts, result synthesis | ◻ planned |

Run the tests (each file is a standalone script, e.g.):

```bash
python3 tests/test_new_cards.py
python3 tests/test_determinism.py
```

Full test suite: **24 suites green.**

## Cards implemented (~78, each unit-tested)

- **Dragapult ex** line (Stage 2 spread): Phantom Dive, Recon Directive, + the
  Dusknoir/Dusclops Cursed-Blast KO engine, Munkidori, Fezandipiti, Budew, etc.
- **Mega Charizard X / Y ex** (Stage 2 MEGA, gives up **3** prizes): Inferno X,
  Explosion Y, the Dunsparce/Oricorio/Fan Rotom support.
- **Raging Bolt ex / Teal Mask Ogerpon ex** (Basic, energy-scaling): Bellowing
  Thunder, Burst Roar, Teal Dance, Myriad Leaf Shower.
- **Mega Gardevoir ex** line (Psychic): Ralts (Collect), Kirlia (Call Sign), Mega
  Gardevoir ex (Overflowing Wishes accel + Mega Symphonia scaling), plus Mega
  Diancie ex, Iron Crown ex, Latias ex.
- **Colorless toolbox:** Lugia ex, Snorlax ex, Cyclizar ex, Mega Kangaskhan ex,
  Terapagos ex.
- **Fire:** Reshiram ex, Volcanion ex, Ethan's Ho-Oh ex. **Lightning:** Tapu Koko ex.
- **Fighting:** Mega Lucario ex (Aura Jab/Mega Brave), Regirock ex, Iron Boulder ex,
  Koraidon ex. **Dark:** Mega Absol ex. **Metal:** Mega Mawile ex, Hop's Zacian ex.
  **Water:** Dondozo ex, Lapras ex.
- **Trainer / staple suite:** Rare Candy, Buddy-Buddy Poffin, Ultra Ball, Poké
  Pad, Boss's Orders, Switch, Night Stretcher, Crushing Hammer, Lillie's
  Determination, Judge, Hilda, Dawn, Crispin, plus the core-stabilization staples
  (Carmine, Lacey, Kofu, Cyrano, Colress's Tenacity, Lana's Aid, Drayton, Hassel,
  Poké Ball, Master Ball, Dusk Ball, Pokégear 3.0, Energy Switch, Energy Recycler,
  Sacred Ash, Pokémon Catcher, Klefki).

## Agents (`agents.py`, `mcts.py`)

- **Greedy** — hand-written priorities (evolve, develop, lethal, consistency
  trainers, attack), with general Item/Supporter fallbacks so no implemented
  Trainer is ever inert. Fast; the default.
- **EvalAgent** — 1-ply lookahead over `position_value` (effect-aware: prizes,
  bench pressure, disruption, development).
- **MCTS** — determinized UCT (PIMC for hidden info). Supports a `position_value`
  leaf eval (`rollout="eval"`) and a multi-turn negamax tree across the turn
  boundary (`search_plies=N`). Beats greedy ~61% (single-turn).

## Validation status (`docs/VALIDATION_RESULT.md`)

Card implementation is **complete** — both tournament lists are fully faithful.
The honest result: the sim rates Dragapult vs Mega Charizard ~53–59%, while the
published Limitless number is ~84%. This is **not** a card/engine-fidelity failure
(cards are tested) — it's **agent/policy strength**: greedy and single-turn
eval-MCTS don't yet express Dragapult's multi-turn spread+disruption plan.

### Known limitations (read win rates accordingly)

- **Greedy mispilots complex decks.** It ranks attacks by printed damage and can't
  sequence multi-step plans, so e.g. `raging_bolt` underperforms and games often
  end by self-deck-out, not prizes. The cards are correct; the piloting is weak.
  Use `--agent mcts` for stronger play, or treat greedy win rates as a fast,
  approximate signal — not optimal play.
- Full multi-turn ISMCTS / hidden-hand-aware evaluation are not built yet.

## Data source

Official dump: `PokemonTCG/pokemon-tcg-data` (no API key, works offline after the
first pull). A small hand-maintained `data/manual_cards.json` supplements newer
Mega-era cards the upstream dump hasn't published; the fetch script merges it
(deduped by name) so a re-fetch reproduces all 1,276 cards deterministically.

## When the format rotates

Rotation lives in one place — `STANDARD_LEGAL_MARKS` in `src/engine/legality.py`
(imported by the fetch script). Update the set, re-run the fetch, re-run the tests.
