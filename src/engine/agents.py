#!/usr/bin/env python3
"""
agents.py — the policies that choose actions. NO LLM, NO tokens.

ELI15: an agent looks at the legal moves and picks one. The random agent picks
blindly (a baseline). The greedy agent follows a few common-sense rules. The
real strength later comes from MCTS, but the interface stays identical: given a
state, return an Action.
"""

from __future__ import annotations

import random
from .game import Action, legal_actions
from .state import GameState


class RandomAgent:
    """Picks a uniformly random legal action. The dumb baseline to beat."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def choose(self, state: GameState) -> Action:
        return self.rng.choice(legal_actions(state))


class GreedyAgent:
    """A few sensible priorities, in order:
        1. Attack if it knocks out the opponent's active.
        2. Otherwise build the board: bench Basics, attach energy.
        3. Attack for the most damage available.
        4. Pass.
    Still tokenless — just hand-written priorities. This is the kind of policy
    MCTS later replaces with something that actually searches ahead.
    """

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def choose(self, state: GameState) -> Action:
        acts = legal_actions(state)
        p = state.current
        defender = state.opponent.active

        # 0. use any free ability first (card advantage / setup)
        abilities = [a for a in acts if a.kind == "use_ability"]
        if abilities:
            return abilities[0]

        trainers = [a for a in acts if a.kind == "play_trainer"]

        # 0a. Rare Candy is an evolve-enabler — play it eagerly.
        for a in trainers:
            if p.hand[a.hand_index].name == "Rare Candy":
                return a

        # 0b. develop the bench via search items early (more evolution targets)
        for a in trainers:
            name = p.hand[a.hand_index].name
            if name == "Buddy-Buddy Poffin" and len(p.bench) < 3:
                return a

        # 0c. evolve whenever possible — almost always strong.
        evolves = [a for a in acts if a.kind == "evolve"]
        if evolves:
            return evolves[0]

        attacks = [a for a in acts if a.kind == "attack"]

        # 1. lethal attack?
        if defender is not None:
            for a in attacks:
                atk = p.active.card.attacks[a.attack_index]
                dmg = atk.damage
                for wtype, _ in defender.card.weaknesses:
                    if p.active.card.types and wtype == p.active.card.types[0]:
                        dmg *= 2
                if dmg >= defender.remaining_hp:
                    return a

        # 1b. play a Stadium when one is available. It's a free action that doesn't
        # end the turn, and it's only OFFERED when it isn't already our same-name
        # Stadium in play (so this can't thrash). This establishes a beneficial
        # Stadium — e.g. Battle Cage to deny the opponent's Bench spread (Phantom
        # Dive / Cursed Blast) — and bumps an opponent's Stadium out. Without this
        # branch a greedy player never plays its Stadiums, so Battle Cage (and the
        # whole Stadium war) would be silently inert in every game.
        stadiums = [a for a in acts if a.kind == "play_stadium"]
        if stadiums:
            return stadiums[0]

        # 2. develop board early: bench, then attach energy
        # draw with a Supporter if the hand is running low
        if len(p.hand) <= 3:
            for a in trainers:
                if p.hand[a.hand_index].name == "Cheren":
                    return a
        benches = [a for a in acts if a.kind == "play_basic"]
        if benches and len(p.bench) < 3:
            return self.rng.choice(benches)
        attaches = [a for a in acts if a.kind == "attach_energy"]
        if attaches:
            # prefer attaching to the active
            active_attaches = [a for a in attaches if a.target_index == -1]
            return (active_attaches or attaches)[0]

        # 3. best available attack
        if attacks:
            return max(attacks, key=lambda a: p.active.card.attacks[a.attack_index].damage)

        # 4. nothing useful
        return Action(kind="pass")
