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
        action = self.base.choose(state)
        # Only record decisions where there was a genuine choice (>1 legal action).
        legal = legal_actions(state)
        if len(legal) > 1:
            self.sink.append({
                "seat": state.active_index,
                "turn": state.turn_number,
                "state": encode_state(state, self.vocab),
                "legal": legal_ids(legal),
                "action": action_to_id(action),
            })
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
                  deck_a_id: str, deck_b_id: str, agent_kind: str = "greedy") -> list[dict]:
    """Play one self-play game; return its finished training records (with value z)."""
    sink: list[dict] = []
    rng_a, rng_b = random.Random(seed), random.Random(seed + 1)
    agent_a = RecordingAgent(_make_base(agent_kind, rng_a), 0, vocab, sink)
    agent_b = RecordingAgent(_make_base(agent_kind, rng_b), 1, vocab, sink)

    state = play_game(deck_a, deck_b, agent_a, agent_b, seed=seed, keep_log=False, db=db)
    winner = state.winner   # 0, 1, or None (tie)

    records = []
    for r in sink:
        seat = r["seat"]
        z = 0.0 if winner is None else (1.0 if winner == seat else -1.0)
        records.append({
            "fv": config.FEATURE_VERSION, "av": config.ACTION_VERSION, "rv": config.RECORD_VERSION,
            "seed": seed, "deck_a": deck_a_id, "deck_b": deck_b_id,
            "seat": seat, "turn": r["turn"],
            "state": r["state"], "legal": r["legal"], "action": r["action"], "z": z,
        })
    return records


def generate_batch(deck_a_id: str, deck_b_id: str, seeds: list[int], db: CardDB,
                   vocab: Vocab, agent_kind: str = "greedy") -> list[dict]:
    """Generate records for a list of seeds on one (deck_a, deck_b) pairing."""
    deck_a = load_deck(db, deck_a_id)
    deck_b = load_deck(db, deck_b_id)
    out: list[dict] = []
    for s in seeds:
        out.extend(generate_game(deck_a, deck_b, s, vocab, db, deck_a_id, deck_b_id, agent_kind))
    return out


def all_deck_ids() -> list[str]:
    return list(DECKS.keys())
