# Piece 2b — Multi-Turn Negamax MCTS — Regression Result

**Status:** findings for review — NOT a final verdict.

## Files dropped (2026-06-03)
- `src/engine/mcts.py` — multi-turn negamax MCTS (md5-identical to working-tree version already present; git showed `modified` but `diff` was empty, so the working tree already matched the zip)
- `tests/test_mcts_negamax.py` — pins the dangerous invariant (opponent nodes optimized for opponent)
- `docs/PIECE2b_multiturn_negamax.md` — design doc, 5 targeted edits, regression protocol

## Gate test — green
```
$ python3 tests/test_mcts_negamax.py
OK — negamax backprop: opponent nodes optimized for the opponent (no inversion).
```
Negamax backprop verified: opponent nodes accumulate `1 - value`. The inflated-but-believable bug is pinned out.

## Regression — Dragapult ex vs Mega Charizard X/Y ex, mirrored, eval-MCTS, `search_plies=2`

120 games total (60 per orientation), 100 iters, two chunks of 60 to fit shell timeouts (`--seed 0` and `--seed 999`):

| | greedy | terminal-MCTS | eval-MCTS (1-ply, R14) | eval-MCTS+1b disruption (R15) | **eval-MCTS+2-ply (piece 2b)** |
|---|---:|---:|---:|---:|---:|
| Dragapult win % | 53.0 | 57.5 | 59.2 | 52.5 | **60.8** |
| won by prizes | — | — | 42% | 47% | **39%** |

| line | R14 (1-ply) | R15 (1-ply + 1b) | **piece 2b (2-ply)** |
|------|------------:|-----------------:|---------------------:|
| Phantom Dive (spread) | 36/120 | 31/120 | **29/120** |
| gust (Boss's Orders) | 81/120 | 86/120 | **91/120** |
| Cursed Blast (KO engine) | 34/120 | — | **34/120** |
| Crushing Hammer | 44/120 | 42/120 | **56/120** |
| TRW (ability lock) | — | 77/120 | **82/120** |
| Battle Cage prevented spread | — | 22/120 | **14/120** |
| **Budew item-lock** | **0/120** | **0/120** | **0/120** |

## Honest read

**Win % moved in the right direction by ~8 points** (52.5 → 60.8), still below the 68–82% band. Tactical lines stayed healthy or strengthened: **gust 91/120, TRW 82/120, Crushing Hammer 56/120** — the multi-turn opponent makes gust-into-KO and energy-denial pay off more often. Phantom Dive count drifted down a touch (29/120) but the stadium war is alive (TRW + Battle Cage both firing; Battle Cage dropped 22 → 14, consistent with Dragapult sequencing around it or finding non-spread lines under it).

**But the named gap did not close: Budew = 0/120.** Per R15, Budew is a turn-1 *opener* line (must be Active to Itchy Pollen), and a deeper tree alone can't cure that — the agent doesn't *promote a fresh Budew*. Multi-turn lets search **see** the payoff one turn out, but the action-space gating around active/bench placement at the opener is still single-policy. That is **piece 3** (promote-to-disrupt / target policies), exactly as anticipated.

**Did multi-turn earn its place?** Partially. Real depth was added (gust/TRW/CH all up, win % up ~8 pts toward the band). But the diagnostic line specifically flagged for 2b — **Budew off 0/120 — did not move**. Per the band+mechanism rule, the win % gain alone is not the validation; piece 3 needs to land before this matchup is read as closed.

## Caveats
- Two seeds chunked (0 and 999) due to shell timeout, not a single seed-0 run. Point estimate fine; not bit-exact reproducible as one continuous trace. R17 should re-run as a single seed for the REVIEW_LOG entry.
- `position_value` was NOT modified — the 8-pt lift is search depth alone, no eval re-tuning (per the no-point-chasing rule).

## Next (scoped against what 2b actually moved)
- **Piece 3 = target/opening policies** — primary need: promote-to-disrupt for Budew openings. The eval already values item-lock; the agent just never reaches the gated state where Itchy Pollen is legal. Search-owned target policies (gust target, promote-on-setup, Cursed Blast target) replacing the v0 greedy defaults.
- **Single-seed re-run** for the REVIEW_LOG entry as the regression metric.
- **Piece 2c (mid-tree re-determinization / full ISMCTS)** deliberately deferred — depth + correct adversary did get partial real gains; the residual gap is policy gating, not search width.

No REVIEW_LOG verdict written; held for user/Grok review per the standing rule.
