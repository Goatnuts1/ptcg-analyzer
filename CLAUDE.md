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
- Data layer is done and tested. `data/standard_pool.json` = 1,273 unique
  Standard-legal cards (regulation marks H/I/J, 2026 season).
- Engine, agents, and LLM roles are not built yet.

## Layout
- `src/`    — pipeline code (currently just the fetch script)
- `data/`   — generated artifacts (gitignored; rebuild with the fetch script)
- `tests/`  — invariant checks
- `docs/`   — notes

## Commands
```bash
python3 src/fetch_standard_pool.py --out data/standard_pool.json
python3 tests/test_pool.py
```

## Conventions
- Cards are referenced by `name` (de-duped across set reprints).
- Standard legality = regulation mark in LEGAL_MARKS AND legalities.standard == "Legal".
- Format rotation = change `LEGAL_MARKS` in the fetch script, re-run fetch + test.
- Keep the data layer's slimmed schema lean; only add fields the engine reads.

## Next task
Card schema + engine state machine (turns, phases, energy, evolution, prizes,
status, bench, stadiums, tools). Effects/`text` parsing is the long pole — scope
to current meta cards first, not all 1,273.
