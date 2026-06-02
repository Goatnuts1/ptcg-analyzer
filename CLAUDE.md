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

## Next task
MCTS agent. The greedy heuristic can't sequence a Stage 2 deck, so win rates are
not yet trustworthy (Dragapult shows ~36% vs the Lightning fixture purely from
weak piloting). Replace GreedyAgent with MCTS over the existing legal_actions /
apply_action interface (state is cheap to copy; ~1,700 games/sec leaves room for
search). Only AFTER MCTS plays competently should we start trusting matchup win
rates — and validate each against a published result before believing it.
Broadening the card library (more archetypes) can proceed in parallel; same
discipline (primitive + registry + test per card).
