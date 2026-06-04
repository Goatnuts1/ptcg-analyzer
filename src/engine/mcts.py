#!/usr/bin/env python3
"""
mcts.py — a search-based agent. Still NO LLM, NO tokens: it uses the engine to
explore hypothetical lines and keeps the ones that win most.

WHY THIS IS THE HARD PART (and how we handle it):

1. STATE CLONING. Search means "try a move, see what happens, undo it" thousands
   of times. We clone the state (GameState.clone) — cheap because Card objects
   are immutable and shared; only the mutable wrappers are copied.

2. HIDDEN INFORMATION. Pokémon is imperfect-information: you can't see your
   opponent's hand, your own deck order, or which cards are prized. Naive search
   that "reads" the shuffled deck would CHEAT and report fantasy win rates. We
   fix this with DETERMINIZATION: before each simulation we sample one concrete
   world consistent with what the acting player legitimately knows (their own
   hand + everyone's public board/discard), reshuffling all hidden zones. This is
   Perfect-Information Monte Carlo (PIMC) — search many plausible worlds, average.

3. SCOPE OF THE TREE. `search_plies` controls how many turn-segments the tree
   spans before the leaf is scored:
     - search_plies = 1  -> single-turn tree (the v1 behavior): branch only on the
       acting player's own turn, then evaluate/rollout. Backward compatible.
     - search_plies >= 2 -> MULTI-TURN (piece 2b): the tree continues ACROSS the
       turn boundary into the opponent's turn (and back), so search can value
       lines whose payoff lands a turn later — out-sequencing the stadium war,
       Budew promote-to-disrupt, etc. Two correctness requirements come with this:
         (a) NEGAMAX backprop — a node's statistic is value FROM THE PERSPECTIVE OF
             THE PLAYER WHO CHOSE IT, so the opponent's nodes are optimized for the
             OPPONENT, not for us. Without this the search models an opponent who
             helps us win and reports an inflated, believable-looking number.
         (b) NO-LEAK determinization is preserved: we sample ONE world per
             iteration from the root player's legitimate knowledge; the opponent's
             in-tree draws come off THAT determinized deck. Diversity comes from
             re-sampling per iteration. (Full mid-tree re-determinization / ISMCTS
             is a later 2c; determinized-root multi-ply is correct PIMC and is what
             the Budew/stadium-war gap actually needs — depth + a real opponent.)
"""

from __future__ import annotations

import math
import random
from typing import Optional

from .state import GameState, InPlayPokemon, PlayerState, Phase
from .game import (Action, PASS, legal_actions, apply_action,
                   start_turn, end_turn, check_win, MAX_TURNS)
from .agents import GreedyAgent, RandomAgent
from .evaluation import position_value
from .policies import SearchPolicy


def _logistic(x: float, scale: float = 60.0) -> float:
    """Squash a signed position_value into a [0,1] 'win-ish' value for backprop."""
    try:
        return 1.0 / (1.0 + math.exp(-x / scale))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# --------------------------------------------------------------------------- #
# Determinization — sample a world consistent with the acting player's knowledge
# --------------------------------------------------------------------------- #
def determinize(state: GameState, root_index: int, rng: random.Random) -> GameState:
    """Return a clone with hidden zones reshuffled into one plausible arrangement.

    Known and preserved: the root player's hand, both players' in-play Pokémon
    (with damage/energy), and both discards. Hidden and reshuffled: deck order and
    prize contents for both players, and the OPPONENT's hand (size preserved).
    """
    s = state.clone(fresh_rng=random.Random(rng.random()))
    for i, p in enumerate(s.players):
        if i == root_index:
            # own hand is known; only deck + prizes are hidden
            pool = list(p.deck) + list(p.prizes)
            rng.shuffle(pool)
            prize_n = len(p.prizes)
            p.prizes = [pool.pop() for _ in range(prize_n)]
            p.deck = pool
        else:
            # opponent's hand is hidden too; reshuffle hand + deck + prizes
            hand_n = len(p.hand)
            prize_n = len(p.prizes)
            pool = list(p.hand) + list(p.deck) + list(p.prizes)
            rng.shuffle(pool)
            p.hand = [pool.pop() for _ in range(hand_n)]
            p.prizes = [pool.pop() for _ in range(prize_n)]
            p.deck = pool
    return s


