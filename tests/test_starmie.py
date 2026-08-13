#!/usr/bin/env python3
"""
test_starmie.py — assert Mega Starmie ex and its pre-evolution Staryu do EXACTLY
what their card text says (both newly added to data/standard_pool.json this
session as me3-21 / me3-20, Perfect Order, regulation mark J; text verified
against limitlesstcg.com/cards/POR/20 and /21 this session).

Covers:
  - Staryu: plain "Water Gun" [W] 20 damage, no text.
  - Mega Starmie ex "Jetting Blow" [W] 120 + 50 bench-spread (bench damage does
    NOT apply Weakness/Resistance, per engine convention).
  - Mega Starmie ex "Nebula Beam" [CCC] 210, "isn't affected by Weakness or
    Resistance, or by any effects on your opponent's Active Pokémon" — the
    CRITICAL wall-bypass case: a defender with Crustle's "Mysterious Rock Inn"
    (Prevent all damage done to this Pokémon by attacks from your opponent's
    Pokémon ex) active must take the FULL 210 unprevented from Nebula Beam,
    while the SAME defender takes 0 from Jetting Blow's main hit (proving the
    bypass is attack-specific to Nebula Beam, not a blanket wall-disable on
    this card). Also covers weakness-ignoring on Nebula Beam vs weakness-
    applying on Jetting Blow's main hit, and negative/no-crash cases.

Run from project root:  python3 tests/test_starmie.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db                    # effects read state.db for searches/chains
    st.turn_number = 5            # past turn-1 attack restriction
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source,
                            db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # =================================================================== #
    # STARYU (me3-20, Basic, Water, HP 70, Weakness Lightning x2, Retreat 1)
    # Attack "Water Gun" [W] -> 20 damage. (no text)
    # =================================================================== #

    staryu_card = db.get("Staryu")
    check(staryu_card.hp == 70, f"Staryu should be 70 HP, got {staryu_card.hp}")
    check(tuple(staryu_card.types) == ("Water",),
          f"Staryu should be Water-typed, got {staryu_card.types}")
    check(any(w == ("Lightning", "×2") for w in staryu_card.weaknesses),
          f"Staryu should be Weak to Lightning x2, got {staryu_card.weaknesses}")
    check(staryu_card.evolves_to == ("Mega Starmie ex",) or "Mega Starmie ex" in staryu_card.evolves_to,
          f"Staryu should evolve into Mega Starmie ex, got {staryu_card.evolves_to}")

    # --- 1a. POSITIVE: Water Gun deals exactly 20 damage, no side effects, no crash. ---
    st, a, b = fresh_state(db)
    staryu = InPlayPokemon(card=staryu_card)
    a.active = staryu
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))   # 320 HP, no Weakness listed
    st.active_index = 0
    wg_i = next(i for i, atk in enumerate(staryu.card.attacks) if atk.name == "Water Gun")
    game._resolve_attack(st, wg_i)
    check(b.active is not None and b.active.damage == 20,
          f"Water Gun should deal exactly 20 plain damage, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(len(b.bench) == 0, "Water Gun must not touch the bench (no text)")

    # =================================================================== #
    # MEGA STARMIE EX (me3-21, Stage 1 MEGA ex, Water, HP 330, Weakness
    # Lightning x2, Retreat 2, evolves from Staryu)
    # =================================================================== #

    starmie_card = db.get("Mega Starmie ex")
    check(starmie_card.hp == 330, f"Mega Starmie ex should be 330 HP, got {starmie_card.hp}")
    check(starmie_card.evolves_from == "Staryu",
          f"Mega Starmie ex should evolve from Staryu, got {starmie_card.evolves_from}")
    check("ex" in starmie_card.subtypes and "MEGA" in starmie_card.subtypes,
          f"Mega Starmie ex must carry both MEGA and ex subtypes, got {starmie_card.subtypes}")
    check(starmie_card.gives_up_prizes == 3,
          f"a Mega Evolution Pokémon ex must give up 3 prizes on KO, got "
          f"{starmie_card.gives_up_prizes}")

    # =================================================================== #
    # Attack "Jetting Blow" [W] 120 (pool text): "This attack also does 50
    # damage to 1 of your opponent's Benched Pokémon. (Don't apply Weakness
    # and Resistance for Benched Pokémon.)"
    # =================================================================== #

    # --- 2a. POSITIVE: 120 to Active + 50 to the (single) Benched Pokémon. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))          # 320 HP, no Weakness
    bench_mon = InPlayPokemon(card=db.get("Dwebble"))
    b.bench = [bench_mon]
    st.active_index = 0
    jb_i = next(i for i, atk in enumerate(starmie.card.attacks) if atk.name == "Jetting Blow")
    game._resolve_attack(st, jb_i)
    check(b.active is not None and b.active.damage == 120,
          f"Jetting Blow should deal 120 to the Active, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(bench_mon.damage == 50,
          f"Jetting Blow should also deal 50 to the (only) Benched Pokémon, got "
          f"{bench_mon.damage}")

    # --- 2b. Bench damage does NOT apply Weakness: bench victim is weak to Water
    # (Ponyta) yet still only takes the flat 50, not 100. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    ponyta = InPlayPokemon(card=db.get("Ponyta"))                  # Fire, Weak Water x2
    b.bench = [ponyta]
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(ponyta.damage == 50,
          f"Jetting Blow's bench hit must NOT apply Weakness (flat 50 even though "
          f"Ponyta is Weak to Water x2), got {ponyta.damage}")

    # --- 2c. Weakness DOES apply to Jetting Blow's main (Active) hit — this is a
    # plain engine-applied base hit, not owned by the effect. Magcargo ex (270 HP,
    # Weak Water x2) takes 120*2=240, not 120. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    magcargo = InPlayPokemon(card=db.get("Magcargo ex"))           # Fire, 270 HP, Weak Water x2
    b.active = magcargo
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(magcargo.damage == 240,
          f"Jetting Blow's main hit must apply Weakness normally (120*2=240 vs "
          f"Water-weak Magcargo ex), got {magcargo.damage}")

    # --- 2d. Targeting: with 2 Benched Pokémon, the 50 lands on the LOWEST
    # remaining-HP one (gust/Break-Through style v0 policy). ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    low_hp_mon = InPlayPokemon(card=db.get("Dwebble"))             # 70 HP
    low_hp_mon.damage = 60                                          # remaining_hp = 10
    high_hp_mon = InPlayPokemon(card=db.get("Crustle"))            # 150 HP, undamaged
    b.bench = [high_hp_mon, low_hp_mon]
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(low_hp_mon.damage == 60 + 50,
          f"Jetting Blow should target the LOWEST remaining-HP bencher, got "
          f"low_hp_mon.damage={low_hp_mon.damage}")
    check(high_hp_mon.damage == 0,
          f"the higher-HP bencher should be untouched, got high_hp_mon.damage={high_hp_mon.damage}")

    # --- 2e. NEGATIVE: no Benched Pokémon -> only the 120 main hit, no crash. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.bench = []
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(b.active is not None and b.active.damage == 120,
          f"Jetting Blow with an empty bench should still deal 120 to the Active "
          f"with no crash, got {b.active.damage if b.active else 'KO'}")

    # =================================================================== #
    # THE CRITICAL CASE — Crustle's "Mysterious Rock Inn" ability (pool text):
    # "Prevent all damage done to this Pokémon by attacks from your opponent's
    # Pokémon ex." Mega Starmie ex IS a Pokémon ex (subtypes include 'ex'), so
    # the wall's precondition IS met for both of its attacks. Nebula Beam's
    # "isn't affected by ... any effects on your opponent's Active Pokémon"
    # must bypass it (ignore_active_effects=True, same chokepoint as Superb
    # Scissors/Demolish); Jetting Blow carries NO such text and must be fully
    # blocked, proving the bypass is attack-specific, not a blanket wall-disable
    # for this card.
    # =================================================================== #

    # --- 3a. Jetting Blow's main hit is FULLY PREVENTED (0 damage) by Mysterious
    # Rock Inn on the SAME defender used in 3b below. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    crustle = InPlayPokemon(card=db.get("Crustle"))                # Mysterious Rock Inn
    b.active = crustle
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(crustle.damage == 0,
          f"Jetting Blow's main hit must be FULLY PREVENTED by Mysterious Rock Inn "
          f"(Mega Starmie ex is a Pokémon ex), got {crustle.damage}")

    # --- 3b. THE CRITICAL ASSERTION: Nebula Beam vs the SAME wall-active Crustle
    # deals the FULL 210, completely unprevented. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    crustle = InPlayPokemon(card=db.get("Crustle"))                # Mysterious Rock Inn, 150 HP
    b.active = crustle
    st.active_index = 0
    nb_i = next(i for i, atk in enumerate(starmie.card.attacks) if atk.name == "Nebula Beam")
    check(fx.wall_prevents_damage(st, crustle, starmie),
          "setup sanity: Mysterious Rock Inn must be an ACTIVE wall against Mega "
          "Starmie ex (a Pokémon ex) before we assert the bypass")
    game._resolve_attack(st, nb_i)
    check(crustle.damage == 210,
          f"Nebula Beam MUST deal the full 210, unprevented by Mysterious Rock Inn "
          f"(bypassed via ignore_active_effects, same mechanism as Superb Scissors/"
          f"Demolish), got {crustle.damage}")

    # --- 3c. Ability suppression on Crustle: with the wall suppressed, Jetting
    # Blow's main hit now goes through normally too (confirms 3a was really the
    # wall, not some other block). ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    crustle = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle
    st.active_index = 0
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        game._resolve_attack(st, jb_i)
        check(crustle.damage == 120,
              f"with Mysterious Rock Inn suppressed, Jetting Blow's main hit should "
              f"land normally for 120, got {crustle.damage}")
    finally:
        fx.ability_suppressed = orig_suppressed

    # =================================================================== #
    # Attack "Nebula Beam" [CCC] 210 (pool text): "This attack's damage isn't
    # affected by Weakness or Resistance, or by any effects on your opponent's
    # Active Pokémon."
    # =================================================================== #

    # --- 4a. POSITIVE, no wall in play: plain 210 damage. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))          # 320 HP, no Weakness
    st.active_index = 0
    game._resolve_attack(st, nb_i)
    check(b.active is not None and b.active.damage == 210,
          f"Nebula Beam should deal exactly 210 with no wall/weakness in play, got "
          f"{b.active.damage if b.active else 'KO'}")

    # --- 4b. Weakness is IGNORED: Magcargo ex (270 HP, Weak Water x2) takes 210,
    # not 420 (would OTKO through a 270-HP wall if doubled). ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    magcargo = InPlayPokemon(card=db.get("Magcargo ex"))
    b.active = magcargo
    st.active_index = 0
    game._resolve_attack(st, nb_i)
    check(magcargo.damage == 210,
          f"Nebula Beam must ignore Weakness (exactly 210 vs Water-weak Magcargo ex, "
          f"not 420), got {magcargo.damage}")

    # --- 4c. Single-hit only: Nebula Beam owns all of its damage (registered in
    # ATTACK_EFFECT_OWNS_DAMAGE), so the engine must NOT also apply the printed
    # 210 as a separate base hit on top of the effect's 210 (which would double
    # to 420 against a plain, wall-less, non-Weak defender). Re-assert 4a's
    # non-doubling explicitly against a fresh mon. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=starmie_card)
    a.active = starmie
    dwebble = InPlayPokemon(card=db.get("Dwebble"))
    dwebble.card  # sanity: real card object
    fresh_dragapult = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = fresh_dragapult
    st.active_index = 0
    game._resolve_attack(st, nb_i)
    check(fresh_dragapult.damage == 210,
          f"Nebula Beam must own its damage exactly once (210), not double-apply "
          f"the printed base on top of the effect, got {fresh_dragapult.damage}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Staryu (Water Gun) and Mega Starmie ex (Jetting Blow bench-spread, "
          "including Mysterious Rock Inn wall-block + weakness rules, and Nebula "
          "Beam's wall-bypass + weakness-ignore, incl. the critical same-defender "
          "contrast case) all hold.")


if __name__ == "__main__":
    main()
