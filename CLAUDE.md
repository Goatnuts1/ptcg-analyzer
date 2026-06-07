# CLAUDE.md — ptcg-analyzer

Context for Claude Code sessions in this project.

## What this is
A Pokémon TCG deck analyzer. End goal: a deterministic simulator that crunches
game scenarios all day to tune decks and surface edges. Token-cheap by design.

## The non-negotiable architectural rule
**The LLM is never in the game loop.** Games are played by a deterministic
engine (CPU only, zero tokens). The model's jobs are bounded:
1. author card scripts from card text,
2. self-heal: patch a card script when the engine throws on an interaction,
3. synthesize: read aggregate stats and propose deck changes,
4. escalate genuinely hard reasoning to a frontier model via API on a schedule.
Every model output is validated against the engine before it's trusted.

## Current state
- Data layer: done + tested. `data/standard_pool.json` = **1,276 cards** (marks
  H/I/J; 3 in the tracked `data/manual_cards.json` supplement, merged by the fetch
  script and deduped by name).
- Engine: done + tested. `src/engine/` plays full legal games, zero tokens. Core
  rules faithful incl. evolution timing, Stadiums + the two bench chokepoints
  (Battle Cage counters / Tera attack-damage), Special Conditions, Tools, Special
  Energy, MEGA 3-prize rule, self-KO prize awards, ability suppression (TRW).
- **Deterministic — a tested invariant.** Same seed = byte-identical game,
  in-process (greedy + MCTS) AND cross-process (hash-seed-independent). Guarded by
  `tests/test_determinism.py`. If this breaks, every win rate is worthless.
- Effect system: done + tested. `effects.py` = primitives + registries for attacks,
  abilities, Trainers, Tools, Special Energy. **~54 distinct cards implemented**,
  each asserted against its card text. Includes the two namesake archetype lines
  plus a draw/search/recovery staple suite.
- Decks (`decks.py`): two faithful tournament lists (`dragapult`, `charizard_xy`)
  and a third archetype (`raging_bolt`), in the `DECKS` registry; `load_deck(db,name)`.
- Agents (`agents.py`): RandomAgent, GreedyAgent (hand-written priorities + general
  Item/Supporter fallbacks so no implemented Trainer is ever inert), EvalAgent
  (1-ply over `position_value`). MCTS in `mcts.py` (see below).
- Validated: greedy beats random ~99%; MCTS beats greedy ~61%; effects fire in
  real games. Matchup-fidelity findings in `docs/VALIDATION_RESULT.md`.

## Effect system (`src/engine/effects.py`)
Hybrid: primitives + registries. Attack/ability registries keyed by
(card_name, move_name); Trainer registry keyed by card_name with a parallel
can_play predicate. Engine hooks: `_resolve_attack`, use_ability branch,
play_trainer branch. KO logic shared in `process_knockouts` (scans bench).
IMPORTANT: in play_trainer the card is popped from hand BEFORE the effect runs,
because effects mutate the hand (learned bug — index shift).

- MCTS agent: done + tested. `src/engine/mcts.py` = GameState.clone() +
  determinize() (PIMC, handles hidden info) + UCT. Now supports a `position_value`
  leaf evaluation (`rollout="eval"`, far cheaper than terminal rollouts) and a
  multi-turn negamax tree across the turn boundary (`search_plies=N`). Beats greedy
  ~61% (single-turn, greedy rollout). `tests/test_mcts*.py` check clone/determinize
  correctness, negamax sign handling, and strength.

## MCTS notes (`src/engine/mcts.py`)
- clone() shares immutable Card refs, copies mutable wrappers — keep it that way.
- determinize() conserves the exact card multiset and preserves the acting
  player's known info (own hand, public board/discard); reshuffles hidden zones.
- Tree is SINGLE-TURN (acting player's sequencing); rest is rolled out. Full
  multi-turn ISMCTS is a later upgrade.
- Actions are de-duplicated by semantic key (same card from different hand slots,
  same energy type to same target) so the iteration budget isn't wasted.

## Using it — the CLI (`cli.py`)
The "crunch all day" entry point. Decks are referenced by name from `DECKS`.
```
python3 cli.py --list                                           # available decks
python3 cli.py --deck1 dragapult --deck2 charizard_xy --games 5000   # win rates
python3 cli.py --deck1 dragapult --deck2 raging_bolt --seed 42 --save-game myrun
python3 cli.py --replay saved_games/myrun.json                  # step-by-step replay
```
Matchups mirror seats (cancels the going-first edge) and are deterministic by
`--seed`. `--agent` is `greedy` (default, ~900–1000 games/sec), `random`, or `mcts`
(far slower). Save files store the reproducible recipe + full step log; replay
re-simulates from the seed and verifies the log matches byte-for-byte.
`src/engine/run.py` is the lower-level batch loop; `src/engine/matchup.py` is the
instrumented validation runner (win% + right-lines evidence).

## Validation status (see `docs/VALIDATION_RESULT.md`)
Card-implementation milestone is COMPLETE (both tournament lists fully faithful).
The matchup number, however, reads more EVEN than reality: sim rates Dragapult vs
Mega Charizard ~53–59%, published Limitless ~84%. This is NOT a card/engine-fidelity
failure — it's **agent/policy strength**: greedy and single-turn eval-MCTS don't yet
express Dragapult's multi-turn spread+disruption plan. The strength lever (deeper
MCTS / better target policies) is the open frontier, deliberately deprioritized in
favor of a solid, usable, trustworthy core.

## Known limitations (be honest about these)
- **Greedy mispilots complex decks.** It ranks attacks by printed damage and can't
  sequence multi-step plans, so e.g. `raging_bolt` (discard-energy-for-damage,
  2-type cost) underperforms (~16–28% vs dragapult) and games frequently end by
  self-deck-out rather than prizes. The CARDS are correct (unit-tested); the
  *piloting* is weak. Use `--agent mcts` for stronger (slower) play, or read win
  rates as greedy-piloted, not optimal.
- Full multi-turn ISMCTS / hidden-hand-aware eval are not built (see VALIDATION_RESULT).

## Card legality
The Mega ex mechanic is current (mark I). Old SV-base ex (Charizard ex, Gardevoir
ex, mark G) rotated OUT — always check the pool, never card-name memory. Rotation
lives in one place: `STANDARD_LEGAL_MARKS` in `src/engine/legality.py`.
