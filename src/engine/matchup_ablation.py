#!/usr/bin/env python3
"""
matchup_ablation.py — per-policy ablation for piece 3 (R19 follow-up).

WHY THIS EXISTS
---------------
R19's symmetric ON-vs-OFF A/B (docs/PIECE3_REGRESSION_RESULT.md) showed:
    OFF (v0):    55.4% Dragapult-favored (n=240 across 2 seeds)
    ALL_ON:      52.1% Dragapult-favored  (-3.3pt, same -4 games on EACH seed)
Mechanism counts moved (gust→KO 42, cursed→engine 26, phantom→multi 14 per 120),
band did NOT — it drifted ~3pt toward 50/50. Per piece-3's own discipline:
*surface, do not tune.* This runner is the disentangling experiment.

FACTUAL CORRECTION (load-bearing for interpreting results)
----------------------------------------------------------
PIECE3_REGRESSION_RESULT.md attributes Cursed Blast to "Charizard-side tech
(Dusknoir/Dusclops)." That's INVERTED.

Verify in `src/engine/decks.py`:
    TOURNAMENT_DRAGAPULT includes ("Duskull", 2), ("Dusclops", 2), ("Dusknoir", 1).
    TOURNAMENT_CHARIZARD_XY does NOT contain any Duskull-line cards.

The engine-piece allowlist {Dudunsparce, Fan Rotom} is Charizard-side targets.
So the 26 cursed→engine events are DRAGAPULT firing Cursed Blast and sniping
CHARIZARD's draw/search engine, not the other way around. The R19 hypothesis
"engine-kill helps the underdog" was based on a wrong premise about which side
owned the attack.

CORRECTED HYPOTHESIS SPACE the ablation is designed to disentangle:

  H1 — engine-piece scoring over-weights replaceable targets. Charizard runs
       3 Dunsparce + 2 Dudunsparce. Killing the in-play Dudunsparce forces
       re-evolution from a spare Dunsparce (tempo cost) — NOT engine destruction.
       So Dragapult spends a Cursed Blast self-KO on a less-impactful kill than
       v0's coincidental lowest-HP target. The +3 engine score over-weighted the
       marginal benefit. Predicts: CURSED_ONLY arm carries (some of) the -3.3pt.

  H2 — Phantom Dive's ratified tempo-trade doesn't pay. The spec trades 1
       immediate KO for ≥2 deferred next-turn threats; if the deferred threats
       don't convert before the game turns, that's lost tempo for the favored
       side. Predicts: PHANTOM_ONLY arm carries (some of) the -3.3pt.

  H3 — Gust target change has hidden costs. Less likely; the gust policy is
       strictly KO-securing where v0 was KO-agnostic. But possible if KO-secured
       gust targets are systematically lower-prize than v0's lowest-HP picks
       were stumbling into. Predicts: GUST_ONLY arm carries (some of) the -3.3pt.

  H4 — Symmetric application alone compresses the matchup, regardless of which
       policy. Predicts: each single-policy arm is ~neutral, only ALL_ON drops.
       This would validate piece-3's "out of scope" prediction that the remaining
       sim↔reality gap lives in the deferred pieces (2c full ISMCTS, hidden-hand-
       aware eval).

WHAT THIS RUNS
--------------
Five arms, SYMMETRIC (both agents use the same policy), SAME seeds across arms
so the comparison is apples-to-apples:
    OFF           — V0Policy (baseline; equivalent to no policy attached)
    GUST_ONLY     — gust policy ON; cursed + phantom OFF (return None → v0)
    CURSED_ONLY   — cursed policy ON; gust + phantom OFF
    PHANTOM_ONLY  — phantom policy ON; gust + cursed OFF
    ALL_ON        — full SearchPolicy (the R19 ON arm)

Reports per arm: Dragapult win%, drag/char/tie split, mechanism-marker counts,
and the full LINE_MARKERS table for cross-arm line-fire comparison.

WHAT THIS DOESN'T DO (deliberately)
-----------------------------------
- Asymmetric A/B (Dragapult policy ON, Charizard OFF, or reverse). If the
  symmetric ablation isolates a single policy as the culprit, asymmetric A/B
  is the right next experiment to confirm side-attribution. Not bundled here
  to keep this drop focused.
- Larger N. n=120/arm at plies=2 is ~1 SE. Bigger N would tighten the CI but
  the standing rule applies: characterize the effect, do NOT chase the band.

CLI
---
    python3 -m src.engine.matchup_ablation --games 60 --iters 100 --plies 2 --seed 0
        # default — runs all 5 arms (~8 min at 0.8s/game)
    python3 -m src.engine.matchup_ablation --arms OFF,CURSED_ONLY,ALL_ON
        # subset (faster sanity check)
    python3 -m src.engine.matchup_ablation --games 30
        # smaller sample for first-pass orientation
"""

