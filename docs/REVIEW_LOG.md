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

## R7 — Second archetype: Mega Charizard X ex (branch: feat/raging-bolt → renamed work)
**Correction:** I first claimed Charizard/Gardevoir had "rotated out." Half right —
the *old* Charizard ex / Gardevoir ex (G mark) rotated, but the **Mega** versions
(Mega Charizard X ex, Mega Gardevoir ex, 27 Mega ex total) are legal (mark I) and
in the pool. Lesson reinforced: check the pool, not card-name memory.
**Engine fidelity fixes:**
- **MEGA prize rule** — Mega Evolution ex give up **3** prizes when KO'd, not 2.
  `gives_up_prizes` now returns 3 for MEGA ex, 2 for other ex, 1 otherwise. This
  materially affects any Mega matchup (a wrong value silently skews win rates).
- **Variable damage** — `×` and `+` attacks now resolve correctly: an attack with
  a registered effect computes its full hit (weakness applied once to the total);
  an unregistered variable attack falls back to its printed base (fixed a
  regression where Iron Thorns' `70×` briefly did 0).
**Cards implemented + tested (5 new):** Inferno X (Mega Charizard X ex, Fire
discard ×90), Bellowing Thunder + Burst Roar (Raging Bolt ex), Teal Dance +
Myriad Leaf Shower (Teal Mask Ogerpon ex). Plus an ability `can_use` guard so
the engine never offers a do-nothing ability (e.g. Teal Dance with no Grass).
**Determinize hardening (from R6 review):** added the *correct* zone-integrity
invariant — public zones (in-play, attached energy, discard) byte-identical
pre/post, and resampled cards drawn only from each player's own pool (no
cross-player leak). Note: prizes intentionally DO resample (their contents are
hidden — pinning them would leak info), so Grok's originally-proposed discard
test would have been trivially true; this is the right test instead.
**Internal matchup (NOT validated):** Mega Charizard X ex vs Dragapult ≈ 50%
(greedy) / 46% (MCTS). Roughly even, plausible — but these are fixture decks, not
tournament lists, so this is an internal data point, NOT a number to compare to
Limitless yet. Real validation still needs faithful 60-card lists on both sides.
**Next:** faithful decklists → validate one matchup vs a published Limitless
result; optional multi-turn ISMCTS.
