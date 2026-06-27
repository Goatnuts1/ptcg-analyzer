"""net.py — the policy/value network (PyTorch).

Card-embedding + MLP trunk -> two heads:
  policy: logits over the ACTION_SPACE action templates (masked to legal at use time)
  value : a scalar in [-1, 1] (tanh) — expected game outcome from the acting POV

Small by design (the state is compact): a few-M params, trains/infers fast on MPS.
"""
from __future__ import annotations

import torch
import torch.nn as nn

from .actions import ACTION_SPACE
from .features import CARD_SLOTS, NUMERIC_DIM


def pick_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class PolicyValueNet(nn.Module):
    def __init__(self, vocab_size: int, embed: int = 24, hidden: int = 256,
                 action_space: int = ACTION_SPACE, numeric_dim: int = NUMERIC_DIM,
                 card_slots: int = CARD_SLOTS):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, embed, padding_idx=0)
        trunk_in = card_slots * embed + numeric_dim
        self.trunk = nn.Sequential(
            nn.Linear(trunk_in, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.policy_head = nn.Linear(hidden, action_space)
        self.value_head = nn.Sequential(nn.Linear(hidden, 1), nn.Tanh())

    def forward(self, card_ids: torch.Tensor, numeric: torch.Tensor):
        e = self.embed(card_ids).flatten(start_dim=1)        # [B, slots*embed]
        h = self.trunk(torch.cat([e, numeric], dim=1))
        return self.policy_head(h), self.value_head(h).squeeze(-1)

    @staticmethod
    def masked_policy_logits(logits: torch.Tensor, legal: torch.Tensor) -> torch.Tensor:
        """Set illegal-action logits to -inf so they get ~0 probability."""
        return logits.masked_fill(~legal, float("-inf"))
