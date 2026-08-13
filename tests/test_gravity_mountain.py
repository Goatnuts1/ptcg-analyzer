#!/usr/bin/env python3
"""
test_gravity_mountain.py — Gravity Mountain (Surging Sparks 177), Stadium:
"Each Stage 2 Pokémon in play (both yours and your opponent's) gets −30 HP."

This is the engine's first HP-CHANGING effect, so the mechanics are asserted end to end:
  * InPlayPokemon.max_hp = printed HP + hp_modifier, and hp_modifier is DERIVED state
    recomputed from the live Stadium by effects.refresh_hp_modifiers() — never accumulated;
  * it hits Stage 2 Pokémon on BOTH sides, and nothing else (Basic / Stage 1 / MEGA
    Stage 1 are negative cases);
  * a Stage 2 whose damage already meets its reduced HP is Knocked Out when the Stadium
    comes into play (asserted through the real play_stadium engine action);
  * removing/replacing the Stadium restores the printed HP;
  * the max_hp floor is 10 (HP can never be reduced to 0 or below by an HP modifier).

Run: python3 tests/test_gravity_mountain.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card, CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import Action, apply_action


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    gm = db.get("Gravity Mountain")

    # --- 0. card data + registry wiring. ---
    check("Stadium" in gm.subtypes, "Gravity Mountain is a Stadium")
    check(any("Each Stage 2 Pokémon in play (both yours and your opponent's) gets -30 HP"
              in r for r in gm.rules), f"unexpected card text: {gm.rules}")
    check("Gravity Mountain" in fx.STADIUM_IMPLEMENTED,
          "Gravity Mountain must be recorded as an implemented Stadium")
    check("Gravity Mountain" in fx.STADIUM_HP_MODIFIERS,
          "Gravity Mountain must be registered as an HP-modifying Stadium")

    # --- 1. −30 for Stage 2 on BOTH sides; other stages untouched. ---
    st, a, b = fresh_state(db)
    mine_s2 = InPlayPokemon(card=db.get("Metagross"))          # Stage 2, 180 HP
    mine_s1 = InPlayPokemon(card=db.get("Metang"))             # Stage 1, 100 HP
    mine_mega = InPlayPokemon(card=db.get("Mega Excadrill ex"))  # Stage 1 MEGA, 340 HP
    theirs_s2 = InPlayPokemon(card=db.get("Metagross"))
    theirs_basic = InPlayPokemon(card=db.get("Beldum"))        # Basic, 70 HP
    a.active, a.bench = mine_s2, [mine_s1, mine_mega]
    b.active, b.bench = theirs_s2, [theirs_basic]
    st.stadium, st.stadium_owner = gm, 0
    fx.refresh_hp_modifiers(st)
    check(mine_s2.max_hp == 150 and mine_s2.remaining_hp == 150,
          f"your Stage 2 must read 150 HP, got {mine_s2.max_hp}")
    check(theirs_s2.max_hp == 150,
          f"the OPPONENT's Stage 2 must also read 150 HP, got {theirs_s2.max_hp}")
    check(mine_s1.max_hp == 100, f"NEGATIVE: a Stage 1 is untouched, got {mine_s1.max_hp}")
    check(mine_mega.max_hp == 340,
          f"NEGATIVE: a Stage 1 MEGA ex is not a Stage 2, got {mine_mega.max_hp}")
    check(theirs_basic.max_hp == 70, f"NEGATIVE: a Basic is untouched, got {theirs_basic.max_hp}")

    # --- 2. it is DERIVED, not accumulated: refreshing twice is not −60. ---
    fx.refresh_hp_modifiers(st)
    fx.refresh_hp_modifiers(st)
    check(mine_s2.max_hp == 150,
          f"repeated refreshes must not stack the modifier, got {mine_s2.max_hp}")

    # --- 3. removing the Stadium restores the printed HP. ---
    st.stadium, st.stadium_owner = None, None
    fx.refresh_hp_modifiers(st)
    check(mine_s2.max_hp == 180 and mine_s2.hp_modifier == 0,
          f"with no Stadium the printed 180 HP is back, got {mine_s2.max_hp}")

    # --- 4. NEGATIVE: a different Stadium does not reduce HP. ---
    st.stadium, st.stadium_owner = db.get("Battle Cage"), 0
    fx.refresh_hp_modifiers(st)
    check(mine_s2.max_hp == 180, f"Battle Cage must not change HP, got {mine_s2.max_hp}")

    # --- 5. KO threshold: a Metagross with 150 damage survives at 180 HP but is Knocked
    # Out the moment Gravity Mountain is in play. Asserted through the real engine
    # action, which is the only path a game takes. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Beldum"))
    a.hand = [gm]
    a.deck = [db.get("Basic Metal Energy")] * 5
    victim = InPlayPokemon(card=db.get("Metagross"), damage=150)
    b.active = victim
    b.bench = [InPlayPokemon(card=db.get("Beldum"))]           # something to promote
    b.prizes = [db.get("Basic Metal Energy")] * 6
    a.prizes = [db.get("Basic Metal Energy")] * 6
    check(not victim.is_knocked_out, "150 damage on a printed-180 HP Metagross is not a KO")
    st.active_index = 0
    apply_action(st, Action("play_stadium", hand_index=0))
    check(st.stadium is gm, "the Stadium must be in play")
    check(b.active is not victim,
          "the Stage 2 whose HP dropped to its damage total must be Knocked Out")
    check(any(c.name == "Metagross" for c in b.discard),
          f"the KO'd Metagross must be in its owner's discard, got "
          f"{[c.name for c in b.discard]}")
    check(len(a.prizes) == 5,
          f"the opponent of the KO'd Pokémon takes 1 Prize, got {len(a.prizes)} left")

    # --- 6. NEGATIVE: a Stage 2 at 140 damage survives under Gravity Mountain (150 HP). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Beldum"))
    survivor = InPlayPokemon(card=db.get("Metagross"), damage=140)
    b.active = survivor
    st.stadium, st.stadium_owner = gm, 0
    fx.process_knockouts(st)
    check(b.active is survivor and survivor.remaining_hp == 10,
          f"140 damage under a 150 HP cap survives with 10 left, got "
          f"{survivor.remaining_hp}")

    # --- 7. the max_hp floor: an HP modifier can never take a Pokémon to 0 max HP. ---
    tiny_stage2 = Card(id="test-tiny", name="Tiny Stage 2", supertype="Pokémon",
                       subtypes=("Stage 2",), hp=20, types=("Metal",), evolves_from="X",
                       evolves_to=(), abilities=(), attacks=(), rules=(), weaknesses=(),
                       resistances=(), retreat_cost=0, regulation_mark="H")
    tiny = InPlayPokemon(card=tiny_stage2)
    st, a, b = fresh_state(db)
    a.active = tiny
    st.stadium, st.stadium_owner = gm, 0
    fx.refresh_hp_modifiers(st)
    check(tiny.max_hp == 10, f"max_hp floors at 10, got {tiny.max_hp}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_gravity_mountain.py: all checks passed — Gravity Mountain takes 30 HP off "
          "every Stage 2 on both sides, KOs the ones it drops to zero, and reverses cleanly")


if __name__ == "__main__":
    main()
