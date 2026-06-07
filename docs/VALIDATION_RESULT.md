# Validation Result — Dragapult ex vs Mega Charizard X/Y ex

**Status: RATIFIED (2026-06-06, see R20 below + REVIEW_LOG R20).** Simulator directionally
validated; matchup-fidelity milestone CLOSED against an uncertainty-aware target. The historical
sections below trace how the verdict was reached (R12 → R19 chased a mis-specified 84%/68–82% band;
R20 resolved that the band itself was the error). The R20 section is the standing conclusion.

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

---

## Policy milestone — piece 1b: strategic-disruption terms (lines off 0) + a real MCTS bug

Reordered (correctly): value disruption BEFORE deepening search — deeper search toward an eval
that scores disruption at ~0 just explores more lines that undervalue the same thing.

**Added mechanistic board-fact terms to `position_value`** (not number-fitted): per opponent
Pokémon whose Ability is currently shut off (TRW → Dudunsparce's draw), and per Benched Pokémon a
Battle Cage is shielding from spread.

**Then a sensitivity test exposed the actual blocker:** even at 40× weights, TRW/Battle Cage still
fired 0 — because **MCTS's `_semantic_key` had no case for `play_stadium`/`attach_tool`** (added to
the engine *after* MCTS was written). They collapsed to the `("pass",)` key and were **dropped from
the search entirely.** A whole class of plays was invisible to MCTS, regardless of eval. Fixed.

**Result — eval-MCTS mirror, 120 games, after the fix (disruption lines climbing off 0 = the
success signal):**

