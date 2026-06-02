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
- Data layer: done + tested. `data/standard_pool.json` = 1,273 cards (marks H/I/J).
- Engine v0: done + tested. `src/engine/` plays full legal games at ~1,700
  games/sec, zero tokens. Core rules faithful incl. evolution timing.
- Effect system: done + tested. `effects.py` = primitives + registries for
  attacks, abilities, and Trainers. 8 cards implemented (Dragapult line + Rare
  Candy, Buddy-Buddy Poffin, Cheren, Boss's Orders), each validated vs card text.
  Trainer play wired in (Items unlimited, Supporters once/turn, can_play gating).
  Basic energy injected in the loader. `db` threaded through state for searches.
- Validated: greedy beats random ~99%; effects fire in real games; Dragapult
  attacks as early as turn 3 via Rare Candy.

## Effect system (`src/engine/effects.py`)
Hybrid: primitives + registries. Attack/ability registries keyed by
(card_name, move_name); Trainer registry keyed by card_name with a parallel
can_play predicate. Engine hooks: `_resolve_attack`, use_ability branch,
play_trainer branch. KO logic shared in `process_knockouts` (scans bench).
IMPORTANT: in play_trainer the card is popped from hand BEFORE the effect runs,
because effects mutate the hand (learned bug — index shift).

- MCTS agent: done + tested. `src/engine/mcts.py` = GameState.clone() +
  determinize() (PIMC, handles hidden info) + single-turn UCT with greedy
  rollouts. Beats greedy 61% across mirrored seats (deterministic). ~1 game/sec
  at 120 iterations. `tests/test_mcts.py` checks clone/determinize correctness
  (instant) and strength (~35s; skip with --fast).
- Validated: greedy beats random ~99%; MCTS beats greedy ~61%; effects fire.

## MCTS notes (`src/engine/mcts.py`)
- clone() shares immutable Card refs, copies mutable wrappers — keep it that way.
- determinize() conserves the exact card multiset and preserves the acting
  player's known info (own hand, public board/discard); reshuffles hidden zones.
- Tree is SINGLE-TURN (acting player's sequencing); rest is rolled out. Full
  multi-turn ISMCTS is a later upgrade.
- Actions are de-duplicated by semantic key (same card from different hand slots,
  same energy type to same target) so the iteration budget isn't wasted.

## Next task
VALIDATION is now the priority. Two real archetypes exist (Dragapult, Mega
Charizard X ex) but as FIXTURE decks. To trust a matchup number:
1. Build faithful ~60-card tournament lists for both (proper draw/search counts,
   energy ratios, tech cards) — pull current lists from Limitless.
2. Run the matchup with MCTS and compare to the published win rate (target within
   ~5-8%). Log it in REVIEW_LOG. THAT comparison is what tells us if the sim
   reflects reality.
Note on card legality: the Mega ex mechanic is current (mark I). Old SV-base ex
(Charizard ex, Gardevoir ex, mark G) rotated OUT — always check the pool, never
card-name memory. Optional later: multi-turn ISMCTS; more archetypes.
