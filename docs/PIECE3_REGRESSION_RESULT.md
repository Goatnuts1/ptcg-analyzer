# Piece 3 — Regression Result (target policies)

**Status: HELD for user/Grok ratification. This is a measurement, not a verdict.**
**Headline: the policies are correct and fire as designed, but they do NOT move
the matchup toward the band — they slightly and consistently move it the wrong way.**

## Setup

- Command: `python3 -m src.engine.matchup --agent mcts-eval --games 60 --plies 2 --iters 100 --seed {0,1}`
  (`--games 60` = 120 games/seat-orientation pair; mcts-eval, 2-ply negamax, 100 iters).
- Clean same-binary A/B: policy ON = the integrated `SearchPolicy`; policy OFF =
  rebind `mcts.SearchPolicy → V0Policy` so agents build a no-op (all-`None`) policy
  = pure v0. Everything else (seed, decks, iters, plies) identical.
- Both agents use the policy when ON (symmetric — it's a mirror-style matchup
  runner, Dragapult vs Mega Charizard X/Y).

## Numbers

| seed | OFF (v0) | ON (policy) | Δ (Dragapult) | gust→KO | cursed→engine | phantom→multi |
|---|---|---|---|---|---|---|
| 0 | 55.8% (67/120) | 52.5% (63/120) | −3.3pt (−4 games) | 43 | 26 | 14 |
| 1 | 55.0% (66/120) | 51.7% (62/120) | −3.3pt (−4 games) | 42 | 27 | 14 |
| **pooled** | **55.4% (133/240)** | **52.1% (125/240)** | **−3.3pt (−8/240)** | ~42 | ~26 | 14 |

Line-fire rates (gust ~85, Cursed Blast ~36, Phantom Dive ~31 per 120) are
unchanged ON vs OFF within noise — the cards are played at the same rate; only
the *targets* changed. With v0, the three policy markers are 0/0/0 by construction.

NOTE on the doc's "60.8%" piece-2b baseline: this clean A/B puts the pre-policy
number at ~55.4% (n=240), not 60.8%. The 60.8% figure came from different
conditions; the OFF column here is the honest same-binary control.

## What this means (read carefully — do not over-claim either way)

1. **Mechanism: confirmed.** The targeting demonstrably changed — 42 gust KOs, 26
   Cursed-Blast engine kills, 14 Phantom-Dive multi-setups per 120 that simply do
   not happen under v0 (0/0/0). The seam works; the policies do what they say.
2. **Win%: flat-to-slightly-negative, consistently.** −3.3pt for the favored side,
   the SAME −4 games on two independent seeds. Pooled that's ~1 SE (SE≈3.2% at
   n=240) — not statistically conclusive, but the cross-seed consistency argues
   it's a small *real* effect, not pure noise.
3. **Direction is wrong relative to the success criterion.** The criterion was
   "still inside, or moving toward, the Dragapult-favored 68–82% band, alongside
   mechanism counts moving." The mechanism counts moved; the band did not — it
   drifted ~3pt toward 50/50. **This is NOT a validation success as-built.**

Per the piece's own discipline ("a win% gain without mechanism movement is not
validation" — and the inverse, mechanism movement without the band moving the
right way, is equally not validation): **surface it and stop. Do not tune.**

## Most likely why sharper targeting *reduced* the favored side's edge

Both candidate mechanisms point the same way (hurt Dragapult), and both are
symmetric-application artifacts, not bugs:

- **Engine-kill helps the underdog.** Cursed Blast is a Charizard-side tech
  (Dusknoir/Dusclops). The engine-value tie-break lets *Charizard* snipe
  Dragapult's in-play engine piece 26×/120 — a sharper version of the disruption
  that was already Charizard's path back into a Dragapult-favored matchup.
  Sharper underdog disruption compresses the gap toward 50.
- **Phantom Dive's tempo-trade may not pay.** The ratified spec trades an
  immediate KO for ≥2 deferred next-turn threats (14×/120, Dragapult-side). If the
  deferred threats don't convert before the game turns, that's lost tempo for the
  side that was ahead.

These are hypotheses, not measured. Disentangling them needs a **per-policy
ablation** (next section).

## Recommended next steps (for user/Grok to choose — verdict HELD)

1. **Per-policy ablation:** toggle each of the three policies independently (3 ON,
   3 OFF) at the same seeds, to see which one(s) carry the −3.3pt. If it's the
   phantom tempo-trade, the spec — not the code — is the thing to revisit.
2. **Asymmetric A/B:** policy ON for only the Dragapult agent vs only the Charizard
   agent, to confirm the "engine-kill helps the underdog" hypothesis.
3. **Larger N / more seeds** to tighten the CI — *with the explicit caveat that
   chasing a band target is the point-chasing trap to avoid.* The goal is to
   understand the effect, not to make 52% become 70%.
4. **Architectural read:** if mechanistic targeting genuinely doesn't move this
   matchup, that's evidence the remaining sim↔reality gap lives in the deferred
   pieces (2c full ISMCTS, hidden-hand-aware eval), exactly as piece 3's own
   "out of scope" section predicted.

## What is NOT in question

The integration is clean and tested: 3 seam gate tests + 1 SearchPolicy-logic
test green; all 22 suites green; the policy is opt-in and leak-free (Greedy/Random
reference behavior unchanged — `test_mcts` strength unmoved). The negative result
is a finding about the *lever*, not a defect in the *implementation*.
