# Contributing / Workflow

Small project, simple rules. The point is to keep the build trustworthy.

## The loop
1. **Build** a focused increment (one milestone: a feature, an archetype, an agent).
2. **Test** — every new card effect needs a test asserting it matches the printed
   card text. No effect is trusted without one.
3. **Review** — summarize the change; the reviewer (Grok) checks it; fixes get
   applied and re-verified. Log the cycle in `docs/REVIEW_LOG.md`.
4. **Commit** with a message that says what changed and what was verified.

## Non-negotiables (don't regress these)
- **The LLM is never in the game loop.** Games are played by the deterministic
  engine, zero tokens. The model authors effects, self-heals, and synthesizes.
- **Fidelity gates everything.** A wrong card effect silently corrupts every win
  rate that touches it. Validate against known/published results before trusting
  a number.
- **Pull the live card list; never hardcode card names** — the format rotates.

## Running things
```bash
python3 src/fetch_standard_pool.py --out data/standard_pool.json   # build pool
python3 tests/test_pool.py                                          # data invariants
python3 tests/test_engine.py                                        # engine invariants
python3 tests/test_effects.py                                       # per-card effects
python3 tests/test_stadium.py                                       # Stadium zone + damage chokepoints
python3 tests/test_mega.py                                          # MEGA + Tera namesake rules
python3 tests/test_legality.py                                      # format / rotation framework
python3 tests/test_decklist_coverage.py                             # coverage snapshot (green; red on drift)
python3 -m src.engine.run --games 1000                              # simulate (0 tokens)
python3 -m src.engine.run --log --seed 7                            # watch one game
```

## Adding a card effect
1. Find the real text (it's in `data/standard_pool.json`; never invent it).
2. Write a small effect fn in `src/engine/effects.py` (reuse primitives).
3. Register it in `ATTACK_EFFECTS` / `ABILITY_EFFECTS` / `TRAINER_EFFECTS`
   (add a `can_play` predicate for conditional Trainers).
4. Add a test in `tests/test_effects.py` asserting it matches the text exactly.
5. Run all three test suites. Commit.

## Branch/PR suggestion
Use a branch per milestone (`feat/mcts-agent`, `feat/charizard-line`) and open a
PR so reviews attach to the diff. `main` stays green (all tests passing).
