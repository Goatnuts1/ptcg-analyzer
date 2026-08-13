#!/usr/bin/env python3
"""
test_team_rockets_petrel.py — Team Rocket's Petrel (Destined Rivals 176), Supporter:
"Search your deck for a Trainer card, reveal it, and put it into your hand. Then,
shuffle your deck."

Load-bearing: ANY Trainer card (Item, Supporter, Tool or Stadium) is a legal target —
it is not restricted to "Team Rocket" cards — but exactly ONE is taken, and non-Trainer
cards (Pokémon, Energy) are never taken.

Run: python3 tests/test_team_rockets_petrel.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def trainer_ctx(st, me, opp):
    # Trainers have no source Pokémon (mirrors game.play_trainer's context).
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    card = db.get("Team Rocket's Petrel")

    # --- 0. card data + registry wiring. ---
    check(card.is_supporter, "Team Rocket's Petrel is a Supporter")
    check(any("Search your deck for a Trainer card" in r for r in card.rules),
          f"unexpected card text: {card.rules}")
    check("Team Rocket's Petrel" in fx.TRAINER_EFFECTS, "Petrel must be registered")

    # --- 1. one Trainer comes to hand; the deck shrinks by exactly 1. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Basic Metal Energy"), db.get("Beldum"), db.get("Boss's Orders"),
              db.get("Ultra Ball")]
    did = fx._team_rockets_petrel(trainer_ctx(st, a, b))
    check(did is True, "Petrel must report that it acted")
    check(len(a.hand) == 1 and a.hand[0].is_trainer,
          f"exactly 1 Trainer must come to hand, got {[c.name for c in a.hand]}")
    check(len(a.deck) == 3, f"deck must shrink by exactly 1, got {len(a.deck)}")

    # --- 2. NEGATIVE: it never grabs a Pokémon or an Energy. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Basic Metal Energy"), db.get("Beldum"), db.get("Metang")]
    did = fx._team_rockets_petrel(trainer_ctx(st, a, b))
    check(did is False, "with no Trainer in the deck Petrel must report it did nothing")
    check(a.hand == [], f"nothing may come to hand, got {[c.name for c in a.hand]}")
    check(len(a.deck) == 3, "the deck must be untouched")

    # --- 3. a Tool / Stadium / Item all count as "a Trainer card". ---
    for name in ("Air Balloon", "Gravity Mountain", "Team Rocket's Transceiver"):
        st, a, b = fresh_state(db)
        a.deck = [db.get("Basic Metal Energy"), db.get(name)]
        fx._team_rockets_petrel(trainer_ctx(st, a, b))
        check([c.name for c in a.hand] == [name],
              f"{name} is a Trainer card and must be findable, got "
              f"{[c.name for c in a.hand]}")

    # --- 4. the can_play guard mirrors the effect (never offered when it can't act). ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Basic Metal Energy")]
    check(fx.can_play_trainer(st, a, "Team Rocket's Petrel") is False,
          "no Trainer in deck -> must not be offered")
    a.deck.append(db.get("Boss's Orders"))
    check(fx.can_play_trainer(st, a, "Team Rocket's Petrel") is True,
          "a Trainer in deck -> must be offered")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_team_rockets_petrel.py: all checks passed — Petrel fetches exactly 1 "
          "Trainer card of any kind, and nothing else")


if __name__ == "__main__":
    main()
