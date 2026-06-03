# Validation Result — Dragapult ex vs Mega Charizard X/Y ex

**Status: findings for review — NOT a final verdict.** (Per the standing rule: the matchup
number goes to the user before any REVIEW_LOG verdict is written.)

## What was validated

The card-implementation milestone is **complete**: both current Limitless tournament lists are
**fully faithful** — every non-vanilla card has a hand-written, unit-tested effect (coverage
snapshot `EXPECTED_NEEDS_EFFECT = {}`, 14 test suites green). The question this run answers is the
*actual point* of the milestone: **does the simulator reproduce the real-world matchup?**

## The numbers

| Source | Dragapult ex win % | Notes |
|--------|-------------------:|-------|
| **Published (Limitless)** | **~84%** | CRI Standard 2026, 16-3-0 — small (19-game) sample; consistent with the tiers (Dragapult ~52% overall vs Mega Charizard X ~29%). |
| Sim — **greedy** mirror | **~53%** | 500 games, seats mirrored. Near-even. |
| Sim — **MCTS** mirror | **57.5%** | mirrored-seat, 100 iters, 40 games (wide CI ±~15%; ~17s/game on these decks). Slightly above greedy — MCTS finds a little more of Dragapult's edge, but nowhere near 84%. |

## Honest read

The simulator currently rates this matchup as **far more even (~53%) than reality (~84%)**. The
gap is large and outside any reasonable tolerance. Crucially, this is **not** an engine-core or
card-fidelity failure — the cards are implemented faithfully and tested. Per the pre-registered
suspect list (§6/§5), the divergence points at **agent / policy strength**:

1. **Greedy can't exploit Dragapult's plan.** Dragapult's real edge is *sequenced bench spread*
   (Phantom Dive) plus *disruption* (Budew Item-lock, Crushing Hammer, TRW shutting off the
   Charizard deck's Dudunsparce draw engine, gust into KOs). Greedy ranks attacks by printed
   damage and plays disruption/gust poorly (logged in §5) — so it leaves most of Dragapult's
   advantage on the table, flattening the matchup toward 50/50.
2. **MCTS is single-turn + greedy-rollout.** It explores this turn's sequencing but rolls out with
   greedy, so it inherits greedy's blind spots for multi-turn spread/disruption plans.
3. **Many effects keep v0 greedy target policies** (place-counters maximize-KO, search pick-best,
   Cursed Blast KO-only gate, gust lowest-HP). These are reasonable defaults but not the lines a
   strong Dragapult player takes.
4. The published 84% is itself a **small sample** (19 games) and may overstate the true edge — but
   even a true ~70% would leave the sim well short.

## Conclusion (for the user to ratify)

**The card-implementation milestone succeeded; the matchup-fidelity milestone did not (yet).** This
is the honest, valuable outcome the validation was designed to surface: faithful cards are
necessary but not sufficient — a sim only reflects reality once the *agent* plays the decks at a
level that expresses their real strategy. **The next milestone is policy/agent strength**, not more
cards:
- MCTS upgrades: multi-turn / ISMCTS, smarter rollout policy, effect-aware action valuation
  (value Phantom Dive's spread, gust-into-KO, disruption — not just printed damage).
- Replace the v0 greedy target policies with MCTS-owned choices.
- Re-run this exact matchup as the regression metric; target the published ~84% within ~5–8%.

The harness is ready for that work: faithful decks, a green-on-correct coverage snapshot, a
mirrored-seat matchup runner, and a documented suspect list.