from __future__ import annotations

import argparse
import random

from .cards import CardDB
from .decks import load_tournament_deck
from .mcts import MCTSAgent
from .policies import SearchPolicy, V0Policy
from .game import setup_game, start_turn
from .run import finish_game, _resolve_tie
from .matchup import LINE_MARKERS


# --------------------------------------------------------------------------- #
# Policy variants for the per-policy ablation.
# Each subclasses SearchPolicy and overrides the OTHER two methods to return
# None — the TargetingPolicy "fall back to v0 for this one" signal. So
# GustOnly = real gust policy, v0 cursed_blast, v0 phantom_dive.
# --------------------------------------------------------------------------- #
class _GustOnly(SearchPolicy):
    def cursed_blast_target(self, *a, **k): return None
    def phantom_dive_spread(self, *a, **k): return None


class _CursedOnly(SearchPolicy):
    def gust_target(self, *a, **k): return None
    def phantom_dive_spread(self, *a, **k): return None


class _PhantomOnly(SearchPolicy):
    def gust_target(self, *a, **k): return None
    def cursed_blast_target(self, *a, **k): return None


ARMS = {
    "OFF":          V0Policy,        # baseline — equivalent to attaching nothing
    "GUST_ONLY":    _GustOnly,
    "CURSED_ONLY":  _CursedOnly,
    "PHANTOM_ONLY": _PhantomOnly,
    "ALL_ON":       SearchPolicy,    # the R19 ON arm
}


def _make_agent(policy_cls, iters, plies, rng):
    """MCTSAgent with the chosen policy attached.

    We override `agent._policy` post-init instead of plumbing a `policy=` kwarg
    through MCTSAgent.__init__ — keeps mcts.py untouched, and the agent's
    `_policy` attribute is the only thing that drives policy choice (verified at
    mcts.py:191/195). Safe.
    """
    agent = MCTSAgent(iterations=iters, rollout="eval", rng=rng, search_plies=plies)
    agent._policy = policy_cls()
    return agent


def run_arm(policy_cls, games_per_orient, iters, plies, seed):
    """One ablation arm: both agents use `policy_cls`, mirrored seats. Same seed
    schedule as `matchup.run_matchup` so cross-arm comparisons line up."""
    db = CardDB.from_pool("data/standard_pool.json")
    drag_wins = char_wins = ties = 0
    line_counts = {name: 0 for name in LINE_MARKERS}

    for orient in (0, 1):
        for i in range(games_per_orient):
            base = seed + orient * 100000 + i
            d_drag = load_tournament_deck(db, "dragapult")
            d_char = load_tournament_deck(db, "charizard_xy")
            if orient == 0:
                deck_a, deck_b, drag_seat = d_drag, d_char, 0
            else:
                deck_a, deck_b, drag_seat = d_char, d_drag, 1

            st = setup_game(deck_a, deck_b, seed=base, db=db)
            start_turn(st)
            agent_a = _make_agent(policy_cls, iters, plies, random.Random(base))
            agent_b = _make_agent(policy_cls, iters, plies, random.Random(base + 50000))
            finish_game(st, agent_a, agent_b)
            _resolve_tie(st)

            if st.winner is None:
                ties += 1
            elif st.winner == drag_seat:
                drag_wins += 1
            else:
                char_wins += 1

            log = "\n".join(st.log)
            for name, marker in LINE_MARKERS.items():
                if marker in log:
                    line_counts[name] += 1

    total = drag_wins + char_wins
    games = 2 * games_per_orient
    return {
        "drag_wins": drag_wins, "char_wins": char_wins, "ties": ties,
        "winpct": 100 * drag_wins / total if total else 0,
        "games": games, "line_counts": line_counts,
    }


