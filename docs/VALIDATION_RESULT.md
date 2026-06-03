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

---

## Policy milestone — piece 1: effect-aware valuation (findings)

Built `src/engine/evaluation.py::position_value` — score the *resulting position* (prizes,
damage-toward-KO = bench pressure, disruption flags, board/attacker development), so an action
is worth the board it produces, not its printed number. Plus `EvalAgent` (1-ply lookahead) and
`src/engine/matchup.py` (the regression metric: win% **+ right-lines evidence**).

**The valuation is sound in isolation** (`test_evaluation.py`): it rewards bench pressure,
prizes, and disruption, and — set up — ranks Phantom Dive's spread above passing (value 77 vs
31), i.e. it values the effect, not the "200." EvalAgent correctly attacks when the attacker is
ready.

**But 1-ply is not enough for full games.** EvalAgent mirror (100 games): Dragapult 64% — and
the line evidence shows it's **for the wrong reasons**: Phantom Dive 0/100, gust 0/100,
disruption 0/100, only ~1% won by prizes. Games end ~turn 8 by board-wipe because a 1-ply agent
over-develops one line and can't see the multi-turn setup→attack→prize arc. **This 64% is NOT a
valid validation number** — it's a degenerate-play artifact.

**Conclusion:** position_value is a correct, reusable evaluation; the limiter is *search depth*,
exactly as the build order anticipated. **Piece 2 = MCTS using position_value as its leaf
evaluation** is what will make the agent express the deck's plan.

---

## Policy milestone — piece 2: eval-MCTS (the real number, with right-lines evidence)

Wired `position_value` into MCTS as a **leaf evaluation** (`MCTSAgent(rollout="eval")`): stop at
the leaf and back-propagate `logistic(position_value)` instead of a terminal greedy playout. Far
cheaper (**0.5 s/game** vs ~17 s for terminal rollouts) and it values within-turn lines.

**Result — eval-MCTS mirror, 120 games, 100 iters:**

| | value |
|---|---:|
| **Dragapult ex win %** | **59.2%** (greedy 53 → terminal-MCTS 57.5 → eval-MCTS 59.2) |
| won by prizes | **42%** (vs EvalAgent's 1% — games close the real way again) |
| Phantom Dive (spread) | 36/120 |
| gust (Boss's Orders) | 81/120 |
| Cursed Blast (KO engine) | 34/120 |
| Crushing Hammer (disruption) | 44/120 |
| Budew Item-lock / TRW / Battle Cage | **0 / 0 / 0** |

**Read:** real, non-degenerate play — the *tactical* lines fire (spread, gust, KO engine,
energy-denial), and the number is climbing in the right direction. But it's **still below the
~68–82% band** (~25 pts under the published 84%). Two honest causes for the residual gap:
1. **Search depth** — this is a single-turn tree + leaf eval. Dragapult's edge compounds over
   *multiple* turns (spread now → KOs later); full multi-turn / ISMCTS (build-order piece 2b)
   should recover more of it.
2. **The eval doesn't yet value *strategic* disruption** — Budew Item-lock, TRW shutting off the
   Charizard deck's Dudunsparce draw engine, and Battle Cage denying spread all read as ~0 to
   `position_value` (no term for "opponent's engine disabled" / "future spread prevented"), so the
   agent never plays them. These are precisely the lines that should widen the matchup.

**Next:** (2b) multi-turn/ISMCTS lookahead, then (3) replace the v0 target policies — and, carefully
(no point-chasing), a couple of strategic-disruption terms in the eval (engine-denial, spread-denial).
Re-run this matchup as the regression metric toward the band. The harness + instrumentation make
each step measurable.
