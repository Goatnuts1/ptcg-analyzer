#!/usr/bin/env python3
"""
test_trading_places_print_names.py — Dunsparce (JTG 120) and the print-suffix
evolution rule it forced.

CARD: Dunsparce (JTG 120), 70 HP Colorless Basic.
  [C] Trading Places — "Switch this Pokémon with 1 of your Benched Pokémon." (no damage)
  [C][C] Ram — 20.
The pool already had a DIFFERENT "Dunsparce" (TEF, 60 HP, Gnaw / Dig) which
charizard_xy and alakazam_deck both play, so the TEF print keeps the bare name and the
new one is added as "Dunsparce (JTG)" — the Metagross (CRI) precedent.

THE RULE THAT NEEDED FIXING: a "(SETCODE)" suffix is pool bookkeeping, not part of the
card, so evolution must match a card's PRINTED name. Before this, a suffixed
PRE-evolution silently broke its own line — Dudunsparce's printed `evolvesFrom` is
"Dunsparce", which would never match "Dunsparce (JTG)", leaving the deck's 2
Dudunsparce dead in hand. effects.print_base_name strips the suffix and
game.evolves_onto uses it (as does Rare Candy's basic-name match).

Run: python3 tests/test_trading_places_print_names.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import effects as fx
from src.engine.game import legal_actions, apply_action, evolves_onto


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.turns_taken = 3
    b.turns_taken = 3
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # ----------------------------------------------------------------- #
    # 0. Both prints exist, and the OLD one is untouched.
    # ----------------------------------------------------------------- #
    jtg = db.get("Dunsparce (JTG)")
    tef = db.get("Dunsparce")
    check(jtg.hp == 70 and [a.name for a in jtg.attacks] == ["Trading Places", "Ram"],
          f"Dunsparce (JTG) should be 70 HP with Trading Places + Ram, got {jtg.hp}/"
          f"{[a.name for a in jtg.attacks]}")
    check(jtg.attacks[0].damage == 0 and jtg.attacks[1].damage == 20,
          "Trading Places does no damage; Ram does 20")
    check(tef.hp == 60 and [a.name for a in tef.attacks] == ["Gnaw", "Dig"],
          f"the pool's bare 'Dunsparce' must still be the TEF print (60 HP, Gnaw/Dig) "
          f"that charizard_xy and alakazam_deck play, got {tef.hp}/"
          f"{[a.name for a in tef.attacks]}")
    check(fx.get_attack_effect("Dunsparce", "Dig") is not None
          and fx.get_attack_effect("Dunsparce (JTG)", "Dig") is None,
          "Dig must stay bound to the TEF print only")
    check(fx.get_attack_effect("Dunsparce (JTG)", "Trading Places") is not None
          and fx.get_attack_effect("Dunsparce", "Trading Places") is None,
          "Trading Places must be bound to the JTG print only")

    # ----------------------------------------------------------------- #
    # 1. print_base_name — strips a set-code suffix, and NOTHING else.
    # ----------------------------------------------------------------- #
    check(fx.print_base_name("Dunsparce (JTG)") == "Dunsparce", "suffix must be stripped")
    check(fx.print_base_name("Metagross (CRI)") == "Metagross", "suffix must be stripped")
    check(fx.print_base_name("Dunsparce") == "Dunsparce", "a bare name is unchanged")
    for name in ("Lillie's Clefairy ex", "Bloodmoon Ursaluna ex", "Cornerstone Mask Ogerpon ex",
                 "Pokégear 3.0", "Mega Charizard X ex"):
        check(fx.print_base_name(name) == name,
              f"{name!r} has no print suffix and must be left alone, got "
              f"{fx.print_base_name(name)!r}")

    # ----------------------------------------------------------------- #
    # 2. EVOLUTION across the suffix — the whole reason print_base_name exists.
    # ----------------------------------------------------------------- #
    dudun = db.get("Dudunsparce")
    check(dudun.evolves_from == "Dunsparce",
          "sanity: Dudunsparce's printed evolvesFrom is the bare 'Dunsparce'")
    check(evolves_onto(jtg, dudun) is True,
          "Dudunsparce must be able to evolve from the JTG Dunsparce print")
    check(evolves_onto(tef, dudun) is True,
          "and from the TEF print — any print of Dunsparce becomes any Dudunsparce")
    check(evolves_onto(db.get("Shuppet (PBL)"), dudun) is False,
          "a Shuppet is not a Dunsparce — the match must not have gone fuzzy")
    check(evolves_onto(db.get("Shuppet (PBL)"), db.get("Banette (PBL)")) is True,
          "Banette (PBL) evolves from Shuppet (PBL)")
    check(evolves_onto(db.get("Poltchageist (PBL)"), db.get("Sinistcha (PBL)")) is True,
          "Sinistcha (PBL) evolves from Poltchageist (PBL)")

    # end-to-end through legal_actions: the evolve really is offered and applies.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dunsparce (JTG)"))
    a.hand = [db.get("Dudunsparce")]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    evolves = [x for x in legal_actions(st) if x.kind == "evolve"]
    check(len(evolves) == 1, f"the engine must offer the evolve, got {len(evolves)}")
    apply_action(st, evolves[0])
    check(a.active.card.name == "Dudunsparce",
          f"Dunsparce (JTG) must actually become Dudunsparce, got {a.active.card.name}")

    # ----------------------------------------------------------------- #
    # 3. TRADING PLACES — "Switch this Pokémon with 1 of your Benched Pokémon."
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Dunsparce (JTG)"))
    healthy = InPlayPokemon(card=db.get("Dhelmise (PBL)"))     # 140 HP, undamaged
    hurt = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    hurt.damage = 100
    a.active, a.bench = src, [hurt, healthy]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    fx._trading_places(fx.EffectContext(state=st, me=a, opp=b, source=src, db=db,
                                        rng=st.rng))
    check(a.active is healthy,
          f"Trading Places must promote a Benched Pokémon (v0 policy: the healthiest), "
          f"got {a.active.card.name} dmg={a.active.damage}")
    check(any(m is src for m in a.bench) and len(a.bench) == 2,
          "the attacker must end up on the Bench, bench size unchanged")

    # 3a. Special Conditions clear off the Active Spot, as with retreat / Switch.
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Dunsparce (JTG)"))
    src.confused = True
    a.active, a.bench = src, [InPlayPokemon(card=db.get("Dhelmise (PBL)"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    fx._trading_places(fx.EffectContext(state=st, me=a, opp=b, source=src, db=db,
                                        rng=st.rng))
    check(src.confused is False,
          "leaving the Active Spot clears Special Conditions")

    # 3b. NEGATIVE: with an empty Bench it is a legal but empty attack — nothing moves,
    #     and nothing blows up.
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Dunsparce (JTG)"))
    a.active = src
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    fx._trading_places(fx.EffectContext(state=st, me=a, opp=b, source=src, db=db,
                                        rng=st.rng))
    check(a.active is src and a.bench == [],
          "with no Bench there is nothing to switch with — the board is unchanged")

    # 3c. NEGATIVE: Trading Places deals no damage at all.
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Dunsparce (JTG)"))
    a.active, a.bench = src, [InPlayPokemon(card=db.get("Dhelmise (PBL)"))]
    d = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = d
    fx._trading_places(fx.EffectContext(state=st, me=a, opp=b, source=src, db=db,
                                        rng=st.rng))
    check(d.damage == 0, f"Trading Places has no damage number, got {d.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_trading_places_print_names.py: all checks passed — the JTG print carries "
          "Trading Places, the TEF print keeps Dig, and a print-suffixed pre-evolution "
          "still evolves normally")


if __name__ == "__main__":
    main()
