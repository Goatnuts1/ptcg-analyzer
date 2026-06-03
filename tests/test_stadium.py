#!/usr/bin/env python3
"""
test_stadium.py — Stadium zone + the two bench damage chokepoints (MILESTONE §2.5).

Asserts the confirmed, deliberately-separate rulings:
  - Battle Cage prevents EFFECT-placed counters on a Benched Pokémon from the
    OPPONENT (place_counters), but not on your own bench.
  - Tera prevents ATTACK DAMAGE to a Benched Pokémon (apply_attack_damage), but
    not while Active.
  - The two are orthogonal: Tera does NOT stop Phantom Dive's spread; Battle Cage
    does.

Run from project root:  python3 tests/test_stadium.py
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
    st.db = db
    st.turn_number = 5
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

    # ----------------------------------------------------------------- #
    # 1. Stadium framework: play sets the zone; same-name can't replace;
    #    a different Stadium replaces and discards the old one to its owner.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.hand = [db.get("Battle Cage"), db.get("Battle Cage")]
    st.active_index = 0

    acts = game.legal_actions(st)
    stadium_acts = [x for x in acts if x.kind == "play_stadium"]
    check(len(stadium_acts) >= 1, "Battle Cage should be offered as a play_stadium action")

    game.apply_action(st, stadium_acts[0])
    check(st.stadium is not None and st.stadium.name == "Battle Cage",
          f"stadium zone should hold Battle Cage, got {st.stadium}")
    check(st.stadium_owner == 0, f"stadium owner should be 0, got {st.stadium_owner}")
    check(a.stadium_played_this_turn, "stadium_played_this_turn should be set")

    # second (same-name) Battle Cage must NOT be offered (same-turn + same-name).
    acts2 = game.legal_actions(st)
    check(not any(x.kind == "play_stadium" for x in acts2),
          "a second/same-name Stadium must not be playable")

    # opponent plays a DIFFERENT stadium next turn -> old Battle Cage to A's discard.
    b.hand = [db.get("Team Rocket's Watchtower")]
    st.active_index = 1
    b.stadium_played_this_turn = False
    sa = [x for x in game.legal_actions(st) if x.kind == "play_stadium"]
    check(len(sa) == 1, "a differently-named Stadium should be playable over Battle Cage")
    game.apply_action(st, sa[0])
    check(st.stadium.name == "Team Rocket's Watchtower" and st.stadium_owner == 1,
          "new stadium should replace the old and record the new owner")
    check(db.get("Battle Cage") in a.discard,
          "the replaced Battle Cage should go to its owner's (A's) discard")

    # ----------------------------------------------------------------- #
    # 2. place_counters + Battle Cage (effect counters on the bench).
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    victim = InPlayPokemon(card=db.get("Flutter Mane"))   # 90 HP, not Tera
    b.bench = [victim]
    ctx = ctx_for(st, me=a, opp=b, source=a.active)

    # no stadium -> counters land
    placed = fx.place_counters(ctx, victim, 3, owner=b)
    check(placed == 3 and victim.damage == 30,
          f"no stadium: 3 counters should land (dmg={victim.damage})")

    # Battle Cage up -> opponent's effect counters on B's bench are prevented
    st.stadium = db.get("Battle Cage")
    st.stadium_owner = 0
    placed2 = fx.place_counters(ctx, victim, 3, owner=b)
    check(placed2 == 0 and victim.damage == 30,
          f"Battle Cage: counters on opp bench should be prevented (dmg={victim.damage})")

    # but MY OWN benched Pokémon still take my own counters under Battle Cage
    own = InPlayPokemon(card=db.get("Flutter Mane"))
    a.bench = [own]
    placed3 = fx.place_counters(ctx, own, 2, owner=a)
    check(placed3 == 2 and own.damage == 20,
          f"Battle Cage should not block counters on your OWN bench (dmg={own.damage})")

    # ----------------------------------------------------------------- #
    # 3. End-to-end: Phantom Dive's spread is prevented by Battle Cage,
    #    while its 200 to the Active still lands (damage from attacks).
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active.energy = [db.get("Basic Fire Energy"), db.get("Basic Psychic Energy")]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))   # 320 HP survivor
    bench_low = InPlayPokemon(card=db.get("Dreepy"))        # 70 HP
    bench_low.damage = 60                                   # 1 counter from KO
    b.bench = [bench_low]
    st.stadium = db.get("Battle Cage")
    st.stadium_owner = 1
    st.active_index = 0
    pd = next(i for i, atk in enumerate(a.active.card.attacks) if atk.name == "Phantom Dive")
    game._resolve_attack(st, pd)
    check(b.active is not None and b.active.damage == 200,
          f"Phantom Dive active hit should still land 200 (got {b.active.damage if b.active else 'KO'})")
    check(db.get("Dreepy") not in b.discard and bench_low.damage == 60,
          "Battle Cage should prevent Phantom Dive's bench spread (Dreepy survives)")

    # ----------------------------------------------------------------- #
    # 4. apply_attack_damage + Tera (Dragapult ex has the 'Tera' subtype).
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))   # attacker / source
    # Tera Pokémon on B's BENCH -> attack damage prevented
    tera_bench = InPlayPokemon(card=db.get("Dragapult ex"))
    non_tera_bench = InPlayPokemon(card=db.get("Flutter Mane"))
    b.bench = [tera_bench, non_tera_bench]
    ctx = ctx_for(st, me=a, opp=b, source=a.active)

    dealt_tera = fx.apply_attack_damage(ctx, tera_bench, 100, owner=b)
    check(dealt_tera == 0 and tera_bench.damage == 0,
          f"Tera on bench should prevent attack damage (dmg={tera_bench.damage})")
    dealt_plain = fx.apply_attack_damage(ctx, non_tera_bench, 100, owner=b)
    check(dealt_plain == 100 and non_tera_bench.damage == 100,
          f"non-Tera bench should take the 100 (dmg={non_tera_bench.damage})")

    # Tera does NOT protect while ACTIVE
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    dealt_active = fx.apply_attack_damage(ctx, b.active, 100, owner=b)
    check(dealt_active == 100 and b.active.damage == 100,
          f"Tera should NOT protect the Active (dmg={b.active.damage})")

    # ----------------------------------------------------------------- #
    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Stadium zone + Battle Cage (counters) + Tera (attack damage) hold; "
          "chokepoints stay orthogonal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
