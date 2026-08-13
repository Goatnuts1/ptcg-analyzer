#!/usr/bin/env python3
"""
test_undermine.py — Mega Excadrill ex (Pitch Black 65) Undermine:
"[M][M] 90 — Discard the top 2 cards of your opponent's deck."

Load-bearing: it mills the OPPONENT's deck (not your own), exactly 2 cards, from the
TOP, into their DISCARD (not shuffled away or prized). The printed 90 is flat, so the
engine applies it and the effect only mills.

Run: python3 tests/test_undermine.py
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


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    exca_card = db.get("Mega Excadrill ex")

    # --- 0. card data + registry wiring (also pins the Mega Evolution ex rule). ---
    check(exca_card.hp == 340 and exca_card.types == ("Metal",)
          and exca_card.evolves_from == "Drilbur",
          f"Mega Excadrill ex is a 340 HP Metal Stage 1 from Drilbur, got "
          f"{exca_card.hp}/{exca_card.types}/{exca_card.evolves_from}")
    check(exca_card.gives_up_prizes == 3,
          f"a Mega Evolution Pokémon ex gives up 3 Prizes, got {exca_card.gives_up_prizes}")
    atk = next(a for a in exca_card.attacks if a.name == "Undermine")
    check(atk.cost == ("Metal", "Metal") and atk.damage == 90 and atk.damage_suffix == "",
          f"Undermine is [M][M] for a flat 90, got {atk.cost} {atk.damage}{atk.damage_suffix!r}")
    check(atk.text == "Discard the top 2 cards of your opponent's deck.",
          f"unexpected card text: {atk.text!r}")
    check(("Mega Excadrill ex", "Undermine") in fx.ATTACK_EFFECTS, "Undermine must be registered")
    check(("Mega Excadrill ex", "Undermine") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "the printed 90 is flat — the engine applies it, the effect only mills")

    # --- 1. exactly the top 2 of the OPPONENT's deck go to the OPPONENT's discard. ---
    st, a, b = fresh_state(db)
    exca = InPlayPokemon(card=exca_card)
    a.active = exca
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    t1, t2, t3 = db.get("Boss's Orders"), db.get("Ultra Ball"), db.get("Beldum")
    b.deck = [t1, t2, t3, db.get("Basic Metal Energy")]
    a.deck = [db.get("Basic Metal Energy")] * 3
    fx._undermine(ctx_for(st, a, b, source=exca))
    check([c.name for c in b.discard] == [t1.name, t2.name],
          f"the top 2 (in order) must be discarded, got {[c.name for c in b.discard]}")
    check(len(b.deck) == 2 and b.deck[0] is t3, "the opponent's deck must lose exactly 2 from the top")

    # --- 2. NEGATIVE: our own deck and discard are untouched. ---
    check(len(a.deck) == 3 and a.discard == [],
          f"Undermine must not touch your own deck/discard, got deck={len(a.deck)}, "
          f"discard={len(a.discard)}")

    # --- 3. NEGATIVE: it deals no damage itself (the engine applies the printed 90). ---
    check(b.active.damage == 0,
          f"the effect must not add damage of its own, got {b.active.damage}")

    # --- 4. a 1-card opponent deck mills just that card; an empty deck is a no-op. ---
    st, a, b = fresh_state(db)
    exca2 = InPlayPokemon(card=exca_card)
    a.active = exca2
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    b.deck = [t1]
    fx._undermine(ctx_for(st, a, b, source=exca2))
    check(b.deck == [] and [c.name for c in b.discard] == [t1.name],
          f"a 1-card deck mills 1, got deck={b.deck}, discard={[c.name for c in b.discard]}")
    fx._undermine(ctx_for(st, a, b, source=exca2))
    check(b.deck == [] and len(b.discard) == 1,
          "milling an empty deck must be a safe no-op")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_undermine.py: all checks passed — Undermine discards exactly the top 2 "
          "cards of the opponent's deck and nothing else")


if __name__ == "__main__":
    main()
