"""encoder.py — frozen state-feature spec (FEATURE_VERSION = 1).

Encodes a GameState from the ACTING player's point of view (state.active_index) into a
compact, JSON-able record of card-vocab ids + small numeric features. Hidden zones (the
opponent's hand, both decks, face-down prizes) are encoded only as COUNTS — never their
identities — so a perfect-information leak can't sneak into training data; search samples
those zones via the engine's determinize().

The card vocabulary is derived deterministically from the pool (sorted names), so the same
pool always yields the same ids. 0 = PAD (empty slot), 1 = UNK (name not in vocab).
"""
from __future__ import annotations

from typing import Optional

from src.engine.cards import CardDB

PAD, UNK = 0, 1
ENERGY_TYPES = ("Grass", "Fire", "Water", "Lightning",
                "Psychic", "Fighting", "Darkness", "Metal", "Dragon", "Colorless")
MAX_BENCH = 5
MAX_HAND_IDS = 12      # hand card-ids we record (padded/truncated)


class Vocab:
    """Deterministic card-name -> id map built from a CardDB (frozen by FEATURE_VERSION)."""

    def __init__(self, names: list[str]):
        self.names = names
        self.to_id = {n: i + 2 for i, n in enumerate(sorted(names))}  # 0/1 reserved
        self.size = len(self.to_id) + 2

    @classmethod
    def from_db(cls, db: CardDB) -> "Vocab":
        return cls(list(db.names()))

    def id(self, name: Optional[str]) -> int:
        if not name:
            return PAD
        return self.to_id.get(name, UNK)


def _energy_counts(mon) -> list[int]:
    """Count attached energy by type (Colorless bucket catches anything unusual)."""
    counts = {t: 0 for t in ENERGY_TYPES}
    for e in getattr(mon, "energy", []) or []:
        types = list(getattr(e, "types", []) or []) or ["Colorless"]
        t = types[0] if types[0] in counts else "Colorless"
        counts[t] += 1
    return [counts[t] for t in ENERGY_TYPES]


def _mon_features(mon, vocab: Vocab) -> dict:
    """Per-Pokémon slot features. mon may be None (empty slot -> PAD)."""
    if mon is None:
        return {"id": PAD, "hp_left": 0, "damage": 0, "n_energy": 0,
                "energy": [0] * len(ENERGY_TYPES), "is_ex": 0, "stage": 0,
                "tool": 0, "confused": 0, "cannot_attack": 0}
    card = mon.card
    subs = [s.lower() for s in (getattr(card, "subtypes", ()) or ())]
    stage = 2 if "stage 2" in subs else (1 if "stage 1" in subs else 0)
    hp = getattr(card, "hp", 0) or 0
    energy = _energy_counts(mon)
    return {
        "id": vocab.id(card.name),
        "hp_left": max(0, hp - getattr(mon, "damage", 0)),
        "damage": getattr(mon, "damage", 0),
        "n_energy": sum(energy),
        "energy": energy,
        "is_ex": 1 if "ex" in subs else 0,
        "stage": stage,
        "tool": 1 if getattr(mon, "tool", None) else 0,
        "confused": 1 if getattr(mon, "confused", False) else 0,
        "cannot_attack": 1 if getattr(mon, "cannot_attack", False) else 0,
    }


def _bench(player, vocab: Vocab) -> list[dict]:
    bench = list(getattr(player, "bench", []) or [])
    out = [_mon_features(bench[i] if i < len(bench) else None, vocab) for i in range(MAX_BENCH)]
    return out


def encode_state(state, vocab: Vocab) -> dict:
    """Encode `state` from the acting player's POV into a JSON-able feature record."""
    me_i = state.active_index
    me = state.players[me_i]
    opp = state.players[1 - me_i]

    def hand_ids(p) -> list[int]:
        ids = [vocab.id(c.name) for c in list(getattr(p, "hand", []) or [])[:MAX_HAND_IDS]]
        return ids + [PAD] * (MAX_HAND_IDS - len(ids))

    return {
        "v": 1,
        "turn": state.turn_number,
        "me_first": 1 if me_i == 0 else 0,
        # turn-scoped flags (acting player)
        "energy_attached": 1 if getattr(me, "energy_attached_this_turn", False) else 0,
        "supporter_played": 1 if getattr(me, "supporter_played_this_turn", False) else 0,
        "stadium_played": 1 if getattr(me, "stadium_played_this_turn", False) else 0,
        "cant_play_items": 1 if getattr(me, "cant_play_items", False) else 0,
        # zone sizes (hidden zones: counts only, never identities)
        "me_hand_n": len(getattr(me, "hand", []) or []),
        "me_deck_n": len(getattr(me, "deck", []) or []),
        "me_discard_n": len(getattr(me, "discard", []) or []),
        "me_prizes_n": len(getattr(me, "prizes", []) or []),
        "opp_hand_n": len(getattr(opp, "hand", []) or []),
        "opp_deck_n": len(getattr(opp, "deck", []) or []),
        "opp_discard_n": len(getattr(opp, "discard", []) or []),
        "opp_prizes_n": len(getattr(opp, "prizes", []) or []),
        # board (identities are public, so fully encoded)
        "me_active": _mon_features(getattr(me, "active", None), vocab),
        "opp_active": _mon_features(getattr(opp, "active", None), vocab),
        "me_bench": _bench(me, vocab),
        "opp_bench": _bench(opp, vocab),
        # my hand identities (mine is known to me); opponent's hand is NOT encoded
        "me_hand": hand_ids(me),
        "stadium": vocab.id(getattr(getattr(state, "stadium", None), "name", None)),
        "stadium_mine": 1 if getattr(state, "stadium_owner", None) == me_i else 0,
    }