# --------------------------------------------------------------------------- #
# Tree node
# --------------------------------------------------------------------------- #
class _Node:
    # `chooser` = the player who MADE the move leading into this node (i.e. the
    # actor at the parent). Its statistic is stored from `chooser`'s perspective,
    # so a parent maximizing child means maximizes its OWN value (negamax).
    __slots__ = ("parent", "key", "children", "visits", "wins", "chooser")

    def __init__(self, parent, key, chooser=None):
        self.parent = parent
        self.key = key                  # semantic key of the action that led here
        self.children: dict = {}
        self.visits = 0
        self.wins = 0.0
        self.chooser = chooser


def _akey(a: Action):
    return (a.kind, a.hand_index, a.target_index, a.attack_index)


def _semantic_key(state: GameState, a: Action):
    """Collapse actions that are functionally identical so search isn't wasted on
    them: playing the 2nd vs 3rd copy of a card, or attaching the same energy type
    to the same target, are the SAME decision. Keyed off the current player's hand.
    """
    p = state.current
    if a.kind == "play_basic":
        return ("play_basic", p.hand[a.hand_index].name)
    if a.kind == "attach_energy":
        c = p.hand[a.hand_index]
        etype = (c.types[0] if c.types else "Colorless")
        return ("attach_energy", etype, a.target_index)
    if a.kind == "evolve":
        return ("evolve", p.hand[a.hand_index].name, a.target_index)
    if a.kind == "play_trainer":
        return ("play_trainer", p.hand[a.hand_index].name)
    if a.kind == "play_stadium":
        return ("play_stadium", p.hand[a.hand_index].name)
    if a.kind == "attach_tool":
        return ("attach_tool", p.hand[a.hand_index].name, a.target_index)
    if a.kind == "use_ability":
        return ("use_ability", a.target_index)
    if a.kind == "retreat":
        return ("retreat", a.target_index)
    if a.kind == "attack":
        return ("attack", a.attack_index)
    if a.kind == "pass":
        return ("pass",)
    # FAIL LOUD: a new action kind with no case here used to collapse into the
    # ("pass",) default and silently vanish from search (the play_stadium/attach_tool
    # bug). Never default again — raise so it's caught immediately, and guard it in
    # tests/test_mcts_keys.py (every legal action's key must start with its kind).
    raise ValueError(f"_semantic_key: no case for action kind {a.kind!r} — add one, "
                     f"or it will silently disappear from MCTS search.")


def _deduped_legal(state: GameState):
    """Return {semantic_key: representative Action} for the current player."""
    out = {}
    for a in legal_actions(state):
        k = _semantic_key(state, a)
        if k not in out:
            out[k] = a
    return out


