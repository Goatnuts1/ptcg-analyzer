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
from .game import Action, legal_actions, apply_action
from .state import GameState
from .evaluation import position_value

# v0 greedy Trainer policy (name-based; a real policy is MCTS's job). Without a
# GENERAL branch here, every search/draw Trainer we implement is inert in live
# games — only the hardcoded few would ever be played. These lists keep the
# consistency engine actually firing so the decks function and rollouts are sane.
_CONSISTENCY_ITEMS = ("Poké Pad", "Nest Ball", "Night Stretcher", "Energy Retrieval")
# Disruption / comeback Items greedy plays when offered (their can_play already
# gates them: Crushing Hammer needs opp Energy; Unfair Stamp needs a KO last turn).
_UTILITY_ITEMS = ("Crushing Hammer", "Unfair Stamp", "Counter Catcher")
_DRAW_SUPPORTERS = ("Lillie's Determination", "Judge", "Cheren")
_SEARCH_SUPPORTERS = ("Hilda", "Dawn", "Crispin", "Arven")
# Boss's Orders (gust) is situational — greedy can't judge the KO it sets up, so it
# sits last and MCTS owns the timing. (§5 deviation.)
_OTHER_SUPPORTERS = ("Boss's Orders",)


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

        # 1c. consistency Items — card-neutral/positive search & recovery that
        # develops the game. (Generalized: any new search/draw Item fires here.)
        for a in trainers:
            name = p.hand[a.hand_index].name
            if name in _CONSISTENCY_ITEMS or name in _UTILITY_ITEMS:
                return a
            if name == "Ultra Ball" and len(p.hand) > 4:    # afford the 2-card discard
                return a

        # 1d. one Supporter per turn: refill the hand when low, else set up. (Legal
        # actions already hides Supporters once one is played this turn.)
        supporter_order = (_DRAW_SUPPORTERS + _SEARCH_SUPPORTERS + _OTHER_SUPPORTERS
                           if len(p.hand) <= 4 else
                           _SEARCH_SUPPORTERS + _DRAW_SUPPORTERS + _OTHER_SUPPORTERS)
        for want in supporter_order:
            for a in trainers:
                c = p.hand[a.hand_index]
                if c.name == want and c.is_supporter:
                    return a

        # 1e. attach a Pokémon Tool when one is available (free setup; otherwise
        # Air Balloon / Powerglass would sit in hand, never played).
        tools = [a for a in acts if a.kind == "attach_tool"]
        if tools:
            return tools[0]

        # 2. develop board early: bench, then attach energy
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


class EvalAgent:
    """1-ply lookahead over the effect-aware position_value (POLICY milestone, piece 1).

    For each legal action it clones the state, applies the action, and scores the
    RESULTING position. It picks the highest-scoring result, so an action is worth
    exactly the board it produces — Phantom Dive's bench spread, Budew's Item-lock,
    a Confused Active — with no per-card heuristics and no blindness to effect damage.

    1-ply does NOT yet capture multi-step sequencing (gust-THEN-KO); that's piece 2
    (MCTS using position_value as its leaf evaluation). But bench-spread and disruption
    are 1-ply-visible, so this already expresses most of what greedy missed.
    """

    def __init__(self, rng: random.Random = None):
        self.rng = rng or random.Random()

    def choose(self, state: GameState) -> Action:
        acts = legal_actions(state)
        if not acts:
            return Action(kind="pass")
        me = state.active_index
        best, best_v = None, None
        for a in acts:
            # fresh rng per clone so effects with randomness (flips/shuffles) sample;
            # one sample is enough for a v0 ranking.
            clone = state.clone(fresh_rng=random.Random(self.rng.randrange(1 << 30)))
            try:
                apply_action(clone, a)
            except Exception:
                continue
            v = position_value(clone, me)
            if best_v is None or v > best_v:
                best, best_v = a, v
        return best if best is not None else Action(kind="pass")
