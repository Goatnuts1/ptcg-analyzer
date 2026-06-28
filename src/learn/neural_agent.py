"""neural_agent.py — agents that play with the trained net (Phase 3).

PolicyAgent       0-ply: pick the legal action the policy net likes most (≈ imitation;
                  a fast baseline ~ as strong as the greedy it learned from).
NeuralMCTSAgent   the get-stronger agent: determinized (ISMCTS) PUCT search that uses the
                  policy net as action priors and the VALUE net as the leaf evaluation,
                  reusing the engine's determinize()/apply_action() machinery. Search on
                  top of a learned value function is what lets it plan past greedy.

The engine stays the rules oracle — both agents only ever return a move from
legal_actions(); the net just ranks/values, exactly like position_value did.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from src.engine.game import PASS, legal_actions
from src.engine.mcts import MCTSAgent, _Node, _deduped_legal, determinize
from src.engine.state import GameState, Phase

from .actions import action_to_id


class PolicyAgent:
    """Greedy over the policy net: argmax prior among legal actions."""

    def __init__(self, model, rng: Optional[random.Random] = None):
        self.model = model
        self.rng = rng or random.Random()

    def choose(self, state: GameState):
        legal = legal_actions(state)
        if len(legal) == 1:
            return legal[0]
        priors = self.model.policy(state)                 # {action_id: prob}
        best, best_p = None, -1.0
        for a in legal:
            p = priors.get(action_to_id(a), 0.0)
            if p > best_p:
                best, best_p = a, p
        return best or PASS


class NeuralMCTSAgent(MCTSAgent):
    """Determinized (ISMCTS) search with the VALUE NET as the leaf evaluation.

    Inherits the engine's proven determinized-UCT loop and overrides only the leaf eval —
    swapping the hand-written position_value for the learned value net. Search on top of a
    learned value function is the lever that plans past greedy. (Policy-net PUCT priors are
    a clean follow-up — Phase 3b — once the engine's MCTS exposes per-node states; not wired
    here rather than wired uniformly and dishonestly.)
    """

    def __init__(self, model, iterations: int = 120, c: float = 1.4,
                 rng: Optional[random.Random] = None, search_plies: int = 1):
        super().__init__(iterations=iterations, c=c, rollout="eval",
                         rng=rng, search_plies=search_plies)
        self.model = model
        self._root_prior_by_key: dict = {}     # set per choose() for root-PUCT

    def _evaluate(self, world: GameState, me: int) -> float:
        from src.engine.game import check_win
        if world.phase == Phase.GAME_OVER or check_win(world):
            if world.winner is None:
                return 0.5
            return 1.0 if world.winner == me else 0.0
        v = self.model.value(world)                 # in [-1,1] for world.active_index
        signed_for_me = v if world.active_index == me else -v
        return (signed_for_me + 1.0) / 2.0          # -> [0,1] for `me`

    # --- Phase 3b lever #2: PUCT at the root, using policy-net priors ---
    # The engine's lazy MCTS doesn't expose per-node states, but the ROOT is where move
    # choice + the recorded visit distribution are decided, so we prime priors there.
    def _ucb_select(self, parent, children):
        if getattr(parent, "parent", "x") is None and self._root_prior_by_key:
            sqrtN = math.sqrt(max(1, parent.visits))
            n_children = max(1, len(children))
            def puct(n):
                q = (n.wins / n.visits) if n.visits > 0 else 0.0
                p = self._root_prior_by_key.get(n.key, 1.0 / n_children)
                return q + self.c * p * sqrtN / (1 + n.visits)
            return max(children, key=puct)
        return super()._ucb_select(parent, children)

    # --- Phase 3b lever #1: return the MCTS visit distribution as the policy target ---
    def choose_with_policy(self, state: GameState):
        """Run the search and return (action, {action_id: visit_prob}). The visit
        distribution is the search-improved policy AlphaZero trains on (richer than argmax)."""
        me = state.active_index
        root_legal = _deduped_legal(state)
        if len(root_legal) == 1:
            a = next(iter(root_legal.values()))
            return a, {action_to_id(a): 1.0}

        # prime root priors from the policy net (keyed by the engine's semantic keys)
        priors = self.model.policy(state)           # {action_id: prob} over legal
        self._root_prior_by_key = {
            k: priors.get(action_to_id(a), 0.0) for k, a in root_legal.items()
        }

        root = _Node(parent=None, key=None, chooser=None)
        for _ in range(self.iterations):
            world = determinize(state, me, self.rng)
            node = self._select_expand(root, world, me)
            value = self._evaluate(world, me)
            self._backprop(node, value, me)
        self._root_prior_by_key = {}

        if not root.children:
            return PASS, {action_to_id(PASS): 1.0}
        dist: dict = {}
        total = 0
        for key, child in root.children.items():
            a = root_legal.get(key)
            if a is None:
                continue
            aid = action_to_id(a)
            dist[aid] = dist.get(aid, 0) + child.visits
            total += child.visits
        if total > 0:
            dist = {k: v / total for k, v in dist.items()}
        best = max(root.children.values(), key=lambda n: n.visits)
        return root_legal.get(best.key) or PASS, dist

    def choose(self, state: GameState):
        return self.choose_with_policy(state)[0]
