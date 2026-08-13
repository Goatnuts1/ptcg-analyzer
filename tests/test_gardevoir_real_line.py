#!/usr/bin/env python3
"""
test_gardevoir_real_line.py — the Pokémon-side cards added for Anar Guliyev's real
Mega Gardevoir list (`gardevoir_real`), each asserted against its exact card text:

  Marill (TEF 64 / sv5-64) "Ball Roll"
      [C] 10× — "Flip a coin until you get tails. This attack does 10 damage for
      each heads."
  Azumarill ex (ASC 84) "Bubble Gathering"
      "As often as you like during your turn, you may use this Ability. Move an
      Energy from 1 of your other Pokémon to this Pokémon."
  Azumarill ex (ASC 84) "Energized Balloon"
      [C][C][C] 60+ — "This attack does 40 more damage for each Psychic Energy
      attached to this Pokémon."
  Zacian (PFL 45 / me2-45) "Limit Break"
      [P][C] 50+ — "If your opponent has 3 or fewer Prize cards remaining, this
      attack does 90 more damage."
  Mega Diancie ex (PFL 41 / me2-41) "Diamond Coat"
      "This Pokémon takes 30 less damage from attacks (after applying Weakness and
      Resistance)."
  Lillie's Clefairy ex "Fairy Zone" — VERIFIED, not reimplemented (a prior agent
      already wired it into _apply_weakness_resistance).

Run: python3 tests/test_gardevoir_real_line.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh_state(db, seed=0):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(seed))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None, kind="attack"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=st.rng, effect_kind=kind)


class _Flips:
    """A stand-in rng that makes fx.flip deterministic. fx.flip is
    `bool(ctx.rng.randint(0, 1))` — 1 = heads — so this returns `heads` ones and
    then zeros forever."""

    def __init__(self, heads):
        self.remaining_heads = heads

    def randint(self, lo, hi):
        if self.remaining_heads > 0:
            self.remaining_heads -= 1
            return 1
        return 0

    def shuffle(self, x):
        pass


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # ------------------------------------------------------------------ #
    # 0. PRINTED DATA — the pool entries really are the prints this list plays.
    # ------------------------------------------------------------------ #
    marill = db.get("Marill")
    ball_roll = next((a for a in marill.attacks if a.name == "Ball Roll"), None)
    check(ball_roll is not None, "pool Marill must carry Ball Roll (the TEF 64 print)")
    check(ball_roll.cost == ("Colorless",) and ball_roll.damage == 10
          and ball_roll.damage_suffix == "×",
          f"Ball Roll is [C] for 10×, got {ball_roll.cost} "
          f"{ball_roll.damage}{ball_roll.damage_suffix}")

    azu = db.get("Azumarill ex")
    check(azu.hp == 270 and "Psychic" in azu.types, f"Azumarill ex is 270 HP Psychic, got "
                                                    f"{azu.hp} {azu.types}")
    check(azu.evolves_from == "Marill", "Azumarill ex evolves from Marill")
    check(azu.gives_up_prizes == 2, "Azumarill ex is a (non-MEGA) ex: 2 Prizes")
    bal = next(a for a in azu.attacks if a.name == "Energized Balloon")
    check(bal.cost == ("Colorless", "Colorless", "Colorless") and bal.damage == 60
          and bal.damage_suffix == "+",
          f"Energized Balloon is [C][C][C] 60+, got {bal.cost} "
          f"{bal.damage}{bal.damage_suffix}")
    check(any(ab.name == "Bubble Gathering" for ab in azu.abilities),
          "Azumarill ex must have the Bubble Gathering Ability")

    zac = db.get("Zacian")
    lb = next(a for a in zac.attacks if a.name == "Limit Break")
    check(lb.cost == ("Psychic", "Colorless") and lb.damage == 50
          and lb.damage_suffix == "+",
          f"Limit Break is [P][C] 50+, got {lb.cost} {lb.damage}{lb.damage_suffix}")

    diancie = db.get("Mega Diancie ex")
    check(any(ab.name == "Diamond Coat" for ab in diancie.abilities),
          "the pool's Mega Diancie ex (me2-41) must carry Diamond Coat")
    check(diancie.gives_up_prizes == 3, "Mega Diancie ex is a MEGA ex: 3 Prizes")

    # ------------------------------------------------------------------ #
    # 1. REGISTRATION — right registries, right damage ownership.
    # ------------------------------------------------------------------ #
    for key in (("Marill", "Ball Roll"), ("Azumarill ex", "Energized Balloon"),
                ("Zacian", "Limit Break")):
        check(key in fx.ATTACK_EFFECTS, f"{key} must be registered in ATTACK_EFFECTS")
        # All three are printed "+"/"×", so the engine already applies 0 base and the
        # effect lands the whole hit — no ATTACK_EFFECT_OWNS_DAMAGE entry needed.
        check(key not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
              f"{key} is variable-damage ('+'/'×'); it must NOT also be listed in "
              f"ATTACK_EFFECT_OWNS_DAMAGE")
    check(("Azumarill ex", "Bubble Gathering") in fx.ABILITY_EFFECTS,
          "Bubble Gathering must be registered in ABILITY_EFFECTS")
    check(("Azumarill ex", "Bubble Gathering") in fx.REPEATABLE_ABILITIES,
          "'As often as you like during your turn' -> REPEATABLE_ABILITIES")
    check(("Mega Diancie ex", "Diamond Coat") in fx.PASSIVE_ABILITIES,
          "Diamond Coat is a passive -> PASSIVE_ABILITIES (so the gap-check counts it)")

    # ------------------------------------------------------------------ #
    # 2. BALL ROLL — 10 per heads, all in ONE hit, and 0 on an immediate tails.
    # ------------------------------------------------------------------ #
    st, a, b = fresh_state(db)
    st.rng = _Flips(3)
    mar = InPlayPokemon(card=marill)
    a.active = mar
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))    # Colorless, no Psychic weakness
    fx._ball_roll(ctx_for(st, a, b, source=mar))
    check(b.active.damage == 30, f"3 heads then tails must do 30, got {b.active.damage}")

    st, a, b = fresh_state(db)
    st.rng = _Flips(0)
    mar = InPlayPokemon(card=marill)
    a.active = mar
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    fx._ball_roll(ctx_for(st, a, b, source=mar))
    check(b.active.damage == 0,
          f"NEGATIVE: tails on the first flip must do 0, got {b.active.damage}")

    # Weakness multiplies the TOTAL once (the whole point of letting the effect own the
    # hit): 2 heads = 20, into a Darkness-weak-to-Psychic... use a real ×2 target.
    st, a, b = fresh_state(db)
    st.rng = _Flips(2)
    mar = InPlayPokemon(card=marill)                 # Marill is Psychic
    a.active = mar
    victim_card = db.get("Ralts")                    # Psychic, Weakness Darkness ×2
    b.active = InPlayPokemon(card=victim_card)
    fx._ball_roll(ctx_for(st, a, b, source=mar))
    check(b.active.damage == 20,
          f"2 heads into a non-Psychic-weak target is 20, got {b.active.damage}")

    # ------------------------------------------------------------------ #
    # 3. BUBBLE GATHERING — moves exactly ONE Energy, from one of your OTHER Pokémon.
    # ------------------------------------------------------------------ #
    st, a, b = fresh_state(db)
    azu_mon = InPlayPokemon(card=azu)
    donor = InPlayPokemon(card=db.get("Ralts"))
    a.active = azu_mon
    a.bench = [donor]
    donor.energy = [db.get("Basic Psychic Energy"), db.get("Basic Psychic Energy")]
    fx._bubble_gathering(ctx_for(st, a, b, source=azu_mon, kind="ability"))
    check(len(azu_mon.energy) == 1 and len(donor.energy) == 1,
          f"one use moves exactly 1 Energy, got azumarill={len(azu_mon.energy)} "
          f"donor={len(donor.energy)}")
    fx._bubble_gathering(ctx_for(st, a, b, source=azu_mon, kind="ability"))
    check(len(azu_mon.energy) == 2 and len(donor.energy) == 0,
          "'as often as you like': a second use moves the second Energy too")

    # It never takes from ITSELF ("1 of your OTHER Pokémon"), and the can-use guard
    # goes false with nothing left to move — which is what makes the repeat terminate.
    guard = fx.get_ability_can_use("Azumarill ex", "Bubble Gathering")
    check(guard is not None, "Bubble Gathering must have an ABILITY_CAN_USE guard")
    check(guard(st, a, azu_mon) is False,
          "NEGATIVE: with no Energy on your other Pokémon the Ability must not be offered "
          "(this is what stops the repeatable Ability looping forever)")
    before = len(azu_mon.energy)
    fx._bubble_gathering(ctx_for(st, a, b, source=azu_mon, kind="ability"))
    check(len(azu_mon.energy) == before,
          "NEGATIVE: with no other donor it must be a no-op, never move its own Energy")

    # Prefers a Psychic Energy (what Energized Balloon counts) over a plain one.
    st, a, b = fresh_state(db)
    azu_mon = InPlayPokemon(card=azu)
    d1 = InPlayPokemon(card=db.get("Ralts"))
    a.active = azu_mon
    a.bench = [d1]
    d1.energy = [db.get("Basic Fire Energy"), db.get("Basic Psychic Energy")]
    fx._bubble_gathering(ctx_for(st, a, b, source=azu_mon, kind="ability"))
    check(azu_mon.energy and "Psychic" in azu_mon.energy[0].types,
          f"policy: takes the Psychic Energy first, got "
          f"{[e.name for e in azu_mon.energy]}")

    # ------------------------------------------------------------------ #
    # 4. ENERGIZED BALLOON — 60 + 40 per PSYCHIC Energy attached to the attacker.
    # ------------------------------------------------------------------ #
    for n, expected in ((0, 60), (1, 100), (4, 220)):
        st, a, b = fresh_state(db)
        azu_mon = InPlayPokemon(card=azu)
        azu_mon.energy = [db.get("Basic Psychic Energy")] * n
        a.active = azu_mon
        b.active = InPlayPokemon(card=db.get("Snorlax ex"))
        fx._energized_balloon(ctx_for(st, a, b, source=azu_mon))
        check(b.active.damage == expected,
              f"{n} Psychic Energy -> {expected}, got {b.active.damage}")

    # Telepathic Psychic Energy provides Psychic, so it COUNTS...
    st, a, b = fresh_state(db)
    azu_mon = InPlayPokemon(card=azu)
    azu_mon.energy = [db.get("Telepathic Psychic Energy")]
    a.active = azu_mon
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    fx._energized_balloon(ctx_for(st, a, b, source=azu_mon))
    check(b.active.damage == 100,
          f"Telepathic Psychic Energy is a Psychic Energy: 100, got {b.active.damage}")

    # ...but Prism Energy does NOT: it provides "every type" only on a BASIC holder, and
    # Azumarill ex is a Stage 1, so here it is a plain Colorless provider.
    st, a, b = fresh_state(db)
    azu_mon = InPlayPokemon(card=azu)
    azu_mon.energy = [db.get("Prism Energy")]
    a.active = azu_mon
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    fx._energized_balloon(ctx_for(st, a, b, source=azu_mon))
    check(b.active.damage == 60,
          f"NEGATIVE: Prism Energy on a Stage 1 is not a Psychic Energy: 60, got "
          f"{b.active.damage}")

    # ------------------------------------------------------------------ #
    # 5. LIMIT BREAK — +90 only at 3 or fewer OPPONENT Prizes remaining.
    # ------------------------------------------------------------------ #
    for remaining, expected in ((6, 50), (4, 50), (3, 140), (1, 140)):
        st, a, b = fresh_state(db)
        z = InPlayPokemon(card=zac)
        a.active = z
        b.active = InPlayPokemon(card=db.get("Snorlax ex"))
        b.prizes = [db.get("Basic Psychic Energy")] * remaining
        fx._limit_break(ctx_for(st, a, b, source=z))
        check(b.active.damage == expected,
              f"opponent at {remaining} Prizes -> {expected}, got {b.active.damage}")

    # It reads the OPPONENT's prizes, not our own.
    st, a, b = fresh_state(db)
    z = InPlayPokemon(card=zac)
    a.active = z
    a.prizes = [db.get("Basic Psychic Energy")]          # WE are at 1
    b.prizes = [db.get("Basic Psychic Energy")] * 6      # they are at 6
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    fx._limit_break(ctx_for(st, a, b, source=z))
    check(b.active.damage == 50,
          f"NEGATIVE: our own low prize count must not trigger the bonus, got "
          f"{b.active.damage}")

    # ------------------------------------------------------------------ #
    # 6. DIAMOND COAT — flat −30 attack damage, AFTER Weakness/Resistance.
    # ------------------------------------------------------------------ #
    st, a, b = fresh_state(db)
    dia = InPlayPokemon(card=diancie)
    b.active = dia
    attacker = InPlayPokemon(card=db.get("Snorlax ex"))   # Colorless: no W/R vs Psychic
    a.active = attacker
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=attacker), dia, 100,
                                   owner=b, source=attacker)
    check(dealt == 70 and dia.damage == 70,
          f"Diamond Coat takes 30 off a 100 hit -> 70, got {dealt}/{dia.damage}")

    # AFTER Weakness: Mega Diancie ex is Weakness Metal ×2, so a 100 Metal hit is
    # 200 first, THEN −30 = 170 (not (100−30)×2 = 140).
    st, a, b = fresh_state(db)
    dia = InPlayPokemon(card=diancie)
    b.active = dia
    metal = InPlayPokemon(card=db.get("Mega Excadrill ex"))     # Metal attacker
    a.active = metal
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=metal), dia, 100,
                                   owner=b, source=metal)
    check(dealt == 170,
          f"Diamond Coat subtracts AFTER Weakness: 100 ×2 = 200, −30 = 170, got {dealt}")

    # A 20 hit is reduced to 0, never negative.
    st, a, b = fresh_state(db)
    dia = InPlayPokemon(card=diancie)
    b.active = dia
    attacker = InPlayPokemon(card=db.get("Snorlax ex"))
    a.active = attacker
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=attacker), dia, 20,
                                   owner=b, source=attacker)
    check(dealt == 0 and dia.damage == 0,
          f"a 20 hit is fully absorbed (floored at 0), got {dealt}/{dia.damage}")

    # NEGATIVE 1: damage COUNTERS placed by an effect are not "damage from attacks" —
    # Diamond Coat does not touch place_counters.
    st, a, b = fresh_state(db)
    dia = InPlayPokemon(card=diancie)
    b.active = dia
    src = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active = src
    placed = fx.place_counters(ctx_for(st, a, b, source=src), dia, 5, owner=b)
    check(placed == 5 and dia.damage == 50,
          f"NEGATIVE: Diamond Coat must not reduce placed damage counters, got "
          f"{placed}/{dia.damage}")

    # NEGATIVE 2: it IS an Ability, so Team Rocket's Watchtower... only hits Colorless
    # Pokémon; the live suppressor for a Psychic holder is an opposing Active Flutter
    # Mane's Midnight Fluttering.
    st, a, b = fresh_state(db)
    dia = InPlayPokemon(card=diancie)
    b.active = dia
    flutter = InPlayPokemon(card=db.get("Flutter Mane"))
    a.active = flutter
    check(fx.flat_damage_reduction(st, dia) == 0,
          "NEGATIVE: an opposing Active Flutter Mane's Midnight Fluttering must switch "
          "Diamond Coat off (it is an Ability)")
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=flutter), dia, 100,
                                   owner=b, source=flutter)
    check(dealt == 100, f"suppressed Diamond Coat must let the full 100 through, got "
                        f"{dealt}")

    # NEGATIVE 3: an attack that ignores effects on the opponent's Active bypasses it,
    # same as it bypasses Protect Charge and the wall Abilities.
    st, a, b = fresh_state(db)
    dia = InPlayPokemon(card=diancie)
    b.active = dia
    src = InPlayPokemon(card=db.get("Crustle"))
    a.active = src
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=src), dia, 100, owner=b,
                                   source=src, ignore_active_effects=True)
    check(dealt == 100,
          f"NEGATIVE: 'damage isn't affected by any effects on your opponent's Active' "
          f"must bypass Diamond Coat, got {dealt}")

    # NEGATIVE 4: a Pokémon WITHOUT Diamond Coat gets no reduction.
    st, a, b = fresh_state(db)
    plain = InPlayPokemon(card=db.get("Snorlax ex"))
    b.active = plain
    check(fx.flat_damage_reduction(st, plain) == 0,
          "NEGATIVE: flat_damage_reduction must be 0 for a Pokémon without Diamond Coat")

    # It stacks with Genesect ex's Protect Charge rider (both are −30 after W/R).
    st, a, b = fresh_state(db)
    dia = InPlayPokemon(card=diancie)
    dia.damage_reduction = 30
    b.active = dia
    attacker = InPlayPokemon(card=db.get("Snorlax ex"))
    a.active = attacker
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=attacker), dia, 100,
                                   owner=b, source=attacker)
    check(dealt == 40, f"Diamond Coat + a Protect Charge rider stack to −60, got {dealt}")

    # ------------------------------------------------------------------ #
    # 7. FAIRY ZONE — VERIFY the prior agent's implementation, don't reimplement.
    #    "The Weakness of each of your opponent's Dragon Pokémon in play is now
    #    Psychic. (Apply Weakness as ×2.)"
    # ------------------------------------------------------------------ #
    clef = db.get("Lillie's Clefairy ex")
    check(any(ab.name == "Fairy Zone" for ab in clef.abilities),
          "Lillie's Clefairy ex must carry Fairy Zone")
    check(("Lillie's Clefairy ex", "Fairy Zone") in fx.PASSIVE_ABILITIES,
          "Fairy Zone must already be recorded in PASSIVE_ABILITIES")
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=clef)                 # OUR Clefairy ex
    psychic_attacker = InPlayPokemon(card=db.get("Ralts"))
    a.bench = [psychic_attacker]
    dragon = InPlayPokemon(card=db.get("Dragapult ex"))  # Dragon, no printed Weakness
    b.active = dragon
    check(fx._fairy_zone_active(st, dragon) is True,
          "Fairy Zone must be active on an opponent's Dragon while we have Clefairy ex")
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=psychic_attacker), dragon, 50,
                                   owner=b, source=psychic_attacker)
    check(dealt == 100,
          f"Fairy Zone: a Psychic attack into an opposing Dragon is ×2 -> 100, got {dealt}")
    # NEGATIVE: no Clefairy ex on our side -> no rewrite.
    st, a, b = fresh_state(db)
    psychic_attacker = InPlayPokemon(card=db.get("Ralts"))
    a.active = psychic_attacker
    dragon = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = dragon
    check(fx._fairy_zone_active(st, dragon) is False,
          "NEGATIVE: without our Lillie's Clefairy ex there is no Fairy Zone")
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=psychic_attacker), dragon, 50,
                                   owner=b, source=psychic_attacker)
    check(dealt == 50, f"NEGATIVE: no Fairy Zone -> plain 50, got {dealt}")

    if fails:
        print(f"test_gardevoir_real_line.py: {len(fails)} FAILURE(S)")
        for f in fails:
            print("  -", f)
        return 1
    print("test_gardevoir_real_line.py: all checks passed — Ball Roll, Bubble Gathering, "
          "Energized Balloon, Limit Break and Diamond Coat match their card text; "
          "Fairy Zone verified as already implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
