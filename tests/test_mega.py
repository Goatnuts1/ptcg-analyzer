#!/usr/bin/env python3
"""
test_mega.py — Mega Evolution Pokémon ex rules (MILESTONE §2.9).

Verified against the OFFICIAL 2026 web rulebook (Appendix 1 p23, glossary p43):
the CURRENT "Mega Evolution Pokémon ex" (lowercase ex — Mega Charizard X/Y ex)
have **no special play rules**. In particular:
  - Mega-Evolving does NOT end your turn. (The turn-ending rule belonged to the
    rotated XY-era "Mega Evolution Pokémon-EX", uppercase — not these cards.)
  - They follow normal Evolution rules (direct evolve, or via Rare Candy).
  - A Mega Evolution Pokémon ex gives up 3 Prize cards when Knocked Out.

Run from project root:  python3 tests/test_mega.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.turns_taken = 5            # past the no-evolve-turn-1 rule
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # ----------------------------------------------------------------- #
    # 1. Direct evolve Charmeleon -> Mega Charizard X ex does NOT end the turn.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Charmeleon"))
    a.hand = [db.get("Mega Charizard X ex")]
    st.active_index = 0
    game.apply_action(st, game.Action("evolve", hand_index=0, target_index=-1))
    check(a.active.card.name == "Mega Charizard X ex", "Charmeleon should evolve to the MEGA")
    check(st.phase == Phase.MAIN,
          f"Mega-Evolving a current Mega ex must NOT end the turn, phase={st.phase}")

    # ----------------------------------------------------------------- #
    # 2. Rare Candy Charmander -> Mega Charizard X ex also does NOT end the turn.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    charmander = InPlayPokemon(card=db.get("Charmander"))
    charmander.played_this_turn = False
    a.active = charmander
    a.hand = [db.get("Rare Candy"), db.get("Mega Charizard X ex")]
    st.active_index = 0
    rc_index = next(i for i, c in enumerate(a.hand) if c.name == "Rare Candy")
    game.apply_action(st, game.Action("play_trainer", hand_index=rc_index))
    check(a.active.card.name == "Mega Charizard X ex",
          "Rare Candy should skip Charmeleon straight to the MEGA")
    check(st.phase == Phase.MAIN,
          f"Mega-Evolving via Rare Candy must NOT end the turn, phase={st.phase}")

    # ----------------------------------------------------------------- #
    # 3. A normal (non-MEGA) evolution also does not end the turn (control).
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Charmander"))
    a.hand = [db.get("Charmeleon")]
    st.active_index = 0
    game.apply_action(st, game.Action("evolve", hand_index=0, target_index=-1))
    check(a.active.card.name == "Charmeleon" and st.phase == Phase.MAIN,
          f"a normal evolution should not end the turn, phase={st.phase}")

    # ----------------------------------------------------------------- #
    # 4. Mega Evolution Pokémon ex give up 3 prizes.
    # ----------------------------------------------------------------- #
    check(db.get("Mega Charizard X ex").gives_up_prizes == 3,
          "Mega Charizard X ex should give up 3 prizes")
    check(db.get("Mega Charizard Y ex").gives_up_prizes == 3,
          "Mega Charizard Y ex should give up 3 prizes")

    # ----------------------------------------------------------------- #
    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Mega ex rules hold: Mega-Evolving does NOT end the turn (current ex), "
          "normal evolution rules apply, MEGA gives 3 prizes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
