#!/usr/bin/env python3
"""
test_rocky_fighting_energy.py — Rocky Fighting Energy (Perfect Order 087/088, mark J,
Special Energy), verified on Bulbapedia:

  "As long as this card is attached to a Pokémon, it provides Fighting Energy.
   Prevent all effects of attacks used by your opponent's Pokémon done to the Fighting
   Pokémon this card is attached to. (Existing effects are not removed. Damage is not an
   effect.)"

Two halves, two mechanisms:
  1. "provides Fighting Energy" — the pool entry's types=["Fighting"], read by
     InPlayPokemon.provided_types()/can_pay_cost, exactly like Telepathic Psychic Energy.
  2. the prevention — rocky_fighting_prevents_effect, consulted at the two attack-EFFECT
     chokepoints (place_counters, effect_prevented_on) and DELIBERATELY not at
     apply_attack_damage, because "Damage is not an effect".

The negatives are the whole point: damage still lands in full, an ABILITY's effect is not
prevented (the card says attacks), a non-Fighting holder is not protected, and your own
effects on your own Pokémon are unaffected ("your opponent's Pokémon").

Run: python3 tests/test_rocky_fighting_energy.py
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
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.active_index = 1        # B (the attacker below) is the acting player
    return st, a, b


def ctx_for(st, me, opp, source=None, kind="attack"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng,
                            effect_kind=kind)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    rocky = db.get("Rocky Fighting Energy")

    # ===================================================================== #
    # 0. The card itself: a Special Energy providing Fighting, recorded as implemented.
    # ===================================================================== #
    check(rocky.is_energy and not rocky.is_basic_energy,
          "Rocky Fighting Energy must be a Special (non-Basic) Energy card")
    check("Special" in rocky.subtypes, f"subtypes must include 'Special', got {rocky.subtypes}")
    check(rocky.types == ("Fighting",),
          f"it must provide Fighting Energy via types, got {rocky.types}")
    check(rocky.regulation_mark == "J", f"regulation mark J, got {rocky.regulation_mark!r}")
    check("Rocky Fighting Energy" in fx.SPECIAL_ENERGY_IMPLEMENTED,
          "it must be recorded in SPECIAL_ENERGY_IMPLEMENTED (passive handler)")
    check(fx.get_special_energy_on_attach("Rocky Fighting Energy") is None,
          "it has no on-attach trigger — its behavior is purely passive")

    # --- 1. "provides Fighting Energy": it alone pays a [F] cost. ---
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    gible.energy = [rocky]
    check(gible.provided_types() == ["Fighting"],
          f"provided_types must be ['Fighting'], got {gible.provided_types()}")
    rock_hurl = db.get("Cynthia's Gible").attacks[0]
    check(rock_hurl.name == "Rock Hurl" and rock_hurl.cost == ("Fighting",),
          "sanity: Rock Hurl costs a single [F]")
    check(can_pay_cost(gible, rock_hurl.cost) is True,
          "a lone Rocky Fighting Energy must pay Rock Hurl's [F] cost")
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    chomp.energy = [rocky, db.get("Basic Fighting Energy")]
    buster = db.get("Cynthia's Garchomp ex").attacks[1]
    check(buster.name == "Draconic Buster" and buster.cost == ("Fighting", "Fighting"),
          "sanity: Draconic Buster costs [F][F]")
    check(can_pay_cost(chomp, buster.cost) is True,
          "Rocky + a Basic Fighting must pay [F][F]")

    # ===================================================================== #
    # 2. PREVENTION: an opponent's ATTACK effect placing damage counters on the holder
    #    is prevented outright.
    # ===================================================================== #
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Cynthia's Gible"))
    holder.energy = [rocky]
    a.active = holder
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    placed = fx.place_counters(ctx_for(st, b, a, source=attacker), holder, 4, owner=a)
    check(placed == 0, f"an opposing attack's counters must be fully prevented, got {placed}")
    check(holder.damage == 0, f"no damage may land from that effect, got {holder.damage}")

    # 2a. Benched holder is protected too (the card says nothing about the Active Spot).
    st, a, b = fresh_state(db)
    benched = InPlayPokemon(card=db.get("Cynthia's Gible"))
    benched.energy = [rocky]
    a.active = InPlayPokemon(card=db.get("Cynthia's Roselia"))
    a.bench = [benched]
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    check(fx.place_counters(ctx_for(st, b, a, source=attacker), benched, 4, owner=a) == 0,
          "a Benched holder must be protected as well")

    # --- 3. NEGATIVE, the headline clause: "Damage is not an effect." Attack DAMAGE lands
    # in full on the protected Pokémon. ---
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Cynthia's Gible"))
    holder.energy = [rocky]
    a.active = holder
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=attacker), holder, 60,
                                   owner=a, source=attacker)
    check(dealt == 60, f"attack damage must NOT be prevented, got {dealt}")
    check(holder.damage == 60, f"the holder must really take 60, got {holder.damage}")

    # --- 4. NEGATIVE: "effects of ATTACKS" — an opposing ABILITY's counters still land.
    # (This is why place_counters is gated on ctx.effect_kind.) ---
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Cynthia's Gible"))
    holder.energy = [rocky]
    a.active = holder
    ability_user = InPlayPokemon(card=db.get("Dusknoir"))     # Cursed Blast is an Ability
    b.active = ability_user
    placed = fx.place_counters(ctx_for(st, b, a, source=ability_user, kind="ability"),
                              holder, 4, owner=a)
    check(placed == 4, f"an opposing ABILITY's counters must still land, got {placed}")
    check(holder.damage == 40, f"the holder must take 40 from the Ability, got {holder.damage}")

    # --- 5. NEGATIVE: only the "[F] Pokémon this card is attached to" is protected. Rocky
    # on a GRASS Pokémon (Cynthia's Roselia) provides Fighting but protects nothing. ---
    st, a, b = fresh_state(db)
    grass_holder = InPlayPokemon(card=db.get("Cynthia's Roselia"))
    grass_holder.energy = [rocky]
    a.active = grass_holder
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    check(fx.place_counters(ctx_for(st, b, a, source=attacker), grass_holder, 4, owner=a) == 4,
          "a non-Fighting holder must NOT be protected")

    # --- 6. NEGATIVE: no Rocky attached -> no protection (control for §2). ---
    st, a, b = fresh_state(db)
    bare = InPlayPokemon(card=db.get("Cynthia's Gible"))
    bare.energy = [db.get("Basic Fighting Energy")]
    a.active = bare
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    check(fx.place_counters(ctx_for(st, b, a, source=attacker), bare, 4, owner=a) == 4,
          "control: without Rocky Fighting Energy the counters land")

    # --- 7. NEGATIVE: "your opponent's Pokémon" — OUR OWN effects on our own protected
    # Pokémon are not prevented (e.g. a self-damage attack). ---
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Cynthia's Gible"))
    holder.energy = [rocky]
    a.active = holder
    own_source = InPlayPokemon(card=db.get("Cynthia's Roselia"))
    a.bench = [own_source]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    check(fx.place_counters(ctx_for(st, a, b, source=own_source), holder, 2, owner=a) == 2,
          "our own effects on our own Pokémon must not be prevented")

    # --- 8. The other chokepoint (effect_prevented_on): defender-side attack riders.
    # 8a. Confusion from Munkidori's Mind Bend is blocked. ---
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Cynthia's Gible"))
    holder.energy = [rocky]
    a.active = holder
    munk = InPlayPokemon(card=db.get("Munkidori"))
    b.active = munk
    fx._mind_bend(ctx_for(st, b, a, source=munk))
    check(holder.confused is False,
          "Mind Bend's Confusion is an effect of an attack — it must be prevented")
    # 8a'. control: an unprotected defender IS Confused.
    st, a, b = fresh_state(db)
    plain = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.active = plain
    munk = InPlayPokemon(card=db.get("Munkidori"))
    b.active = munk
    fx._mind_bend(ctx_for(st, b, a, source=munk))
    check(plain.confused is True, "control: without Rocky the Confusion lands")

    # 8b. Metagross (CRI)'s M Bounce Back forced switch-out is blocked.
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Cynthia's Gible"))
    holder.energy = [rocky]
    a.active = holder
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roselia"))]
    gross = InPlayPokemon(card=db.get("Metagross (CRI)"))
    b.active = gross
    fx._bounce_back(ctx_for(st, b, a, source=gross))
    check(a.active is holder,
          "M Bounce Back's forced switch is an effect of an attack — it must be prevented")
    # 8b'. control: an unprotected Active really is bounced.
    st, a, b = fresh_state(db)
    plain = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.active = plain
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roselia"))]
    gross = InPlayPokemon(card=db.get("Metagross (CRI)"))
    b.active = gross
    fx._bounce_back(ctx_for(st, b, a, source=gross))
    check(a.active is not plain, "control: without Rocky the switch-out happens")

    # --- 9. It is an ENERGY, not an Ability: Team Rocket's Watchtower ("Colorless Pokémon
    # in play have no Abilities") cannot switch the prevention off. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Team Rocket's Watchtower")
    st.stadium_owner = 1
    holder = InPlayPokemon(card=db.get("Cynthia's Gible"))
    holder.energy = [rocky]
    a.active = holder
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    check(fx.place_counters(ctx_for(st, b, a, source=attacker), holder, 4, owner=a) == 0,
          "an Energy's effect can't be suppressed by an ability-suppression Stadium")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_rocky_fighting_energy.py: all checks passed — provides [F], prevents an "
          "opponent's ATTACK effects on its Fighting holder, and does NOT prevent damage, "
          "ability effects, or effects on a non-Fighting holder")


if __name__ == "__main__":
    main()
