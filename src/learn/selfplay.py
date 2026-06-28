"""selfplay.py — generate (state, policy, value) records from engine self-play.

A RecordingAgent wraps any base agent (greedy/MCTS) and, at every decision, captures the
encoded state, the legal action-id mask, and the chosen action id — then returns the base
agent's choice unchanged. The deterministic engine plays the game; we only observe. After
the game ends, each record gets its value z from the winner, from that record's seat's POV.

This reuses the existing engine/agents wholesale, so the rules are exactly the engine's
rules and the games stay deterministic (each carries its seed for reproducibility).
"""
from __future__ import annotations

import random

from src.engine.cards import CardDB
from src.engine.decks import load_deck, DECKS
from src.engine.game import legal_actions
from src.engine.run import play_game

from . import config
from .actions import action_to_id, legal_ids
from .encoder import Vocab, encode_state


class RecordingAgent:
    """Wrap a base agent; record (state, legal mask, chosen id, seat) at each choose()."""

    def __init__(self, base, seat: int, vocab: Vocab, sink: list):
        self.base = base
        self.seat = seat
        self.vocab = vocab
        self.sink = sink

    def choose(self, state):
        # If the base agent is search-based, capture its visit distribution (the
        # AlphaZero policy target); otherwise fall back to the single chosen action.
        dist = None
        if hasattr(self.base, "choose_with_policy"):
            action, dist = self.base.choose_with_policy(state)
        else:
            action = self.base.choose(state)
        legal = legal_actions(state)
        if len(legal) > 1:
            rec = {
                "seat": state.active_index,
                "turn": state.turn_number,
                "state": encode_state(state, self.vocab),
                "legal": legal_ids(legal),
                "action": action_to_id(action),
            }
            if dist:
                rec["policy"] = [[aid, round(p, 5)] for aid, p in dist.items() if p > 0]
            self.sink.append(rec)
        return action


def _make_base(kind: str, rng: random.Random):
    from src.engine.agents import RandomAgent, GreedyAgent
    if kind == "random":
        return RandomAgent(rng)
    if kind == "mcts":
        from src.engine.mcts import MCTSAgent
        return MCTSAgent(iterations=120, rollout="greedy", rng=rng)
    return GreedyAgent(rng)


def generate_game(deck_a, deck_b, seed: int, vocab: Vocab, db: CardDB,
                  deck_a_id: str, deck_b_id: str, agent_kind: str = "greedy",
                  agent_factory=None) -> list[dict]:
    """Play one self-play game; return its finished training records (with value z).

    agent_factory(seat, rng) -> base agent overrides agent_kind when given — this is how
    the Phase-3 loop self-plays with the neural agent (kept out of this stdlib module).
    """
    sink: list[dict] = []
    rng_a, rng_b = random.Random(seed), random.Random(seed + 1)
    base_a = agent_factory(0, rng_a) if agent_factory else _make_base(agent_kind, rng_a)
    base_b = agent_factory(1, rng_b) if agent_factory else _make_base(agent_kind, rng_b)
    agent_a = RecordingAgent(base_a, 0, vocab, sink)
    agent_b = RecordingAgent(base_b, 1, vocab, sink)

    state = play_game(deck_a, deck_b, agent_a, agent_b, seed=seed, keep_log=False, db=db)
    winner = state.winner   # 0, 1, or None (tie)

    records = []
    for r in sink:
        seat = r["seat"]
        z = 0.0 if winner is None else (1.0 if winner == seat else -1.0)
        rec = {
            "fv": config.FEATURE_VERSION, "av": config.ACTION_VERSION, "rv": config.RECORD_VERSION,
            "seed": seed, "deck_a": deck_a_id, "deck_b": deck_b_id,
            "seat": seat, "turn": r["turn"],
            "state": r["state"], "legal": r["legal"], "action": r["action"], "z": z,
        }
        if "policy" in r:
            rec["policy"] = r["policy"]
        records.append(rec)
    return records


def generate_batch(deck_a_id: str, deck_b_id: str, seeds: list[int], db: CardDB,
                   vocab: Vocab, agent_kind: str = "greedy", agent_factory=None) -> list[dict]:
    """Generate records for a list of seeds on one (deck_a, deck_b) pairing."""
    deck_a = load_deck(db, deck_a_id)
    deck_b = load_deck(db, deck_b_id)
    out: list[dict] = []
    for s in seeds:
        out.extend(generate_game(deck_a, deck_b, s, vocab, db, deck_a_id, deck_b_id,
                                 agent_kind, agent_factory))
    return out


def all_deck_ids() -> list[str]:
    return list(DECKS.keys())