# --------------------------------------------------------------------------- #
# The agent
# --------------------------------------------------------------------------- #
class MCTSAgent:
    """Determinized UCT.

    iterations   : MCTS simulations per decision (more = stronger, slower)
    c            : UCB1 exploration constant
    rollout      : "random"/"greedy" = play to terminal, backprop win/loss.
                   "eval" = stop at the leaf and backprop position_value (cheaper,
                   values within-turn lines greedy rollout misses).
    search_plies : turn-segments the tree spans. 1 = single-turn (v1). >=2 = the
                   multi-turn negamax tree (piece 2b). Pairs naturally with
                   rollout="eval": the eval truncates each deep line cheaply.
    """

    def __init__(self, iterations: int = 160, c: float = 1.4,
                 rollout: str = "greedy", rng: Optional[random.Random] = None,
                 search_plies: int = 1):
        self.iterations = iterations
        self.c = c
        self.rollout = rollout
        self.rng = rng or random.Random()
        self.search_plies = max(1, search_plies)
        # Piece 3: search-owned target policy. Stateless (pure functions of board
        # state), so one shared instance is reused. Attached to the state at the
        # top of choose() so it shapes BOTH search lines (clone() propagates it)
        # AND the actually-played action (effects run on the real state right
        # after choose returns). start_turn clears it at the turn boundary, so it
        # never leaks into the opponent's turn.
        self._policy = SearchPolicy()

    # -- public interface: same as the other agents --
    def choose(self, state: GameState) -> Action:
        state.targeting_policy = self._policy
        me = state.active_index
        root_legal = _deduped_legal(state)
        if len(root_legal) == 1:
            return next(iter(root_legal.values()))

        root = _Node(parent=None, key=None, chooser=None)
        for _ in range(self.iterations):
            world = determinize(state, me, self.rng)
            node = self._select_expand(root, world, me)
            value = self._evaluate(world, me)          # value in [0,1] for `me`
            self._backprop(node, value, me)

        if not root.children:
            return PASS
        best = max(root.children.values(), key=lambda n: n.visits)
        # map the chosen semantic key back to a concrete legal action
        return root_legal.get(best.key) or PASS

    # -- selection + expansion, replaying actions on the determinized world --
    def _select_expand(self, root: _Node, world: GameState, me: int) -> _Node:
        node = root
        plies = 0
        while world.phase == Phase.MAIN and plies < self.search_plies:
            actor_here = world.active_index          # who is choosing at this node
            by_key = _deduped_legal(world)
            if not by_key:
                break
            untried = [k for k in by_key if k not in node.children]
            if untried:
                k = self.rng.choice(untried)
                self._apply(world, by_key[k], me)
                child = _Node(parent=node, key=k, chooser=actor_here)
                node.children[k] = child
                return child
            legal_children = [node.children[k] for k in by_key if k in node.children]
            if not legal_children:
                break
            node = self._ucb_select(node, legal_children)
            before = world.active_index
            self._apply(world, by_key[node.key], me)
            if world.active_index != before:        # crossed a turn boundary
                plies += 1
        return node

    def _ucb_select(self, parent: _Node, children: list[_Node]) -> _Node:
        logN = math.log(max(1, parent.visits))
        def ucb(n: _Node):
            if n.visits == 0:
                return float("inf")
            # n.wins/n.visits is already value from n.chooser's perspective, which
            # is exactly `parent`'s actor — so maximizing is correct for the chooser.
            return n.wins / n.visits + self.c * math.sqrt(logN / n.visits)
        return max(children, key=ucb)

    # -- apply an action; if it ends the turn, advance to the opponent --
    def _apply(self, world: GameState, action: Action, me: int) -> None:
        apply_action(world, action)
        if action.kind in ("attack", "pass"):
            if action.kind == "pass":
                world.phase = Phase.BETWEEN_TURNS
            # turn is over: hand control to the opponent so search/rollout continues
            if not check_win(world):
                end_turn(world)
                start_turn(world)        # may set GAME_OVER on deck-out
                check_win(world)

    # -- leaf evaluation: return a value in [0,1] from `me`'s perspective --
    def _evaluate(self, world: GameState, me: int) -> float:
        if world.phase == Phase.GAME_OVER:
            if world.winner is None:
                return 0.5
            return 1.0 if world.winner == me else 0.0
        if self.rollout == "eval":
            # effect-aware leaf eval: no terminal playout needed.
            return _logistic(position_value(world, me))
        winner = self._rollout(world, me)
        if winner is None:
            return 0.5
        return 1.0 if winner == me else 0.0

    # -- rollout: finish the game from `world` with a fast default policy --
    def _rollout(self, world: GameState, me: int) -> Optional[int]:
        agent = (RandomAgent(self.rng) if self.rollout == "random"
                 else GreedyAgent(self.rng))
        guard = 0
        while world.phase != Phase.GAME_OVER and world.turn_number < MAX_TURNS:
            guard += 1
            if guard > 2000:
                break
            if world.phase == Phase.MAIN:
                self._play_turn(world, agent)
                if check_win(world):
                    break
                world.phase = Phase.BETWEEN_TURNS
            if world.phase == Phase.BETWEEN_TURNS:
                end_turn(world)
                if not start_turn(world):
                    break
                if check_win(world):
                    break
        if world.winner is None:                 # cap -> fewer prizes left wins
            pa, pb = world.players
            if len(pa.prizes) != len(pb.prizes):
                world.winner = 0 if len(pa.prizes) < len(pb.prizes) else 1
        return world.winner

    def _play_turn(self, world: GameState, agent) -> None:
        safety = 0
        while world.phase == Phase.MAIN:
            a = agent.choose(world)
            apply_action(world, a)
            if a.kind in ("attack", "pass"):
                if a.kind == "pass":
                    world.phase = Phase.BETWEEN_TURNS
                break
            safety += 1
            if safety > 50:
                world.phase = Phase.BETWEEN_TURNS
                break

    def _backprop(self, node: _Node, value: float, me: int) -> None:
        # NEGAMAX: store each node's stat from ITS chooser's perspective. `value`
        # is from `me`'s view; for a node the opponent chose, store (1 - value).
        while node is not None:
            node.visits += 1
            if node.chooser is None or node.chooser == me:
                node.wins += value
            else:
                node.wins += (1.0 - value)
            node = node.parent
