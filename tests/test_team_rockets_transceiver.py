#!/usr/bin/env python3
"""
test_team_rockets_transceiver.py — Team Rocket's Transceiver (Destined Rivals 178), Item:
"Search your deck for a Supporter card that has "Team Rocket" in its name, reveal it,
and put it into your hand. Then, shuffle your deck."

BOTH conditions matter, so both are negative-tested: a Supporter without "Team Rocket"
in its name (Boss's Orders) is not a legal target, and a "Team Rocket" card that is not
a SUPPORTER (Team Rocket's Transceiver itself, an Item) is not either.

Run: python3 tests/test_team_rockets_transceiver.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState
from src.engine import effects as fx


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def trainer_ctx(st, me, opp):
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    card = db.get("Team Rocket's Transceiver")

    # --- 0. card data + registry wiring. ---
    check(card.is_item, "Team Rocket's Transceiver is an Item")
    check(any('Supporter card that has "Team Rocket" in its name' in r for r in card.rules),
          f"unexpected card text: {card.rules}")
    check("Team Rocket's Transceiver" in fx.TRAINER_EFFECTS, "Transceiver must be registered")

    # --- 0b. the predicate: Supporter AND "Team Rocket" in the name. ---
    check(fx.p_team_rocket_supporter(db.get("Team Rocket's Petrel")) is True,
          "Team Rocket's Petrel qualifies (Supporter + name)")
    check(fx.p_team_rocket_supporter(db.get("Boss's Orders")) is False,
          "NEGATIVE: Boss's Orders is a Supporter but has no 'Team Rocket' in its name")
    check(fx.p_team_rocket_supporter(card) is False,
          "NEGATIVE: Transceiver has the name but is an Item, not a Supporter")
    trw = db.get("Team Rocket's Watchtower")
    check(fx.p_team_rocket_supporter(trw) is False,
          "NEGATIVE: Team Rocket's Watchtower has the name but is a Stadium")

    # --- 1. it finds the Team Rocket Supporter and only that. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Boss's Orders"), card, trw, db.get("Team Rocket's Petrel"),
              db.get("Basic Metal Energy")]
    did = fx._team_rockets_transceiver(trainer_ctx(st, a, b))
    check(did is True, "Transceiver must report that it acted")
    check([c.name for c in a.hand] == ["Team Rocket's Petrel"],
          f"only the Team Rocket Supporter may be taken, got {[c.name for c in a.hand]}")
    check(len(a.deck) == 4, f"deck must shrink by exactly 1, got {len(a.deck)}")

    # --- 2. NEGATIVE: a deck full of near-misses yields nothing. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Boss's Orders"), card, trw, db.get("Basic Metal Energy")]
    did = fx._team_rockets_transceiver(trainer_ctx(st, a, b))
    check(did is False, "no qualifying Supporter -> must report it did nothing")
    check(a.hand == [], f"nothing may come to hand, got {[c.name for c in a.hand]}")
    check(len(a.deck) == 4, "the deck must be untouched")

    # --- 3. the can_play guard mirrors the effect. ---
    check(fx.can_play_trainer(st, a, "Team Rocket's Transceiver") is False,
          "no Team Rocket Supporter in deck -> must not be offered")
    a.deck.append(db.get("Team Rocket's Petrel"))
    check(fx.can_play_trainer(st, a, "Team Rocket's Transceiver") is True,
          "a Team Rocket Supporter in deck -> must be offered")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_team_rockets_transceiver.py: all checks passed — Transceiver fetches only "
          "a Supporter whose name contains 'Team Rocket'")


if __name__ == "__main__":
    main()
