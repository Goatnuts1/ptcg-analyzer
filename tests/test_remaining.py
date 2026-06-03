#!/usr/bin/env python3
"""
test_remaining.py — the last cluster: accel / triggers / disruption / tail.

Oricorio Excited Turbo, Fan Rotom Fan Call, Meowth ex Last-Ditch Catch (on-bench
trigger), Crushing Hammer, Team Rocket's Watchtower (Colorless-ability suppression),
Moltres Fighting Wings, Dunsparce Dig (shield), Duskull Come and Get You, Unfair
Stamp. Run from project root:  python3 tests/test_remaining.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


class _Heads:
    def randint(self, a, b): return 1
    def shuffle(self, x): pass


class _Tails:
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


def ctx(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    FIRE = db.get("Basic Fire Energy")
    PULT = db.get("Dragapult ex")
    DREEPY = db.get("Dreepy")

    # --- Excited Turbo: attach a Basic Fire from hand to a Benched Fire Pokémon. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Oricorio ex"))
    benched_fire = InPlayPokemon(card=db.get("Charmander"))
    a.bench = [benched_fire]
    a.hand = [FIRE]
    fx._excited_turbo(ctx(st, a, b, source=a.active))
    check(FIRE in benched_fire.energy and FIRE not in a.hand,
          "Excited Turbo should move a Fire Energy from hand to a Benched Fire Pokémon")

    # --- Fan Call: search up to 3 Colorless Pokémon (<=100 HP) to hand. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Fan Rotom"))
    a.deck = [db.get("Dunsparce"), db.get("Fan Rotom"), DREEPY, PULT]  # Dunsparce/Rotom = Colorless; Dreepy/Pult not
    fx._fan_call(ctx(st, a, b, source=a.active))
    got = [c.name for c in a.hand]
    check("Dunsparce" in got and "Fan Rotom" in got and "Dragapult ex" not in got,
          f"Fan Call should fetch Colorless ≤100 HP Pokémon only, got {got}")

    # --- Meowth ex Last-Ditch Catch fires on being benched from hand. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT)
    a.hand = [db.get("Meowth ex")]
    a.deck = [db.get("Boss's Orders"), DREEPY]   # a Supporter to find
    st.active_index = 0
    game.apply_action(st, game.Action("play_basic", hand_index=0))
    check(any(c.name == "Boss's Orders" for c in a.hand),
          "Last-Ditch Catch should search a Supporter when Meowth ex is benched from hand")

    # --- Crushing Hammer (heads): discard an Energy from an opponent's Pokémon. ---
    st, a, b = fresh(db, rng=_Heads())
    b.active = InPlayPokemon(card=PULT, energy=[FIRE, FIRE])
    fx._crushing_hammer(ctx(st, a, b))
    check(len(b.active.energy) == 1 and len(b.discard) == 1,
          f"Crushing Hammer heads should discard 1 Energy (left={len(b.active.energy)})")

    # --- Team Rocket's Watchtower: Colorless Pokémon have no Abilities. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=PULT)
    dudun = InPlayPokemon(card=db.get("Dudunsparce"))   # Colorless, has Run Away Draw
    a.bench = [dudun]                                   # used from the Bench
    a.deck = [DREEPY] * 5
    st.active_index = 0
    check(any(x.kind == "use_ability" for x in game.legal_actions(st)),
          "Dudunsparce ability should be available with no Stadium")
    st.stadium = db.get("Team Rocket's Watchtower"); st.stadium_owner = 0
    check(not any(x.kind == "use_ability" for x in game.legal_actions(st)),
          "TRW should suppress the Colorless Dudunsparce's ability")

    # --- Moltres Fighting Wings: 20, +90 vs an ex Active. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Moltres"))
    b.active = InPlayPokemon(card=PULT)            # an ex
    fx._fighting_wings(ctx(st, a, b, source=a.active))
    check(b.active.damage == 110, f"Fighting Wings should do 110 vs an ex (got {b.active.damage})")
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Moltres"))
    b.active = InPlayPokemon(card=DREEPY)          # not an ex
    fx._fighting_wings(ctx(st, a, b, source=a.active))
    check(b.active.damage == 20, f"Fighting Wings should do 20 vs a non-ex (got {b.active.damage})")

    # --- Dunsparce Dig (heads): shield -> immune to attack damage next turn. ---
    st, a, b = fresh(db, rng=_Heads())
    dun = InPlayPokemon(card=db.get("Dunsparce"))
    a.active = dun
    fx._dig(ctx(st, a, b, source=dun))
    check(dun.shielded, "Dig heads should shield this Pokémon")
    # a shielded Pokémon takes no attack damage
    blocked = fx.apply_attack_damage(ctx(st, b, a), dun, 100, owner=a)
    check(blocked == 0 and dun.damage == 0, "a shielded Pokémon should take no attack damage")

    # --- Duskull Come and Get You: up to 3 Duskull from discard to bench. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Duskull"))
    a.discard = [db.get("Duskull")] * 4 + [DREEPY]
    fx._come_and_get_you(ctx(st, a, b, source=a.active))
    check(sum(1 for m in a.bench if m.card.name == "Duskull") == 3,
          "Come and Get You should bench exactly 3 Duskull (the max)")

    # --- Assault Landing: 70 only if a Stadium is in play, else nothing. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=db.get("Fan Rotom"))
    b.active = InPlayPokemon(card=PULT)
    fx._assault_landing(ctx(st, a, b, source=a.active))
    check(b.active.damage == 0, "Assault Landing should do nothing with no Stadium")
    st.stadium = db.get("Battle Cage")
    fx._assault_landing(ctx(st, a, b, source=a.active))
    check(b.active.damage == 70, f"Assault Landing should do 70 with a Stadium (got {b.active.damage})")

    # --- Tuck Tail: put Meowth ex (and attached) back into hand; promote the bench. ---
    st, a, b = fresh(db)
    meowth = InPlayPokemon(card=db.get("Meowth ex"), energy=[FIRE])
    a.active = meowth
    a.bench = [InPlayPokemon(card=DREEPY)]
    fx._tuck_tail(ctx(st, a, b, source=meowth))
    check(any(c.name == "Meowth ex" for c in a.hand) and FIRE in a.hand,
          "Tuck Tail should return Meowth ex and its Energy to hand")
    check(a.active is not None and a.active.card.name == "Dreepy", "should promote the bench after Tuck Tail")

    # --- Unfair Stamp: both shuffle hand into deck; you draw 5, opp draws 2. ---
    st, a, b = fresh(db)
    a.hand = [FIRE, FIRE]; a.deck = [DREEPY] * 10
    b.hand = [FIRE]; b.deck = [DREEPY] * 10
    fx._unfair_stamp(ctx(st, a, b))
    check(len(a.hand) == 5 and len(b.hand) == 2, f"Unfair Stamp: you 5 / opp 2 (a={len(a.hand)}, b={len(b.hand)})")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — remaining cluster: Excited Turbo, Fan Call, Last-Ditch Catch, Crushing Hammer, "
          "TRW suppression, Fighting Wings, Dig, Come and Get You, Unfair Stamp all match card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
