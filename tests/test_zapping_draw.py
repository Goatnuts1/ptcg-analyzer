#!/usr/bin/env python3
"""
test_zapping_draw.py — Ethan's Pichu (Destined Rivals 71) Zapping Draw:
"[no Energy] 30 — Draw a card."

Bulbapedia's card data for DRI 71 gives the attack cost as {{e|None}} — a genuinely
free attack (the same "no Energy required" shape as Budew's Itchy Pollen), which the
pool encodes as an empty cost list. Asserted here so a data change is caught. The
printed 30 is flat, so the engine applies it and the effect only draws.

Run: python3 tests/test_zapping_draw.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import can_pay_cost


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    pichu_card = db.get("Ethan's Pichu")

    # --- 0. card data + registry wiring. ---
    check(pichu_card.id == "sv10-71",
          f"expected the Destined Rivals Ethan's Pichu (sv10-71), pool has {pichu_card.id}")
    atk = next(a for a in pichu_card.attacks if a.name == "Zapping Draw")
    check(atk.damage == 30 and atk.damage_suffix == "",
          f"Zapping Draw is a flat 30, got {atk.damage}{atk.damage_suffix!r}")
    check(atk.text.strip() == "Draw a card.", f"unexpected card text: {atk.text!r}")
    check(tuple(s for s in atk.cost if s != "Free") == (),
          f"Zapping Draw requires no Energy, got cost {atk.cost}")
    check(("Ethan's Pichu", "Zapping Draw") in fx.ATTACK_EFFECTS,
          "Zapping Draw must be registered")
    check(("Ethan's Pichu", "Zapping Draw") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "the printed 30 is flat — the engine applies it, the effect only draws")

    # --- 1. it is payable with ZERO Energy attached (that's the whole point). ---
    pichu = InPlayPokemon(card=pichu_card)
    check(can_pay_cost(pichu, atk.cost) is True,
          "Zapping Draw must be usable with no Energy attached")

    # --- 2. the effect draws exactly 1 card, from the TOP of the deck. ---
    st, a, b = fresh_state(db)
    a.active = pichu
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    top, second = db.get("Boss's Orders"), db.get("Ultra Ball")
    a.deck = [top, second, db.get("Basic Metal Energy")]
    fx._zapping_draw(ctx_for(st, a, b, source=pichu))
    check([c.name for c in a.hand] == [top.name],
          f"exactly the top card must be drawn, got {[c.name for c in a.hand]}")
    check(len(a.deck) == 2 and a.deck[0] is second, "the deck must lose exactly 1 card")

    # --- 3. NEGATIVE: it draws exactly ONE — not two. ---
    check(len(a.hand) == 1, f"Zapping Draw draws 1 card, got {len(a.hand)}")

    # --- 4. NEGATIVE: an empty deck draws nothing and must not raise (the deck-out
    # loss is the turn loop's job, not this effect's). ---
    st, a, b = fresh_state(db)
    pichu2 = InPlayPokemon(card=pichu_card)
    a.active = pichu2
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    a.deck = []
    fx._zapping_draw(ctx_for(st, a, b, source=pichu2))
    check(a.hand == [], f"an empty deck yields no card, got {[c.name for c in a.hand]}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_zapping_draw.py: all checks passed — Zapping Draw is free, does 30, and "
          "draws exactly 1 card")


if __name__ == "__main__":
    main()
