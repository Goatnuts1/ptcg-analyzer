#!/usr/bin/env python3
"""
test_new_cards.py — the core-stabilization staples. Each new effect is asserted to
do EXACTLY what its card text says (the project's "implemented = tested" gate).

Covers: Carmine, Lacey, Kofu, Cyrano, Colress's Tenacity, Lana's Aid, Drayton,
Hassel, Poké Ball, Master Ball, Dusk Ball, Pokégear 3.0, Energy Switch,
Energy Recycler, Sacred Ash, Pokémon Catcher, and Klefki's Stick 'n' Draw.

Run from project root:  python3 tests/test_new_cards.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx(st, me, opp, rng=None):
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=rng or st.rng)


class _Coin:
    """Deterministic coin for flip tests. randint(0,1) -> fixed; shuffle is a no-op."""
    def __init__(self, heads): self._v = 1 if heads else 0
    def randint(self, a, b): return self._v
    def shuffle(self, seq): pass
    def random(self): return 0.0


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    EX = db.get("Dragapult ex")        # Stage 2 + ex (Rule Box)
    EX2 = db.get("Raging Bolt ex")     # Basic + ex (Rule Box)
    DREEPY = db.get("Dreepy")          # Basic, non-Rule-Box
    DRAKLOAK = db.get("Drakloak")      # Stage 1
    BOSS = db.get("Boss's Orders")     # Supporter (Trainer)
    STAD = db.get("Battle Cage")       # Stadium
    FIRE = db.get("Basic Fire Energy")
    WATER = db.get("Basic Water Energy")

    # --- Carmine: discard your hand, draw 5. ---
    st, a, b = fresh(db)
    a.hand = [FIRE, WATER]
    a.deck = [DREEPY] * 10
    fx._carmine(ctx(st, a, b))
    check(len(a.hand) == 5 and FIRE in a.discard and WATER in a.discard,
          f"Carmine: discard hand + draw 5 (hand={len(a.hand)}, discard={len(a.discard)})")

    # --- Lacey: shuffle hand into deck, draw 4 (8 if opp has <=3 prizes left). ---
    st, a, b = fresh(db)
    a.hand = [FIRE, WATER]; a.deck = [DREEPY] * 10; b.prizes = [DREEPY] * 4
    fx._lacey(ctx(st, a, b))
    check(len(a.hand) == 4, f"Lacey: draw 4 when opp has >3 prizes (hand={len(a.hand)})")
    st, a, b = fresh(db)
    a.hand = [FIRE]; a.deck = [DREEPY] * 12; b.prizes = [DREEPY] * 3
    fx._lacey(ctx(st, a, b))
    check(len(a.hand) == 8, f"Lacey: draw 8 when opp has <=3 prizes (hand={len(a.hand)})")

    # --- Kofu: put 2 from hand on bottom of deck, draw 4. ---
    st, a, b = fresh(db)
    a.hand = [FIRE, WATER, EX]          # 3 cards (Kofu already popped)
    a.deck = [DREEPY] * 10
    ok = fx._kofu(ctx(st, a, b))
    check(ok and len(a.hand) == 5, f"Kofu: 3-2+4 = 5 in hand (got {len(a.hand)})")
    check(a.deck[-2:].count(FIRE) + a.deck[-2:].count(WATER) == 2,
          "Kofu: the 2 bottomed (lowest-value) cards are at the deck bottom")
    st, a, b = fresh(db)
    a.hand = [FIRE]
    check(fx._kofu(ctx(st, a, b)) is False, "Kofu: can't be used with <2 cards in hand")

    # --- Cyrano: search up to 3 Pokémon ex into hand. ---
    st, a, b = fresh(db)
    a.deck = [EX, EX2, DREEPY]
    n = fx._cyrano(ctx(st, a, b))
    check(EX in a.hand and EX2 in a.hand and DREEPY in a.deck,
          "Cyrano: fetch the Pokémon ex, leave the non-ex")

    # --- Colress's Tenacity: a Stadium AND an Energy into hand. ---
    st, a, b = fresh(db)
    a.deck = [STAD, FIRE, DREEPY]
    fx._colress_tenacity(ctx(st, a, b))
    check(STAD in a.hand and FIRE in a.hand and DREEPY in a.deck,
          "Colress's Tenacity: fetch a Stadium + an Energy")

    # --- Lana's Aid: up to 3 (non-Rule-Box Pokémon / Basic Energy) from discard. ---
    st, a, b = fresh(db)
    a.discard = [DREEPY, FIRE, EX]      # EX has a Rule Box -> excluded
    fx._lanas_aid(ctx(st, a, b))
    check(DREEPY in a.hand and FIRE in a.hand, "Lana's Aid: recover the Dreepy + Energy")
    check(EX in a.discard, "Lana's Aid: must NOT recover a Rule-Box Pokémon")

    # --- Drayton: look top 7, take a Pokémon + a Trainer. ---
    st, a, b = fresh(db)
    a.deck = [DREEPY, BOSS, FIRE, FIRE, FIRE, FIRE, FIRE]
    fx._drayton(ctx(st, a, b))
    check(DREEPY in a.hand and BOSS in a.hand,
          "Drayton: take one Pokémon + one Trainer from the top 7")

    # --- Hassel: look top 8, take up to 3 (the effect itself; KO-gate is can_play). ---
    st, a, b = fresh(db)
    a.deck = [DREEPY, EX, BOSS, FIRE, WATER, DREEPY, EX, FIRE]
    fx._hassel(ctx(st, a, b))
    check(len(a.hand) == 3, f"Hassel: take up to 3 of the top 8 (hand={len(a.hand)})")

    # --- Poké Ball: flip; heads -> search a Pokémon. ---
    st, a, b = fresh(db)
    a.deck = [DREEPY]
    fx._poke_ball(ctx(st, a, b, rng=_Coin(heads=True)))
    check(DREEPY in a.hand, "Poké Ball heads: search a Pokémon to hand")
    st, a, b = fresh(db)
    a.deck = [DREEPY]
    fx._poke_ball(ctx(st, a, b, rng=_Coin(heads=False)))
    check(DREEPY in a.deck and not a.hand, "Poké Ball tails: nothing found")

    # --- Master Ball: search ANY Pokémon (incl. ex). ---
    st, a, b = fresh(db)
    a.deck = [EX, FIRE]
    fx._master_ball(ctx(st, a, b))
    check(EX in a.hand, "Master Ball: search any Pokémon (the ex) to hand")

    # --- Dusk Ball: look at the BOTTOM 7, take a Pokémon. ---
    st, a, b = fresh(db)
    a.deck = [WATER, FIRE, FIRE, FIRE, FIRE, FIRE, DREEPY]   # DREEPY in the bottom 7
    fx._dusk_ball(ctx(st, a, b))
    check(DREEPY in a.hand, "Dusk Ball: take a Pokémon from the bottom 7")

    # --- Pokégear 3.0: look top 7, take a Supporter. ---
    st, a, b = fresh(db)
    a.deck = [BOSS, FIRE, FIRE, FIRE, FIRE, FIRE, FIRE]
    fx._pokegear(ctx(st, a, b))
    check(BOSS in a.hand, "Pokégear 3.0: take a Supporter from the top 7")

    # --- Energy Switch: move a Basic Energy from a Benched Pokémon to the Active. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=DREEPY)
    donor = InPlayPokemon(card=DRAKLOAK, energy=[FIRE])
    a.bench = [donor]
    ok = fx._energy_switch(ctx(st, a, b))
    check(ok and a.active.energy and a.active.energy[0] is FIRE and not donor.energy,
          "Energy Switch: move the Basic Energy onto the Active")

    # --- Energy Recycler: shuffle up to 5 Basic Energy from discard into deck. ---
    st, a, b = fresh(db)
    a.discard = [FIRE] * 6
    fx._energy_recycler(ctx(st, a, b))
    check(a.discard.count(FIRE) == 1 and a.deck.count(FIRE) == 5,
          f"Energy Recycler: move 5/6 to deck (deck={a.deck.count(FIRE)}, disc={a.discard.count(FIRE)})")

    # --- Sacred Ash: shuffle up to 5 Pokémon from discard into deck. ---
    st, a, b = fresh(db)
    a.discard = [DREEPY] * 6
    fx._sacred_ash(ctx(st, a, b))
    check(a.discard.count(DREEPY) == 1 and a.deck.count(DREEPY) == 5,
          f"Sacred Ash: move 5/6 Pokémon to deck (deck={a.deck.count(DREEPY)})")

    # --- Pokémon Catcher: flip; heads -> gust a Benched opponent into the Active. ---
    st, a, b = fresh(db)
    b.active = InPlayPokemon(card=DREEPY)
    benched = InPlayPokemon(card=DRAKLOAK)
    b.bench = [benched]
    fx._pokemon_catcher(ctx(st, a, b, rng=_Coin(heads=True)))
    check(b.active is benched and any(m.card.name == "Dreepy" for m in b.bench),
          "Pokémon Catcher heads: drag up the benched opponent")
    st, a, b = fresh(db)
    b.active = InPlayPokemon(card=DREEPY); b.bench = [InPlayPokemon(card=DRAKLOAK)]
    fx._pokemon_catcher(ctx(st, a, b, rng=_Coin(heads=False)))
    check(b.active.card.name == "Dreepy", "Pokémon Catcher tails: no switch")

    # --- Klefki Stick 'n' Draw: discard a card, draw 2. ---
    st, a, b = fresh(db)
    a.hand = [FIRE, WATER]; a.deck = [DREEPY] * 3
    fx._stick_n_draw(fx.EffectContext(state=st, me=a, opp=b,
                                      source=InPlayPokemon(card=db.get("Klefki")),
                                      db=st.db, rng=st.rng))
    check(len(a.hand) == 3 and len(a.discard) == 1,
          f"Stick 'n' Draw: -1 discard +2 draw (hand={len(a.hand)}, disc={len(a.discard)})")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — core-stabilization staples (17 cards) all match card text: Carmine, Lacey, "
          "Kofu, Cyrano, Colress's Tenacity, Lana's Aid, Drayton, Hassel, Poké Ball, "
          "Master Ball, Dusk Ball, Pokégear 3.0, Energy Switch, Energy Recycler, Sacred Ash, "
          "Pokémon Catcher, Stick 'n' Draw.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
