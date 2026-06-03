#!/usr/bin/env python3
"""
evaluation.py — effect-aware position valuation (POLICY MILESTONE, piece 1).

THE IDEA: the greedy agent ranked attacks by *printed damage*, so it was blind to
what effects actually accomplish — Phantom Dive's bench spread, a gust that sets up
a KO, Budew's Item-lock, TRW shutting off a draw engine. The fix is to stop scoring
*actions by their printed number* and instead score the *resulting position*. Then
an action is worth exactly the position it produces — bench pressure, disruption,
prizes and all — with NO per-card heuristics. Phantom Dive is "200 to the Active +
six benched Pokémon closer to KO," because that's what the resulting board shows.

`position_value(state, idx)` is that static evaluation (higher = better for player
`idx`). A 1-ply agent picks the action whose resulting clone scores highest; MCTS
(piece 2) will use it as the rollout-leaf evaluation for multi-turn lookahead.

Weights are deliberately simple and readable — prizes dominate, then damage-toward-KO
(the bench-spread signal), then board/energy, then disruption. Tune against the
Dragapult-vs-Charizard regression matchup, not toward a single published number.
"""

from __future__ import annotations

from .state import GameState, PlayerState

# Coarse weights. Prizes are the win condition, so they dwarf everything; a terminal
# win/loss is effectively infinite.
W_TERMINAL = 100_000.0
W_PRIZE = 100.0          # per prize taken / conceded
W_OPP_DAMAGE = 22.0      # per (fraction-to-KO × prizes) on an OPPONENT Pokémon — bench pressure
W_OWN_DAMAGE = 18.0      # per (fraction-to-KO × prizes) on YOUR Pokémon (you've conceded ground)
W_ENERGY = 2.0           # per attached Energy on your Pokémon (capped) — readiness
W_INPLAY = 0.5           # per Pokémon you have in play — board presence
# Evolution stage value — WITHOUT this a 1-ply agent never evolves (Dreepy->Drakloak
# leaves the in-play count unchanged, so it benches basics forever and never assembles
# an attacker; Phantom Dive then fires 0×). Rewarding stage drives the agent up its
# evolution line toward its real attacker.
W_STAGE = {"Stage 1": 5.0, "Stage 2": 11.0, "MEGA": 11.0}
W_ATTACK_READY = 0.05    # × the best printed damage your Active can currently pay for
W_ITEM_LOCK = 8.0        # opponent can't play Items (Budew) — strong tempo denial
W_NO_RETREAT = 4.0       # opponent can't retreat (Shadow Bind)
W_CONFUSED = 4.0         # opponent's Active is Confused
W_HAND = 0.5             # per card in hand — resources


def _board_damage_pressure(player: PlayerState) -> float:
    """Sum of (damage / HP) × prize-value over `player`'s Pokémon. A benched Pokémon
    at 60/70 HP is worth far more than a fresh one — this is what makes bench spread
    (Phantom Dive, Cursed Blast) show up as real value."""
    total = 0.0
    for m in player.all_in_play():
        hp = m.card.hp or 0
        if hp > 0 and m.damage > 0:
            total += min(1.0, m.damage / hp) * m.card.gives_up_prizes
    return total


def position_value(state: GameState, idx: int) -> float:
    """Static evaluation of the position from player `idx`'s perspective (higher = better)."""
    me = state.players[idx]
    opp = state.players[1 - idx]
    v = 0.0

    # 1. Terminal / near-terminal — prizes are the whole game.
    if len(me.prizes) == 0 or not opp.has_pokemon_in_play():
        v += W_TERMINAL
    if len(opp.prizes) == 0 or not me.has_pokemon_in_play():
        v -= W_TERMINAL
    v += (6 - len(me.prizes)) * W_PRIZE          # prizes you've already taken
    v -= (6 - len(opp.prizes)) * W_PRIZE          # prizes the opponent has taken

    # 2. Damage pressure — the bench-spread signal (closer to KO + more prizes = better).
    v += _board_damage_pressure(opp) * W_OPP_DAMAGE
    v -= _board_damage_pressure(me) * W_OWN_DAMAGE

    # 3. Board development / readiness — energy, presence, evolution stage, and a
    #    ready attacker (an Active that can actually pay for a damaging attack).
    from .game import can_pay_cost      # local import avoids a module cycle
    v += sum(min(m.energy_count(), 3) for m in me.all_in_play()) * W_ENERGY
    v += len(me.all_in_play()) * W_INPLAY
    for m in me.all_in_play():
        for sub in m.card.subtypes:
            if sub in W_STAGE:
                v += W_STAGE[sub]
                break
    if me.active is not None:
        payable = [a.damage for a in me.active.card.attacks if can_pay_cost(me.active, a.cost)]
        if payable:
            v += max(payable) * W_ATTACK_READY

    # 4. Disruption you've imposed (and the reverse imposed on you).
    if opp.cant_play_items:
        v += W_ITEM_LOCK
    if me.cant_play_items:
        v -= W_ITEM_LOCK
    if opp.cant_retreat:
        v += W_NO_RETREAT
    if me.cant_retreat:
        v -= W_NO_RETREAT
    if opp.active is not None and opp.active.confused:
        v += W_CONFUSED
    if me.active is not None and me.active.confused:
        v -= W_CONFUSED

    # 5. Resources.
    v += len(me.hand) * W_HAND
    return v
