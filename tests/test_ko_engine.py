#!/usr/bin/env python3
"""
test_ko_engine.py — KO / damage-manipulation engine (MILESTONE §2.7).

Covers Cursed Blast (self-KO awards the opponent a prize), Adrena-Brain (move
counters), Flip the Script (KO'd-last-turn draw), Cruel Arrow and Explosion Y
(damage to a chosen Pokémon). Asserts each matches its card text.

Run from project root:  python3 tests/test_ko_engine.py
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


def ctx(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    DREEPY = db.get("Dreepy")          # 70 HP, 1 prize
    PULT = db.get("Dragapult ex")      # 320 HP survivor, 2 prizes
    FIRE = db.get("Basic Fire Energy")
    DARK = db.get("Basic Darkness Energy")

    # --- Cursed Blast (Dusknoir, 13 counters): KO an opp Pokémon + self-KO. ---
    st, a, b = fresh(db)
    st.active_index = 0
    dusknoir = InPlayPokemon(card=db.get("Dusknoir"))
    a.active = dusknoir
    a.bench = [InPlayPokemon(card=DREEPY)]          # to promote after the self-KO
    b.active = InPlayPokemon(card=PULT)             # survivor
    victim = InPlayPokemon(card=DREEPY)             # 70 HP -> 130 KOs it
    b.bench = [victim]
    a.prizes = [DREEPY] * 6
    b.prizes = [DREEPY] * 6
    fx._cursed_blast_13(ctx(st, a, b, source=dusknoir))
    fx.process_knockouts(st)
    check(DREEPY in b.discard and victim not in b.bench, "Cursed Blast should KO the benched victim")
    check(len(a.prizes) == 5, f"attacker takes 1 prize for the victim (prizes={len(a.prizes)})")
    check(any(c.name == "Dusknoir" for c in a.discard), "Dusknoir should KO itself (the cost)")
    check(len(b.prizes) == 5, f"OPPONENT takes 1 prize for the self-KO (b.prizes={len(b.prizes)})")
    check(a.active is not None and a.active.card.name == "Dreepy", "a should promote from the bench")

    # --- Cursed Blast (Dusclops, 5 counters = 50): finish a softened target + self-KO. ---
    st, a, b = fresh(db)
    st.active_index = 0
    dusclops = InPlayPokemon(card=db.get("Dusclops"))
    a.active = dusclops
    a.bench = [InPlayPokemon(card=DREEPY)]
    b.active = InPlayPokemon(card=PULT)
    softened = InPlayPokemon(card=DREEPY, damage=30)   # 40 left -> 50 KOs it
    b.bench = [softened]
    a.prizes = [DREEPY] * 6
    b.prizes = [DREEPY] * 6
    fx._cursed_blast_5(ctx(st, a, b, source=dusclops))
    fx.process_knockouts(st)
    check(softened not in b.bench and len(a.prizes) == 5, "Dusclops Cursed Blast (50) should KO the softened target")
    check(any(c.name == "Dusclops" for c in a.discard) and len(b.prizes) == 5,
          "Dusclops should self-KO and give the opponent a prize")

    # --- Adrena-Brain (Munkidori): move up to 3 counters from yours to opp's. ---
    st, a, b = fresh(db)
    munk = InPlayPokemon(card=db.get("Munkidori"), energy=[DARK])
    a.active = munk
    donor = InPlayPokemon(card=PULT, damage=30)     # 3 counters to move
    a.bench = [donor]
    b.active = InPlayPokemon(card=PULT)             # full, won't be KO'd by 30
    fx._adrena_brain(ctx(st, a, b, source=munk))
    check(donor.damage == 0, f"donor should lose the 3 moved counters (damage={donor.damage})")
    check(b.active.damage == 30, f"opponent should gain 30 (damage={b.active.damage})")

    # --- Flip the Script (Fezandipiti): draw 3 only if KO'd last turn. ---
    st, a, b = fresh(db)
    fez = InPlayPokemon(card=db.get("Fezandipiti ex"))
    a.active = fez
    a.deck = [DREEPY] * 10
    a.koed_last_turn = True
    fx._flip_the_script(ctx(st, a, b, source=fez))
    check(len(a.hand) == 3, f"Flip the Script should draw 3 when KO'd last turn (hand={len(a.hand)})")
    st, a, b = fresh(db)
    a.active = fez; a.deck = [DREEPY] * 10; a.koed_last_turn = False
    fx._flip_the_script(ctx(st, a, b, source=fez))
    check(len(a.hand) == 0, "Flip the Script should do nothing if NOT KO'd last turn")

    # --- Cruel Arrow (Fezandipiti): 100 to a chosen opp Pokémon (KOs a 70-HP bench). ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Fezandipiti ex"))
    b.active = InPlayPokemon(card=PULT)
    bench_target = InPlayPokemon(card=DREEPY)       # 70 HP
    b.bench = [bench_target]
    fx._cruel_arrow(ctx(st, a, b, source=a.active))
    check(bench_target.damage == 100, f"Cruel Arrow should put 100 on the bench target (={bench_target.damage})")

    # --- Explosion Y (Mega Charizard Y ex): discard 3 Energy, 280 to a target. ---
    st, a, b = fresh(db)
    mcy = InPlayPokemon(card=db.get("Mega Charizard Y ex"), energy=[FIRE, FIRE, FIRE, FIRE])
    a.active = mcy
    b.active = InPlayPokemon(card=PULT)             # 320 HP, no Fire weakness -> survives 280
    fx._explosion_y(ctx(st, a, b, source=mcy))
    check(len(mcy.energy) == 1, f"Explosion Y should discard exactly 3 Energy (left={len(mcy.energy)})")
    check(len(a.discard) == 3, "the 3 discarded Energy should be in discard")
    check(b.active.damage == 280, f"Explosion Y should deal 280 (damage={b.active.damage})")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — KO engine: Cursed Blast (self-KO awards opp), Adrena-Brain, Flip the Script, "
          "Cruel Arrow, Explosion Y all match card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
