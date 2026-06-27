"""actions.py — a fixed, bounded Action <-> id space for the policy head.

The engine's `Action` is (kind, hand_index, target_index, attack_index). We map every
legal action to a stable integer id in a small fixed range so the learned policy is a
masked softmax over ~a few hundred logits (the engine's legal_actions() supplies the
mask each ply). This is ACTION_VERSION = 1; bump config.ACTION_VERSION if it changes.

Index caps (a hand never realistically exceeds ~10; bench is at most 5):
  hand_index  : 0 .. MAX_HAND-1
  target slot : active (engine -1) -> 0, bench k (0..4) -> 1..5     (MAX_TARGET slots)
  attack_index: 0 .. MAX_ATTACK-1
Out-of-range indices clamp into range (so the mapping is total and never raises).
"""
from __future__ import annotations

from src.engine.game import Action

MAX_HAND = 12
MAX_TARGET = 6      # 0 = active, 1..5 = bench slots 0..4
MAX_ATTACK = 4

# Per-kind id-block sizes, in a fixed order. Layout is contiguous; offsets computed below.
_LAYOUT = [
    ("pass",          1),
    ("play_basic",    MAX_HAND),
    ("play_stadium",  MAX_HAND),
    ("play_trainer",  MAX_HAND),
    ("attach_energy", MAX_HAND * MAX_TARGET),
    ("evolve",        MAX_HAND * MAX_TARGET),
    ("attach_tool",   MAX_HAND * MAX_TARGET),
    ("use_ability",   MAX_TARGET),
    ("retreat",       MAX_TARGET),
    ("attack",        MAX_ATTACK),
]

_OFFSET: dict[str, int] = {}
_acc = 0
for _kind, _size in _LAYOUT:
    _OFFSET[_kind] = _acc
    _acc += _size
ACTION_SPACE = _acc          # total number of action ids (~269)


def _clamp(v, hi: int) -> int:
    if v is None:
        return 0
    return 0 if v < 0 else (hi - 1 if v >= hi else v)


def _target_slot(target_index) -> int:
    """Engine target_index: -1 = active, 0..4 = bench -> slot 0..5."""
    if target_index is None or target_index < 0:
        return 0
    return _clamp(target_index + 1, MAX_TARGET)


def action_to_id(a: Action) -> int:
    """Map an Action to its stable id in [0, ACTION_SPACE). Total (never raises)."""
    k = a.kind
    off = _OFFSET.get(k)
    if off is None:
        return _OFFSET["pass"]            # unknown kind -> pass bucket (defensive)
    if k == "pass":
        return off
    if k in ("play_basic", "play_stadium", "play_trainer"):
        return off + _clamp(a.hand_index, MAX_HAND)
    if k in ("attach_energy", "evolve", "attach_tool"):
        return off + _clamp(a.hand_index, MAX_HAND) * MAX_TARGET + _target_slot(a.target_index)
    if k == "use_ability":
        return off + _target_slot(a.target_index)
    if k == "retreat":
        return off + _target_slot(a.target_index)
    if k == "attack":
        return off + _clamp(a.attack_index, MAX_ATTACK)
    return _OFFSET["pass"]


def legal_ids(actions) -> list[int]:
    """De-duplicated, sorted action ids for a list of legal Actions (the policy mask)."""
    return sorted({action_to_id(a) for a in actions})
