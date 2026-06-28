"""features.py — turn an encoder state-dict into fixed tensors for the net.

The encoder (encoder.py) emits a JSON-able dict per decision. Here we flatten it into:
  card_ids : 25 card-vocab ids (embedded by the net)   [me/opp active, 5+5 bench, 12 hand, stadium]
  numeric  : NUMERIC_DIM normalised floats               [per-mon stats + global scalars]
plus the supervised targets (action id, legal mask, value z) assembled in batch form.

This layout is tied to FEATURE_VERSION; bump config.FEATURE_VERSION if it changes so old
shards/models are filtered out rather than silently mis-read.
"""
from __future__ import annotations

import numpy as np

from .actions import ACTION_SPACE

# card-id slot layout (order is fixed)
N_BENCH = 5
N_HAND = 12
CARD_SLOTS = 1 + 1 + N_BENCH + N_BENCH + N_HAND + 1   # = 25
# per-mon numeric features
_MON_SCALARS = 8           # hp_left, damage, n_energy, is_ex, stage, tool, confused, cannot_attack
_MON_ENERGY = 10           # energy counts by type
_MON_DIM = _MON_SCALARS + _MON_ENERGY   # 18
_N_MONS = 2 + 2 * N_BENCH  # me_active, opp_active, 5 me_bench, 5 opp_bench = 12
_GLOBAL_DIM = 15
NUMERIC_DIM = _MON_DIM * _N_MONS + _GLOBAL_DIM   # 18*12 + 15 = 231


def _mon_vec(m: dict) -> list[float]:
    en = m.get("energy", [0] * _MON_ENERGY)
    return [
        m.get("hp_left", 0) / 350.0,
        m.get("damage", 0) / 350.0,
        m.get("n_energy", 0) / 8.0,
        float(m.get("is_ex", 0)),
        m.get("stage", 0) / 2.0,
        float(m.get("tool", 0)),
        float(m.get("confused", 0)),
        float(m.get("cannot_attack", 0)),
    ] + [c / 4.0 for c in en]


def _mon_id(m: dict) -> int:
    return int(m.get("id", 0))


def vectorize(state: dict) -> tuple[list[int], list[float]]:
    """One state-dict -> (card_ids[25], numeric[NUMERIC_DIM])."""
    me_b = state["me_bench"]
    op_b = state["opp_bench"]
    ids = ([_mon_id(state["me_active"]), _mon_id(state["opp_active"])]
           + [_mon_id(m) for m in me_b]
           + [_mon_id(m) for m in op_b]
           + list(state["me_hand"])[:N_HAND]
           + [int(state["stadium"])])
    assert len(ids) == CARD_SLOTS, f"{len(ids)} != {CARD_SLOTS}"

    num: list[float] = []
    num += _mon_vec(state["me_active"])
    num += _mon_vec(state["opp_active"])
    for m in me_b:
        num += _mon_vec(m)
    for m in op_b:
        num += _mon_vec(m)
    num += [
        state["turn"] / 30.0, float(state["me_first"]),
        float(state["energy_attached"]), float(state["supporter_played"]),
        float(state["stadium_played"]), float(state["cant_play_items"]),
        state["me_hand_n"] / 12.0, state["me_deck_n"] / 40.0,
        state["me_discard_n"] / 40.0, state["me_prizes_n"] / 6.0,
        state["opp_hand_n"] / 12.0, state["opp_deck_n"] / 40.0,
        state["opp_discard_n"] / 40.0, state["opp_prizes_n"] / 6.0,
        float(state["stadium_mine"]),
    ]
    assert len(num) == NUMERIC_DIM, f"{len(num)} != {NUMERIC_DIM}"
    return ids, num


def records_to_arrays(records: list[dict]) -> dict:
    """Vectorize records into numpy arrays. `policy` is a soft target over ACTION_SPACE:
    the MCTS visit distribution when present (AlphaZero-style), else a one-hot on the
    chosen action (so greedy/bootstrap records still work). `action` (argmax) is kept too."""
    n = len(records)
    card_ids = np.zeros((n, CARD_SLOTS), dtype=np.int64)
    numeric = np.zeros((n, NUMERIC_DIM), dtype=np.float32)
    action = np.zeros(n, dtype=np.int64)
    legal = np.zeros((n, ACTION_SPACE), dtype=np.bool_)
    policy = np.zeros((n, ACTION_SPACE), dtype=np.float32)
    value = np.zeros(n, dtype=np.float32)
    for i, r in enumerate(records):
        ids, num = vectorize(r["state"])
        card_ids[i] = ids
        numeric[i] = num
        action[i] = r["action"]
        legal[i, r["legal"]] = True
        value[i] = r["z"]
        if r.get("policy"):
            for aid, p in r["policy"]:
                policy[i, aid] = p
            s = policy[i].sum()
            if s > 0:
                policy[i] /= s
        else:
            policy[i, r["action"]] = 1.0
    return {"card_ids": card_ids, "numeric": numeric, "action": action,
            "legal": legal, "policy": policy, "value": value}
