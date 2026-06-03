#!/usr/bin/env python3
"""
test_evaluation.py — effect-aware position valuation (POLICY milestone, piece 1).

Proves position_value is SOUND in isolation: it rewards bench pressure, disruption,
and prizes, and — the whole point — ranks an effect attack (Phantom Dive's spread)
above doing nothing when the attacker is set up, with no per-card heuristics.

(Separately: a 1-ply EvalAgent using this eval plays degenerate FULL games — it can't
see setup→payoff across turns. That's a known limitation the valuation function does
not fix on its own; multi-turn search, piece 2, is what makes it express the deck's
plan. So these tests assert the eval's correctness, not full-game strength.)

Run from project root:  python3 tests/test_evaluation.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine.evaluation import position_value
from src.engine.agents import EvalAgent
from src.engine.game import legal_actions, apply_action


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 6
    a.turns_taken = b.turns_taken = 4
    a.prizes = [db.get("Dreepy")] * 6
    b.prizes = [db.get("Dreepy")] * 6
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    PULT = db.get("Dragapult ex")
    DREEPY = db.get("Dreepy")
    FIRE = db.get("Basic Fire Energy")
    PSY = db.get("Basic Psychic Energy")

    # --- bench pressure: damage on the opponent's board raises your value. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT)
    b.active = InPlayPokemon(card=PULT)
    b.bench = [InPlayPokemon(card=DREEPY), InPlayPokemon(card=DREEPY)]
    base = position_value(st, 0)
    b.bench[0].damage = 60          # a benched Dreepy near KO
    check(position_value(st, 0) > base, "damage on the opponent's bench should raise your value")

    # --- prizes dominate. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT); b.active = InPlayPokemon(card=PULT)
    before = position_value(st, 0)
    a.prizes.pop()                  # you took a prize
    check(position_value(st, 0) > before + 50, "taking a prize should be a large value gain")

    # --- disruption you impose is worth value. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT); b.active = InPlayPokemon(card=PULT)
    base = position_value(st, 0)
    b.cant_play_items = True
    check(position_value(st, 0) > base, "opponent Item-lock should raise your value")

    # --- THE POINT: with a set-up Dragapult ex, the effect attack (Phantom Dive)
    #     scores above passing — the eval values the spread, not the printed number. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT, energy=[FIRE, PSY])
    a.bench = [InPlayPokemon(card=db.get("Drakloak"))]
    b.active = InPlayPokemon(card=PULT)
    b.bench = [InPlayPokemon(card=DREEPY), InPlayPokemon(card=DREEPY)]
    st.active_index = 0
    acts = legal_actions(st)
    pd = next((x for x in acts if x.kind == "attack"
               and a.active.card.attacks[x.attack_index].name == "Phantom Dive"), None)
    check(pd is not None, "Phantom Dive should be legal when set up")
    def val_of(action):
        cl = st.clone(fresh_rng=random.Random(1)); apply_action(cl, action)
        return position_value(cl, 0)
    pass_v = val_of(next(x for x in acts if x.kind == "pass"))
    pd_v = val_of(pd)
    check(pd_v > pass_v, f"Phantom Dive ({pd_v:.1f}) should out-value passing ({pass_v:.1f})")
    check(EvalAgent(random.Random(0)).choose(st).kind == "attack",
          "EvalAgent should attack (Phantom Dive) when the attacker is ready")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — position_value is sound: values bench pressure, prizes, disruption, and ranks "
          "Phantom Dive's spread above passing when set up. (Full-game 1-ply play is degenerate "
          "by design — piece 2 / multi-turn search is what fixes that.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
