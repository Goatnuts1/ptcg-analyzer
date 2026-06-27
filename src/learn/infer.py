"""infer.py — load a trained model artifact and evaluate live GameStates.

Wraps a PolicyValueNet for single-state inference inside the engine's decision loop:
  value(state)  -> scalar in [-1, 1], the predicted outcome for state.active_index
  policy(state) -> {action_id: prob} over the LEGAL actions (masked + renormalised)

Runs on CPU by default: the net is tiny (~0.38M params) and single-state forward passes
are faster on CPU than paying MPS per-call overhead (MPS is for batched training).
Validates that the artifact's FEATURE/ACTION/vocab versions match this code.
"""
from __future__ import annotations

import torch

from src.engine.cards import CardDB
from src.engine.game import legal_actions

from . import config
from .actions import action_to_id
from .encoder import Vocab, encode_state
from .features import vectorize
from .net import PolicyValueNet


class Model:
    def __init__(self, artifact_path: str, pool: str = config.DEFAULT_POOL,
                 device: str = "cpu"):
        ckpt = torch.load(artifact_path, map_location="cpu", weights_only=False)
        if ckpt.get("feature_version") != config.FEATURE_VERSION:
            raise ValueError(f"feature_version mismatch: artifact {ckpt.get('feature_version')} "
                             f"!= code {config.FEATURE_VERSION}")
        if ckpt.get("action_version") != config.ACTION_VERSION:
            raise ValueError(f"action_version mismatch: artifact {ckpt.get('action_version')} "
                             f"!= code {config.ACTION_VERSION}")
        self.vocab = Vocab.from_db(CardDB.from_pool(pool))
        if ckpt.get("vocab_size") != self.vocab.size:
            raise ValueError(f"vocab_size mismatch: artifact {ckpt.get('vocab_size')} "
                             f"!= pool {self.vocab.size}")
        self.device = torch.device(device)
        self.net = PolicyValueNet(self.vocab.size,
                                  embed=ckpt.get("embed", 24), hidden=ckpt.get("hidden", 256))
        self.net.load_state_dict(ckpt["state_dict"])
        self.net.to(self.device).eval()
        self.metrics = ckpt.get("metrics", {})
        self.git_sha = ckpt.get("git_sha", "?")

    @torch.no_grad()
    def _forward(self, state):
        ids, num = vectorize(encode_state(state, self.vocab))
        ci = torch.tensor([ids], dtype=torch.long, device=self.device)
        nm = torch.tensor([num], dtype=torch.float32, device=self.device)
        logits, value = self.net(ci, nm)
        return logits[0], float(value[0])

    def value(self, state) -> float:
        """Predicted outcome in [-1, 1] for the player to move (state.active_index)."""
        return self._forward(state)[1]

    def policy(self, state) -> dict:
        """{action_id: prob} over the legal actions, masked + renormalised."""
        logits, _ = self._forward(state)
        legal = legal_actions(state)
        ids = sorted({action_to_id(a) for a in legal})
        sub = logits[ids]
        probs = torch.softmax(sub, dim=0)
        return {aid: float(p) for aid, p in zip(ids, probs)}

    def policy_value(self, state):
        """Both at once (one forward pass): (policy dict, value)."""
        logits, value = self._forward(state)
        legal = legal_actions(state)
        ids = sorted({action_to_id(a) for a in legal})
        probs = torch.softmax(logits[ids], dim=0)
        return {aid: float(p) for aid, p in zip(ids, probs)}, value