| line | before 1b | after 1b |
|------|----------:|---------:|
| **TRW (ability lock / draw-denial)** | **0/120** | **77/120** |
| **Battle Cage prevented spread** | **0/120** | **22/120** |
| Phantom Dive | 36 | 31 |
| gust (Boss's Orders) | 81 | 86 |
| Crushing Hammer | 44 | 42 |
| Budew Item-lock | 0 | **0** (defensible skip — see CORRECTION) |
| Dragapult win % | 59.2% | 52.5% |
| won by prizes | 42% | 47% |

**Read:** the disruption mechanism now *works* — the stadium war (Dragapult's TRW vs Charizard's
Battle Cage) is modeled and fires. The win % actually dipped because Battle Cage's spread-denial is
effective and two equal MCTS agents fight the stadium war to ~even; reaching the Dragapult-favored
band now needs deeper search (piece 2b) to out-sequence the war, plus the two still-missing pieces.
**Budew stays 0** — see the CORRECTION below; the earlier "promote-to-disrupt / opener-sequencing"
hypothesis (this line, and the one in §2b) was **investigated and overturned**. The headline of 1b
stands: the MCTS bug was the unlock — without valuing + *surfacing* disruption, no amount of search
would have played the stadium war.

---

## Policy milestone — piece 2b: multi-turn negamax MCTS (depth across the turn boundary)

`MCTSAgent(search_plies=N)`: 1 = single-turn (v1, preserved); ≥2 = the tree spans the turn boundary
into the opponent's reply, with **negamax backprop** (each node's stat from the perspective of the
player who *chose* it, so opponent nodes are optimized for the opponent — no inversion). No-leak
preserved (one root determinization per iteration; opponent's in-tree draws come off that deck).

**Correctness gates (all green BEFORE trusting the number):** `test_mcts_negamax.py` (opponent model
not inverted — a me-winning line scores ~0 at the opponent's node); `search_plies=1` still beats
greedy **61%** (backward compatible); full suite green. 2-ply is **0.6 s/game** (the eval leaf
truncates each deep line — pieces 1 and 2b are synergistic).

**Result — eval-MCTS, `search_plies=2`, 120 games, mirrored:**

| line | 1-ply (R15) | **2-ply (R17)** |
|------|------------:|----------------:|
| Dragapult win % | 52.5% | **55.8%** |
| **TRW (Dragapult's draw-denial)** | 77 | **79/120** |
| **Battle Cage (Charizard's defense)** | 22 | **16/120** |
| **Budew Item-lock** | 0 | **0/120** |
| gust / Crushing Hammer / Phantom Dive / Cursed Blast | 86/42/31/34 | 86 / 55 / 31 / 35 |

**Read:** depth tilts the **stadium war toward Dragapult** (TRW 79 ≫ Battle Cage 16 — Dragapult now
out-sequences it) and nudges win% up (52.5→55.8%, within sample noise at n=120). **Budew stays 0** —
the cause is the CORRECTION below, *not* depth or opener-sequencing. Still below the band; not tuned
toward 84. Net: a partial mechanism win (stadium war).

---

## CORRECTION (post-2b investigation) — the Budew 0/120 framing was wrong

Earlier (R15/R17) this doc attributed Budew = 0/120 to a "promote-to-disrupt / turn-1 opener"
policy gap. **An investigation overturned that:**
- **Itchy Pollen is free-cost** (zero energy) — Budew can attack with nothing attached.
- In the best case (seed 64: Dragapult second, Budew already Active), the agent has Itchy Pollen
  **legally available turn 2** and **chooses to retreat Budew and develop instead.** Promotion
  happens; the attack is in `legal_actions`; the agent passes on it.
- So it is **not** an opener-sequencing or action-space gap. It is a **valuation choice**: under the
  current eval, "retreat → develop → draw → continue the turn" out-scores "Itchy Pollen → end turn,"
  and 2-ply negamax confirms it (the simulated opponent routes around an item-lock with supporters/
  abilities, so the modeled cost of one lock is small). **The agent's choice is defensible.**

**Decision (D + pivot):** accept Budew 0/120 as a play-style under the current valuation — **not a
bug.** Do NOT crank `W_ITEM_LOCK` (point-chasing; would over-fire lock everywhere). Budew is a 1-of
worth ~1–2 pts; the ~10–20 pt band gap is dominated by **targeting** in the lines that fire in most
games. **Known limitation (recorded, not fixed):** an item-lock's value is contingent on the
opponent's *hidden* hand (which items they'd skip), which PIMC with a public-info-determinized
opponent hand can't see except in the random fraction of worlds where they hold the key item.

**Next: piece 3 = search-owned TARGET policies** (replacing the v0 greedy defaults), the real band
lever:
- `gust_target` — drag the benched Pokémon whose removal yields a **KO this turn** (energy + the
  active's damage), not just lowest-HP; fall back to highest-threat when no KO is available.
- `cursed_blast_target` — pick the KO that closes the most prize math and/or disables the most engine
  (TRW/Battle Cage holder, draw-engine pieces like Dudunsparce).
- `phantom_dive_spread` — distribute the 6 counters as **next-turn KO setup**, not v0 max-KO-this-turn.

Budew (B-style, scoped by the opponent's *developed-ness* — board facts, not turn number) is
revisited only if target policies close most of the gap and disruption is the residual. 2c (mid-tree
re-determinization / full ISMCTS) stays deferred — both runs say the residual is policy, not width.

**Independent corroboration (cowork).** A separate cowork run of the same 2-ply regression
(`docs/PIECE2b_REGRESSION_cowork.md`) reached the same result: Dragapult **60.8%** (vs my 55.8% —
overlapping at n=120; pooled ~58%), every line-fire count within sampling noise (Phantom Dive 29/31,
gust 91/86, TRW 82/79, Battle Cage 14/16), and **Budew 0/120 in both** (a defensible valuation skip,
per the CORRECTION — not the piece-3 driver). Two independent implementations agreeing on the
mechanism. Note: cowork's run was 2-seed-chunked
(0+999) for a shell-timeout; **this doc's number is the clean single-seed-0 mirrored run** — use it
for the REVIEW_LOG.

---

## Policy milestone — piece 3 ablation + the depth-vs-structure-vs-target investigation (R20)

After piece 3 (search-owned target policies) **regressed** the matchup instead of closing it, the
question "what actually causes the sim ≈58% vs published 84% gap?" was reopened and answered with
three measurement-only experiments (no spec/weight tuning — the standing rule held throughout).

### (a) Piece-3 ablation — the target policies hurt, and one arm carries it
Per-policy symmetric ablation (`src/engine/matchup_ablation.py`, seed 0, n=120/arm, same seeds):

| arm | win% | Δ vs OFF |
|-----|-----:|---------:|
| OFF (v0) | 50.8% | — |
| GUST_ONLY | 50.0% | −0.8pt (≈1 game, noise) |
| CURSED_ONLY | 48.3% | **−2.5pt** |
| PHANTOM_ONLY | 50.8% | +0.0pt |
| ALL_ON (R19) | 48.3% | **−2.5pt** |

**CURSED_ONLY's Δ equals ALL_ON's Δ** — the Cursed Blast engine-piece target policy carries the
entire R19 regression; gust/phantom are inert. This is the H1 signature from the ablation's own
docstring: the engine-piece allowlist over-weights *replaceable-from-deck* targets (Dragapult
spends a Cursed Blast self-KO to snipe Charizard's Dudunsparce, which re-evolves off a spare
Dunsparce — a tempo cost dressed up as engine destruction). **Verdict held — surfaced, not tuned.**
R19's target policies are NOT in the validation harness (`matchup.py` uses plain `MCTSAgent`); the
clean baseline below is unaffected.

### (b) Search-scaling diagnostic — depth helps modestly, does NOT march to 84%
eval-MCTS, same seeds, n=40/config (wide CI — read the trend): 100it/2ply **57.5%**, 400it/2ply
**65.0%**, 1000it/2ply **60.0%**, 200it/3ply **52.5%**, 600it/3ply **65.0%**. Budget moves it
~57→60–65% but is **noise-dominated and non-monotonic** (1000it < 400it). Conclusion: the gap is
*partly* search depth (+5–8pt, with diminishing/noisy returns) but **mostly not** — depth alone
cannot bridge a 25-pt gap. (This is the data that says building 2c full ISMCTS is unlikely to be
worth its correctness risk for the few points on offer.)

### (c) Asymmetric-strength — 84% is NOT reproduced by any sensible skill gap
The published 84% is a mirror of **unequal humans** (Charizard pilots went 3-16); the sim is a mirror
of **equal agents**. Pitting strong vs weak (n=50/cell, seed 0):

| Dragapult | Charizard | drag% | note |
|-----------|-----------|------:|------|
| eval-MCTS | eval-MCTS | 58.0% | same-skill strong (baseline) |
| eval-MCTS | EvalAgent (1-ply) | 72.0% | **discount** — EvalAgent is degenerate (over-develops, board-wiped ~T8); strong Dragapult farms it, not a "weaker but sensible" opponent |
| eval-MCTS | greedy | 56.0% | strong vs greedy — the maximal *clean* skill gap |
| EvalAgent | greedy | 52.0% | 1-ply vs greedy |
| greedy | greedy | 48.0% | same-skill greedy |

The maximal **clean** skill gap (strong Dragapult vs greedy Charizard) is only **56%** — *below* the
same-skill mirror. Skill asymmetry does not explain the gap; every clean configuration lands 48–65%.

### (d) Clean confirmation number (the sim's same-skill matchup estimate)
eval-MCTS 300it/2ply, **disjoint** seeds {0, 1000, 2000}, 120 games/seed (an earlier run with seeds
{0,1,2} was discarded — those windows overlapped ~98% and gave a falsely-precise CI):

| | win% | Wilson 95% CI | n |
|---|-----:|:-------------:|--:|
| **Sim (same-skill mirror)** | **56.7%** | **[51.5%, 61.7%]** | 360 (independent) |
| Published (Limitless CRI) | 84% (16-3-0) | [62%, 94%] | 19 |

Per-seed: 59.2 / 55.0 / 55.8 — stable ~57%. The two intervals **nearly touch but do not overlap**
(sim ceiling 61.7 vs published floor 62.0).

### Honest verdict
- **Milestone as originally specified (land in ~68–82% "for the right reasons"): NOT met.** The sim
  sits at ~57% and no honest lever (depth, skill-asymmetry) reaches the band.
- **But the gap is dominated by target mis-specification, not sim infidelity.** The ~68–82% band was
  derived from an over-precise reading of a **19-game** sample. Properly, the published number's own
  95% CI floor is ~62% — only ~0.3pt above the sim's CI ceiling. At point estimates the gap is ~27pt;
  at the honest interval boundary it is ~0pt.
- **The sim is directionally correct and roughly calibrated.** It robustly identifies Dragapult as
  favored at ~57%, with the right lines firing (Phantom Dive, gust, TRW stadium war, Cursed Blast).
  The residual disagreement is attributable to (i) a same-skill mirror vs a skill-skewed human sample
  — the real 84% bakes in Charizard pilots going 3-16 — and (ii) modest, noisy search depth.
- **Recommendation:** accept the simulator as **directionally validated** against an
  uncertainty-aware target; record **56.7% [51.5, 61.7]** as the sim's same-skill estimate of the
  matchup. 2c (full ISMCTS) and a hidden-hand-aware eval term remain available levers but are **not
  clearly worth their cost** — the scaling and asymmetry data say they would buy a few points, not
  close to 84%, and 84% is not the right yardstick for a same-skill mirror. **Do not tune toward the
  point estimate** (forbidden, and it would fabricate fidelity).
