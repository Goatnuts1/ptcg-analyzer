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

import random
from typing import Optional

from src.engine.game import PASS, legal_actions
from src.engine.mcts import MCTSAgent
from src.engine.state import GameState

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

    def _evaluate(self, world: GameState, me: int) -> float:
        from src.engine.game import check_win
        from src.engine.state import Phase
        if world.phase == Phase.GAME_OVER or check_win(world):
            if world.winner is None:
                return 0.5
            return 1.0 if world.winner == me else 0.0
        v = self.model.value(world)                 # in [-1,1] for world.active_index
        signed_for_me = v if world.active_index == me else -v
        return (signed_for_me + 1.0) / 2.0          # -> [0,1] for `me`
