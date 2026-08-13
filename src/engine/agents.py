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
from . import effects as fx
from .game import Action, legal_actions, apply_action
from .state import GameState
from .evaluation import position_value

# v0 greedy Trainer policy (name-based; a real policy is MCTS's job). Without a
# GENERAL branch here, every search/draw Trainer we implement is inert in live
# games — only the hardcoded few would ever be played. These lists keep the
# consistency engine actually firing so the decks function and rollouts are sane.
_CONSISTENCY_ITEMS = ("Poké Pad", "Nest Ball", "Night Stretcher", "Energy Retrieval",
                      # core-stabilization search/recovery staples
                      "Poké Ball", "Master Ball", "Dusk Ball", "Pokégear 3.0",
                      "Energy Switch", "Energy Recycler", "Sacred Ash")
# Disruption / comeback Items greedy plays when offered (their can_play already
# gates them: Crushing Hammer needs opp Energy; Unfair Stamp needs a KO last turn).
_UTILITY_ITEMS = ("Crushing Hammer", "Unfair Stamp", "Counter Catcher", "Pokémon Catcher")
_DRAW_SUPPORTERS = ("Lillie's Determination", "Judge", "Cheren",
                    "Carmine", "Lacey", "Kofu", "Hassel", "Drayton")
_SEARCH_SUPPORTERS = ("Hilda", "Dawn", "Crispin", "Arven",
                      "Cyrano", "Colress's Tenacity", "Lana's Aid")
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

        # 0c'. Grand Tree's free once-per-turn deck-search evolution. Card-POSITIVE
        # (it pulls the Stage 1, and often the Stage 2, straight out of the deck for
        # nothing), so it ranks with the normal evolve branch. Without this the ACE SPEC
        # Stadium's whole reason for being in the list would be inert under greedy —
        # the same inertness bug the general Trainer fallbacks exist to prevent.
        stadium_evolves = [a for a in acts if a.kind == "stadium_evolve"]
        if stadium_evolves:
            return stadium_evolves[0]

        # 0c''. Team Rocket's Factory's free once-per-turn draw 2. Card-POSITIVE with no
        # cost at all (legal_actions already checked its "you played a Team Rocket
        # Supporter this turn" condition and that there are cards to draw), so it ranks
        # with the other free upside — unlike Prism Tower's card-NEGATIVE discard-2-draw-1
        # below, which greedy has to be choosy about. Without this branch the Stadium
        # would be inert in every greedy game (the recurring inertness bug).
        stadium_factory = [a for a in acts if a.kind == "stadium_factory"]
        if stadium_factory:
            return stadium_factory[0]

        # 0c'''. Academy at Night's free once-per-turn "put a card from your hand on top
        # of your deck". Card-NEGATIVE in a vacuum (you bury a card you could have used),
        # so greedy only takes it for the one line the Stadium is actually played for:
        # planting Seek Inspiration copy-fodder when the Active is Slowking. The planted
        # card is the hand's highest seek-value non-Rule-Box attacker, and only when that
        # value beats what Slowking would expect blind off the top (>= 130 clears every
        # toolbox piece — Metallic Hammer 150, Trifrost 250, Destined Fight 400 — while
        # refusing to bury a Slowpoke). Without this branch the Stadium's activated
        # ability would be inert in every greedy game (the recurring inertness bug).
        academy = [a for a in acts if a.kind == "stadium_academy"]
        if academy and p.active is not None and p.active.card.name == "Slowking":
            def _plant_value(a):
                c = p.hand[a.hand_index]
                if not (c.is_pokemon and not fx._has_rule_box(c)) or not c.attacks:
                    return 0
                return max(fx.seek_value(c, atk) for atk in c.attacks)
            best = max(academy, key=_plant_value)
            if _plant_value(best) >= 130:
                return best

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

        # 1b'. Prism Tower's free once-per-turn discard-2-draw-1. It is card-NEGATIVE
        # (−2 +1), so greedy only takes it with a hand big enough to spare the cards —
        # otherwise it would grind its own hand away every turn. Without this branch the
        # Stadium's activated ability would be silently inert in every greedy game, the
        # same inertness bug the general Item/Supporter fallbacks exist to prevent.
        if len(p.hand) >= 5:
            stadium_draws = [a for a in acts if a.kind == "stadium_draw"]
            if stadium_draws:
                return stadium_draws[0]

        # 1b''. Mystery Garden's free once-per-turn "discard an Energy from hand, then
        # draw until your hand size equals your Psychic-Pokémon count". legal_actions
        # already refuses to offer it unless it draws at least 1, which is only
        # card-NEUTRAL (−1 Energy, +1 card); greedy holds out for a strictly positive
        # trade, i.e. a hand still below the target after paying. Without this branch the
        # Stadium's activated ability would be inert in every greedy game — the same
        # inertness bug the general Trainer fallbacks exist to prevent.
        garden = [a for a in acts if a.kind == "stadium_garden"]
        if garden and len(p.hand) < fx.mystery_garden_target(state, p):
            return garden[0]

        # 1c. consistency Items — card-neutral/positive search & recovery that
        # develops the game. (Generalized: any new search/draw Item fires here.)
        for a in trainers:
            name = p.hand[a.hand_index].name
            if name in _CONSISTENCY_ITEMS or name in _UTILITY_ITEMS:
                return a
            if name == "Ultra Ball" and len(p.hand) > 4:    # afford the 2-card discard
                return a

        # 1c'. GENERAL Item fallback — play any other offered Item. The engine only
        # offers an Item whose can_play says it does something, and playing it pops
        # it from hand (no re-offer loop). Without this, every newly-implemented
        # Item not named above would sit in hand forever (the recurring inertness
        # bug). Supporters are excluded here — they're handled (1-per-turn) below.
        for a in trainers:
            c = p.hand[a.hand_index]
            if c.is_item and not c.is_supporter:
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

        # 1d'. GENERAL Supporter fallback — play any other offered Supporter (still
        # 1/turn; legal_actions hides them after one is played). Future-proofs new
        # Supporters against the inertness bug. Held BELOW the named draw/search ones
        # so the well-understood lines take priority.
        for a in trainers:
            c = p.hand[a.hand_index]
            if c.is_supporter:
                return a

        # 1e. attach a Pokémon Tool when one is available (free setup; otherwise
        # Air Balloon / Powerglass would sit in hand, never played).
        tools = [a for a in acts if a.kind == "attach_tool"]
        if tools:
            return tools[0]

        # 2. develop board early: bench, then attach energy
        benches = [a for a in acts if a.kind == "play_basic"]
        if benches and len(p.bench) < 3:
            # Shaymin (DRI) first: its Flower Curtain only works FROM the Bench, so a
            # pilot holding it always benches it before random engine pieces. Scoped to
            # the one card — every other Basic keeps the existing random pick.
            for a in benches:
                if p.hand[a.hand_index].name == "Shaymin (DRI)":
                    return a
            return self.rng.choice(benches)
        attaches = [a for a in acts if a.kind == "attach_energy"]
        if attaches:
            # 2a'. Seek Inspiration fuel first: a Slowking still short of its [P][C]
            # outranks the default attach-to-Active — the whole archetype runs off
            # that one attack, and without this the Active (often Latias ex) soaks
            # every attachment while Slowking sits dry on the Bench (observed in
            # livefire). Narrow scope: only a Slowking, only until it holds 2.
            for a in attaches:
                mon = p.active if a.target_index == -1 else p.bench[a.target_index]
                if (mon is not None and mon.card.name == "Slowking"
                        and mon.energy_count() < 2):
                    return a
            # prefer attaching to the active
            active_attaches = [a for a in attaches if a.target_index == -1]
            return (active_attaches or attaches)[0]

        # 2b. Slowking promotion: the Seek Inspiration engine only runs from the
        # Active Spot, but greedy has no general retreat logic, so a benched Slowking
        # would sit there until Boss's Orders drags it up to die (observed in livefire).
        # Narrowly scoped on purpose: retreat ONLY into a benched Slowking that can
        # already pay Seek Inspiration's [P][C], and only while the current Active is
        # not itself a Slowking — so it can't thrash, and no other archetype's play
        # changes. legal_actions already gated the retreat's affordability.
        if p.active is not None and p.active.card.name != "Slowking":
            for a in acts:
                if a.kind == "retreat":
                    mon = p.bench[a.target_index]
                    if (mon.card.name == "Slowking"
                            and mon.energy_count() >= 2
                            and any("Psychic" in t for e in mon.energy
                                    for t in e.types)):
                        return a

        # 3. best available attack. Value = printed damage, with ONE exception:
        # Slowking's Seek Inspiration (printed 0) is valued at the seek_value of the
        # top card of the deck when that card is KNOWN GOOD — i.e. this player planted
        # it there with Academy at Night this turn (0c''' above). Blind, it keeps its
        # printed 0 and loses to Super Psy Bolt's flat 120, which is the honest
        # greedy read of an unknown top card. This is player-legal information: you
        # know what you just put on top of your own deck.
        def _attack_value(a):
            atk = p.active.card.attacks[a.attack_index]
            if (atk.name == "Seek Inspiration" and p.active.card.name == "Slowking"
                    and p.stadium_academy_used_this_turn and p.deck):
                top = p.deck[0]
                if top.is_pokemon and not fx._has_rule_box(top) and top.attacks:
                    return max(fx.seek_value(top, t) for t in top.attacks)
            return atk.damage
        if attacks:
            return max(attacks, key=_attack_value)

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
