#!/usr/bin/env python3
"""
test_conditions.py — Special Conditions framework (MILESTONE §2.6).

Confusion (Munkidori Mind Bend), can't-retreat (Dusknoir Shadow Bind), and
can't-play-Items (Budew Itchy Pollen). Asserts the rider effects + their timing
(turn-scoped debuffs active for exactly the opponent's next turn; Confusion clears
off the Active Spot).

Run from project root:  python3 tests/test_conditions.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game, effects as fx


class _Tails:                      # forces Confusion's coin flip to tails
    def randint(self, a, b): return 0
    def shuffle(self, x): pass


def fresh(db, rng=None):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=rng or random.Random(0))
    st.db = db
    st.turn_number = 5
    a.turns_taken = b.turns_taken = 5
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

    # --- Mind Bend: sets Confusion on the opponent's Active. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Munkidori"))
    b.active = InPlayPokemon(card=PULT)
    fx._mind_bend(fx.EffectContext(state=st, me=a, opp=b, source=a.active, db=db, rng=st.rng))
    check(b.active.confused, "Mind Bend should Confuse the opponent's Active")

    # --- Confused attacker, tails: 30 to itself, attack fails (no damage to opp). ---
    st, a, b = fresh(db, rng=_Tails())
    a.active = InPlayPokemon(card=PULT, energy=[FIRE, db.get("Basic Psychic Energy")])
    a.active.confused = True
    b.active = InPlayPokemon(card=PULT)
    st.active_index = 0
    pd = next(i for i, atk in enumerate(a.active.card.attacks) if atk.name == "Phantom Dive")
    game._resolve_attack(st, pd)
    check(a.active is not None and a.active.damage == 30, "Confusion tails: 30 to itself")
    check(b.active.damage == 0, "Confusion tails: the attack should do nothing to the opponent")

    # --- Confusion clears when the Pokémon leaves the Active Spot (retreat). ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT, energy=[FIRE, FIRE], confused=True)
    a.bench = [InPlayPokemon(card=DREEPY)]
    game.apply_action(st, game.Action("retreat", target_index=0))
    benched = [m for m in a.bench if m.card.name == "Dragapult ex"][0]
    check(not benched.confused, "Confusion should clear when the Pokémon retreats to the Bench")

    # --- Shadow Bind: opponent can't retreat during their next turn (then clears). ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Dusknoir"))
    b.active = InPlayPokemon(card=PULT, energy=[FIRE, FIRE])   # could retreat if not locked
    b.bench = [InPlayPokemon(card=DREEPY)]
    b.deck = [DREEPY] * 5
    fx._shadow_bind(fx.EffectContext(state=st, me=a, opp=b, source=a.active, db=db, rng=st.rng))
    check(b.pending_cant_retreat, "Shadow Bind should arm the opponent's can't-retreat")
    st.active_index = 1
    game.start_turn(st)                       # b's turn begins
    check(b.cant_retreat and not b.pending_cant_retreat, "can't-retreat should activate for b's turn")
    acts = game.legal_actions(st)
    check(not any(x.kind == "retreat" for x in acts), "retreat must NOT be offered while locked")
    game.start_turn(st)                       # b's following turn
    check(not b.cant_retreat, "can't-retreat should clear after one turn")

    # --- Itchy Pollen: opponent can't play Item cards next turn (Supporters still OK). ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Budew"))
    b.active = InPlayPokemon(card=PULT)
    b.deck = [DREEPY] * 5
    b.hand = [db.get("Ultra Ball"), db.get("Lillie's Determination")]   # an Item + a Supporter
    fx._itchy_pollen(fx.EffectContext(state=st, me=a, opp=b, source=a.active, db=db, rng=st.rng))
    st.active_index = 1
    game.start_turn(st)
    check(b.cant_play_items, "Itchy Pollen should lock b's Items for their turn")
    names = [b.hand[x.hand_index].name for x in game.legal_actions(st) if x.kind == "play_trainer"]
    check("Ultra Ball" not in names, "the Item (Ultra Ball) must be locked out")
    check("Lillie's Determination" in names, "a Supporter should still be playable under Item-lock")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Special Conditions: Confusion (set/tails/clear), Shadow Bind (no-retreat, "
          "one turn), Itchy Pollen (Item-lock, Supporters exempt) all hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
