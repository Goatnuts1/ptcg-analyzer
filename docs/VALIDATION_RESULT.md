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
| Budew Item-lock | 0 | **0** (opener-sequencing, below) |
| Dragapult win % | 59.2% | 52.5% |
| won by prizes | 42% | 47% |

**Read:** the disruption mechanism now *works* — the stadium war (Dragapult's TRW vs Charizard's
Battle Cage) is modeled and fires. The win % actually dipped because Battle Cage's spread-denial is
effective and two equal MCTS agents fight the stadium war to ~even; reaching the Dragapult-favored
band now needs deeper search (piece 2b) to out-sequence the war, plus the two still-missing pieces.
**Budew stays 0** — it's a turn-1 *opener* line (Budew must be Active to Itchy Pollen); the agent
doesn't promote-to-disrupt. That's a sequencing/opening limitation, not an eval-term gap; flag for
piece 2b/3. The headline is the MCTS bug: the reordering instinct was right — without valuing +
*surfacing* disruption, no amount of search would have played it.

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

**Read (matches the doc's predicted branch):** depth tilts the **stadium war toward Dragapult**
(TRW 79 ≫ Battle Cage 16 — Dragapult now out-sequences it) and nudges win% up (52.5→55.8%, within
sample noise at n=120). **But Budew stays 0** → exactly the doc's call: *depth alone wasn't enough;
promote-to-disrupt is a turn-1 opening choice the legal-action set doesn't surface well* → **piece 3**
(search-owned target/opening policies). Still below the band; not tuned toward 84. Net: a partial
mechanism win (stadium war), with the named remaining gap (Budew opener) now precisely localized.

**Next: piece 3** — search-owned opening/target policies (promote-to-disrupt so Budew's Item-lock
can actually be played turn 1), then re-measure. Optional 2c: mid-tree re-determinization (full
ISMCTS) — deferred unless 3 shows it's needed.

**Independent corroboration (cowork).** A separate cowork run of the same 2-ply regression
(`docs/PIECE2b_REGRESSION_cowork.md`) reached the same result: Dragapult **60.8%** (vs my 55.8% —
overlapping at n=120; pooled ~58%), every line-fire count within sampling noise (Phantom Dive 29/31,
gust 91/86, TRW 82/79, Battle Cage 14/16), and **Budew 0/120 in both → piece 3**. Two independent
implementations agreeing on the mechanism *and* the named gap. Note: cowork's run was 2-seed-chunked
(0+999) for a shell-timeout; **this doc's number is the clean single-seed-0 mirrored run** — use it
for the REVIEW_LOG.
