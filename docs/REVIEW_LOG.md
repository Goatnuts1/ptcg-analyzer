# Review Log

This project uses a two-reviewer loop: **Claude** builds, **Grok** reviews, fixes
get applied and re-verified. This file tracks each cycle so the back-and-forth is
visible in the repo (and so a future session can see what was decided and why).

Convention: one entry per review, newest at the bottom. Link commits where useful.

---

## R1 — Data layer
**Reviewer:** Grok · **Score:** 8.5/10
**Verdict:** Strong foundation. Architecture correct ("LLM never in the game loop"),
clean `slim()`, dual legality check, good docs.
**Fixes requested → applied (commit 67f5eff):**
- Add `evolvesTo` to the schema ✓
- Tighten test pool-size bounds (800–2500 → 1100–1800) ✓
- Robust `hp` conversion (`safe_hp`) ✓
- Narrow exception handling + track failed sets (loud warning, non-zero exit) ✓
- Move HTML inspector to `viz/` ✓
- Build metadata sidecar (`*_meta.json`) ✓ (beyond ask)

## R2 — Post-fix verification
**Reviewer:** Grok · **Score:** 9.2/10
**Verdict:** All R1 fixes verified. Partial-pull guarding went beyond the ask.
Data layer production-ready. Greenlit engine work.

## R3 — Engine v0
**Reviewer:** Grok · **Score:** (rolled into R4 discussion)
**Built:** Card model, state, deterministic rules engine, agents, batch runner.
~1,700–2,500 games/sec, 0 tokens. greedy beats random 99%. Effects stubbed
behind hooks. (commit a74fa37)

## R4 — Effect system + Dragapult line
**Reviewer:** Grok · **Score:** 9.4/10
**Built (commit 59fb45e):** hybrid effect system (primitives + registries),
Phantom Dive (200 + 6-counter bench spread), Recon Directive, ability activation,
**evolution timing rules** (caught a real bug: line was evolving on turn 1).
**Polish notes → applied in R5:**
- `EffectContext`: make `source` optional, add `target` ✓
- Greedy should evolve/develop more aggressively ✓

## R5 — Trainer engine (Option A)
**Built (commit d3c4d0f):** `play_trainer` mechanic (Item/Supporter rules,
`can_play` gating); Rare Candy, Buddy-Buddy Poffin, Cheren, Boss's Orders;
`EffectContext` polish; `db` threaded through state for searches/chains.
**Bug found + fixed:** `play_trainer` popped the card after the effect ran, but
effects mutate the hand → index shift → IndexError. Now pops before running.
**Finding:** the rotation removed Professor's Research / Iono from Standard;
current draw engine is Cheren-tier. (Reinforces: pull the live list, never
hardcode card names.)
**Honest status:** Dragapult functions (Phantom Dive by turn 3) but only ~36% vs
the Lightning fixture — that's *weak greedy piloting* of a Stage 2 deck, NOT the
real matchup. Win rates are not yet trustworthy.

## Next
**MCTS agent** is the gate before any win rate is trustworthy. Validate each
matchup against a published result before believing it. Card-library breadth can
grow in parallel (same discipline: primitive + registry + test per card).

## R6 — MCTS agent (branch: mcts-agent)
**Built:** `GameState.clone()` (shares immutable Cards, copies mutable wrappers);
`determinize()` for hidden info (PIMC — reshuffles hidden zones, preserves the
acting player's known info; tested to conserve the card multiset); single-turn
UCT with greedy rollouts and semantic action de-duplication. Runner gains an
`mcts` agent option. `finish_game()` refactored out of `play_game` so rollouts
can finish an arbitrary mid-game state.
**Result:** MCTS beats greedy **61%** across mirrored seats (deterministic, fixed
seeds), ~1 game/sec at 120 iterations. Honest framing: a real but bounded edge —
greedy already makes obvious plays; MCTS wins on sequencing and non-obvious lines.
**Scope/limits (documented):** tree is single-turn (not full multi-turn ISMCTS);
determinization assumes both decklists are known (true in self-play).
**Tests:** `tests/test_mcts.py` — clone/determinize correctness (instant) +
strength check (~35s, `--fast` to skip).
**Next:** breadth (more real archetypes) + validation vs published Limitless
matchups; optional full ISMCTS.