def main():
    ap = argparse.ArgumentParser(description="piece-3 per-policy ablation")
    ap.add_argument("--games", type=int, default=60,
                    help="games PER orientation (×2 = total per arm)")
    ap.add_argument("--iters", type=int, default=100, help="MCTS iterations")
    ap.add_argument("--plies", type=int, default=2, help="MCTS search_plies")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--arms", default="all",
                    help="comma-separated arm names, or 'all'. "
                         f"Available: {', '.join(ARMS)}")
    args = ap.parse_args()

    if args.arms == "all":
        arms_to_run = list(ARMS.keys())
    else:
        arms_to_run = [a.strip().upper() for a in args.arms.split(",")]

    games_per_arm = 2 * args.games
    print(f"\nPiece-3 per-policy ablation — mcts-eval, plies={args.plies}, iters={args.iters}")
    print(f"  {games_per_arm} games per arm (mirrored), seed={args.seed}")
    print(f"  Arms: {', '.join(arms_to_run)}")
    print(f"  Estimated runtime: ~{0.8 * games_per_arm * len(arms_to_run) / 60:.1f} min @ ~0.8s/game\n")

    results = {}
    for arm in arms_to_run:
        if arm not in ARMS:
            print(f"  ! unknown arm: {arm} (skipping)")
            continue
        print(f"  running arm: {arm} ...", flush=True)
        results[arm] = run_arm(ARMS[arm], args.games, args.iters, args.plies, args.seed)

    if not results:
        print("\nNo arms ran. Check --arms argument.")
        return

    # --- headline summary ---
    print("\n" + "=" * 84)
    print("PIECE-3 ABLATION — SYMMETRIC, SAME SEED, mcts-eval/plies=2")
    print("=" * 84)
    off = results.get("OFF")
    print(f"{'arm':<14} {'win%':>7} {'Δ vs OFF':>10} {'drag/char/tie':>17} "
          f"{'gust→KO':>9} {'crsd→eng':>10} {'phan→mlti':>11}")
    print("-" * 84)
    for arm, r in results.items():
        gust_ko    = r["line_counts"].get("gust→KO secured (policy)", 0)
        curse_eng  = r["line_counts"].get("Cursed Blast→engine KO (policy)", 0)
        phant_mult = r["line_counts"].get("Phantom Dive→multi-setup (policy)", 0)
        delta = ""
        if off is not None and arm != "OFF":
            d = r["winpct"] - off["winpct"]
            delta = f"{d:+.1f}pt"
        print(f"{arm:<14} {r['winpct']:>6.1f}% {delta:>10} "
              f"{r['drag_wins']:>4}/{r['char_wins']:<3}/{r['ties']:<3}  "
              f"{gust_ko:>9} {curse_eng:>10} {phant_mult:>11}")

    # --- full line-fire matrix ---
    print("\nFull line-fire matrix (count per arm):")
    header = f"{'line':<36}" + "".join(f"{a:>14}" for a in results)
    print(header)
    print("-" * len(header))
    for ln in LINE_MARKERS:
        row = "".join(f"{r['line_counts'][ln]:>14}" for r in results.values())
        print(f"{ln:<36}{row}")

    # --- READING GUIDE -------------------------------------------------- #
    print("\nReading guide (per the corrected hypothesis space in this file's docstring):")
    print("  - If ONE arm's Δ is close to the ALL_ON Δ and the others are ~0,")
    print("    that's the policy carrying the regression. Revisit that policy's spec.")
    print("  - If all three single arms are mildly negative and they ~sum to ALL_ON's Δ,")
    print("    symmetric application of sharper targeting compresses the matchup —")
    print("    validates piece-3's 'out of scope' prediction (gap lives in 2c / hidden-hand eval).")
    print("  - Same-seed comparison: each arm runs the same game sequence; differences are")
    print("    causally attributable to the policy, not seed noise.")
    print("\n(Verdict held — surface findings; do NOT tune.)\n")


if __name__ == "__main__":
    main()
