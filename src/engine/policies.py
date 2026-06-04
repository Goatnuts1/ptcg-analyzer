#!/usr/bin/env python3
"""
policies.py — search-owned target policies (piece 3).

These replace three v0 "greedy default" target choices that fire constantly in
the matchup (Boss's Orders gust, Cursed Blast self-KO, Phantom Dive bench
spread). Each policy is a PURE FUNCTION OF PUBLIC BOARD STATE — it never reads
the opponent's hidden hand, deck order, or prize contents, so PIMC integrity is
preserved. No eval weights are touched.

HOW THEY PLUG IN (see docs/PIECE3_target_policies.md):
  - GameState.targeting_policy holds the active policy (default None).
  - The three v0 helpers in effects.py consult it when set, else fall back to v0.
  - MCTSAgent attaches a SearchPolicy at the top of choose(); start_turn clears
    it at the turn boundary, so Greedy/Random reference agents stay v0 and the
    policy never leaks across the turn boundary into the opponent's effects.

The effect hooks are DUCK-TYPED (getattr / method call) — effects.py does not
import this module, avoiding an import cycle.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .state import InPlayPokemon, PlayerState
from .game import can_pay_cost
from .effects import _apply_weakness_resistance


# Engine pieces whose loss is a hard-to-replace setback (evolved draw/search
# engines). Board-fact allowlist, NOT a heuristic — expanding to a new archetype
# means adding a name here WITH a test pinning the pick (see design doc §2 / the
# Sanity caveats). Sourced from the current tournament lists.
ENGINE_PIECE_NAMES = frozenset({
    "Dudunsparce",   # Charizard list's core draw engine (evolved; Run Away Draw)
    "Fan Rotom",     # search engine
})


def _best_affordable_damage(attacker: Optional[InPlayPokemon]) -> int:
    """Highest base damage among the attacker's attacks it can currently pay for.
    Variable-damage attacks (suffix '×') are skipped — we can't model their total
    here, and over-claiming would inflate gust value. '+' attacks count at base
    (a conservative floor)."""
    if attacker is None:
        return 0
    best = 0
    for atk in attacker.card.attacks:
        if atk.damage_suffix in ("", "+") and can_pay_cost(attacker, atk.cost):
            best = max(best, atk.damage)
    return best


class TargetingPolicy:
    """Interface. A policy method returning None means 'no opinion — use v0'."""

    def gust_target(self, state, me: PlayerState, opp: PlayerState,
                    attacker: Optional[InPlayPokemon]) -> Optional[InPlayPokemon]:
        return None

    def cursed_blast_target(self, state, me: PlayerState, opp: PlayerState,
                            dmg: int) -> Optional[InPlayPokemon]:
        return None

    def phantom_dive_spread(self, state, me: PlayerState, opp: PlayerState,
                            counters: int) -> Optional[List[Tuple[InPlayPokemon, int]]]:
        return None


class V0Policy(TargetingPolicy):
    """The current engine behavior, made explicit (for ablation/testing). Attaching
    it is equivalent to attaching no policy at all."""
    # All methods inherit the None ('use v0') default from TargetingPolicy.
    pass


class SearchPolicy(TargetingPolicy):
    """The piece-3 policies. Public-info pure functions; reuse the engine's own
    weakness math rather than duplicating it."""

    # -- policy #1: gust ----------------------------------------------------- #
    def gust_target(self, state, me, opp, attacker):
        bench = opp.bench
        if not bench:
            return None
        best_dmg = _best_affordable_damage(attacker)
        src_card = attacker.card if attacker else None

        koable = []
        for m in bench:
            dealt = _apply_weakness_resistance(src_card, m, best_dmg)
            if best_dmg > 0 and dealt >= m.remaining_hp:
                koable.append(m)

        if koable:
            # (a) a KO this turn, tie-broken by (b) most prizes, then most energy
            # attached (deny a turn of charge-up), then lowest HP (stable).
            pick = max(koable, key=lambda m: (m.card.gives_up_prizes,
                                              m.energy_count(),
                                              -m.remaining_hp))
            # Mechanism marker (counted by matchup.py). Only the real played
            # action's emit lands in the kept log; search runs on dropped-log clones.
            state.emit(f"gust policy: KO target {pick.card.name}")
            return pick
        # (c) no KO available — fall back to v0 (lowest HP). Never worse than v0.
        return min(bench, key=lambda m: m.remaining_hp)

    # -- policy #2: Cursed Blast self-KO target ------------------------------ #
    def cursed_blast_target(self, state, me, opp, dmg):
        koable = [m for m in opp.all_in_play() if 0 < m.remaining_hp <= dmg]
        if not koable:
            return None   # nothing KO-able → let v0 (_pick_ko_target) handle it
        # (a) most prizes (v0), (b) NEW engine-value tie-break, (c) lowest HP.
        pick = max(koable, key=lambda m: (m.card.gives_up_prizes,
                                          self._engine_value(m),
                                          -m.remaining_hp))
        if self._engine_value(pick) > 0:
            state.emit(f"cursed-blast policy: engine KO {pick.card.name}")
        return pick

    @staticmethod
    def _engine_value(mon: InPlayPokemon) -> int:
        """Board-fact-only score of how costly this mon's loss is to the opponent's
        engine. No hidden info — literal in-play facts."""
        score = 0
        if mon.card.name in ENGINE_PIECE_NAMES:
            score += 3                      # non-replaceable evolved draw/search engine
        if mon.tool is not None:
            score += 2                      # deny the attached Tool (e.g. spread-denial)
        if mon.card.abilities:
            score += 1                      # in-play ability engine (TRW-relevant etc.)
        return score

    # -- policy #3: Phantom Dive bench spread -------------------------------- #
    def phantom_dive_spread(self, state, me, opp, counters):
        bench = [m for m in opp.bench if not m.is_knocked_out]
        if len(bench) < 2:
            return None   # can't set up multi-target pressure → v0 pile-drive

        # Model next-turn bench pressure as the recurring spread (Phantom Dive
        # spreads `counters` again next turn). A benched mon becomes a next-turn
        # KO threat if we bring it within `followup` of a knockout this turn.
        followup = counters * 10

        # Greedy knapsack: fund the cheapest-to-threaten mons first to maximize
        # the COUNT of next-turn threats. cost = counters needed to reach range,
        # without over-filling (an immediate KO would waste the deferred threat).
        plans = []
        for m in bench:
            need_dmg = max(0, m.remaining_hp - followup)
            cost = (need_dmg + 9) // 10            # counters (10 dmg each)
            plans.append((cost, m))
        plans.sort(key=lambda cm: cm[0])

        budget = counters
        dist: List[Tuple[InPlayPokemon, int]] = []
        threats = 0
        for cost, m in plans:
            if cost <= budget:
                budget -= cost
                threats += 1
                if cost > 0:
                    dist.append((m, cost))
            # mons already in range (cost 0) count as threats for free

        if threats < 2:
            return None   # didn't secure ≥2 deferred threats → fall back to v0
        # If every threat was already in range (dist empty) there's nothing to
        # place differently from v0; let v0 run so we don't no-op the spread.
        if not dist:
            return None
        state.emit(f"phantom-dive policy: multi-setup ({threats} threats)")
        return dist
