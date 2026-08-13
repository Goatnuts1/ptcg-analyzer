#!/usr/bin/env python3
"""
test_koraidon_ex_asc.py — assert "Koraidon ex (ASC)" (Ascended Heroes 121, the
REAL print James Kowalski's NAIC 2026-winning Clefairy/Kangaskhan list runs) is
a genuinely different card from the pool's plain "Koraidon ex" (Temporal Forces
120), and does EXACTLY what its own card text says.

Card text (scan-verified via LimitlessTCG this session, quoted at each
assertion site):

  Koraidon ex (ASC 121, Basic Fighting Tera ex, 230 HP, Weakness Psychic):
    Rule "Tera": "As long as this Pokémon is on your Bench, prevent all
      damage done to this Pokémon by attacks (both yours and your
      opponent's)."
    Attack "Orichalcum Fang" [F][C] 50+: "If any of your Pokémon were
      Knocked Out by damage from an attack during your opponent's last
      turn, this attack does 120 more damage."
    Attack "Impact Blow" [F][F][C] 200: "During your next turn, this
      Pokémon can't use Impact Blow."

Run from project root:  python3 tests/test_koraidon_ex_asc.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game, effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    a.prizes = [db.get("Basic Fire Energy")] * 6
    b.prizes = [db.get("Basic Fire Energy")] * 6
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.turns_taken = b.turns_taken = 5
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    card = db.get("Koraidon ex (ASC)")

    # --- 0. Print sanity: genuinely different from the pool's bare "Koraidon ex"
    # (Temporal Forces 120 — Dragon type, no ability, no Weakness). ---
    other = db.get("Koraidon ex")
    check(card.hp == 230 and card.types == ("Fighting",),
          f"ASC 121 print should be 230 HP Fighting, got {card.hp} {card.types}")
    check("Tera" in card.subtypes, "ASC 121 should carry the Tera subtype")
    check(other.types == ("Dragon",),
          f"the bare pool print should remain the Dragon-type TEF 120, got {other.types}")

    # =================================================================== #
    # ORICHALCUM FANG
    # =================================================================== #

    # --- 1a. Base 50, no bonus without a prior-turn KO. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=card)
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.koed_last_turn = False
    st.active_index = 0
    of_i = next(i for i, atk in enumerate(card.attacks) if atk.name == "Orichalcum Fang")
    game._resolve_attack(st, of_i)
    check(b.active.damage == 50, f"Orichalcum Fang base should be 50, got {b.active.damage}")

    # --- 1b. +120 (170 total) when a Pokémon of ours was KO'd during the
    # opponent's last turn. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=card)
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.koed_last_turn = True
    st.active_index = 0
    game._resolve_attack(st, of_i)
    check(b.active.damage == 170,
          f"Orichalcum Fang with a prior KO should be 50+120=170, got {b.active.damage}")

    # =================================================================== #
    # TERA — bench damage immunity (generic engine chokepoint, subtype-driven)
    # =================================================================== #

    st, a, b = fresh_state(db)
    benched = InPlayPokemon(card=card)
    a.active = InPlayPokemon(card=db.get("Dreepy"))
    a.bench = [benched]
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    ctx = fx.EffectContext(state=st, me=b, opp=a, source=attacker, db=db, rng=st.rng)
    dealt = fx.apply_attack_damage(ctx, benched, 300, owner=a, source=attacker)
    check(dealt == 0 and benched.damage == 0,
          f"Tera should prevent all attack damage while on the Bench, dealt={dealt}")

    # =================================================================== #
    # IMPACT BLOW
    # =================================================================== #

    st, a, b = fresh_state(db)
    k = InPlayPokemon(card=card)
    a.active = k
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    ib_i = next(i for i, atk in enumerate(card.attacks) if atk.name == "Impact Blow")
    game._resolve_attack(st, ib_i)
    check(b.active.damage == 200, f"Impact Blow should deal exactly 200, got {b.active.damage}")
    check("Impact Blow" in k.pending_locked_attacks,
          "Impact Blow should arm its own next-turn lock")
    check("Orichalcum Fang" not in k.pending_locked_attacks,
          "the lock must be scoped to Impact Blow only — Orichalcum Fang stays usable")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Koraidon ex (ASC 121): correct print (distinct from the pool's "
          "bare Koraidon ex), Orichalcum Fang's KO-triggered bonus, Tera's bench "
          "immunity, and Impact Blow's self-scoped lock all hold.")


if __name__ == "__main__":
    main()
