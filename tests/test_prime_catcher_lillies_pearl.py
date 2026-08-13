#!/usr/bin/env python3
"""
test_prime_catcher_lillies_pearl.py — assert Prime Catcher and Lillie's Pearl
(the two Trainer gaps in the Clefairy / Mega Kangaskhan ex "Slop Box" deck,
James Kowalski's NAIC 2026-winning list) do EXACTLY what the cards say.

Card text (verified via Bulbapedia this session, quoted at each assertion site):

  Prime Catcher (TEF 157, Item, ACE SPEC):
    "Switch in 1 of your opponent's Benched Pokémon to the Active Spot. If you
    do, switch your Active Pokémon with 1 of your Benched Pokémon."

  Lillie's Pearl (JTG 151, Pokémon Tool):
    "If the Lillie's Pokémon this card is attached to is Knocked Out by damage
    from an attack from your opponent's Pokémon, that player takes 1 fewer
    Prize card." (No once-per-game clause, unlike Legacy Energy.)

Run from project root:  python3 tests/test_prime_catcher_lillies_pearl.py
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

    # =================================================================== #
    # PRIME CATCHER
    # =================================================================== #

    # --- 1a. Gusts the opponent's benched mon up AND switches our own Active
    # with our healthiest Bench mon, in one play. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    strong = InPlayPokemon(card=db.get("Dreepy")); strong.damage = 0
    weak = InPlayPokemon(card=db.get("Dreepy")); weak.damage = 20
    a.bench = [weak, strong]
    a.hand = [db.get("Prime Catcher")]
    bopp = InPlayPokemon(card=db.get("Dreepy"))
    b.active = InPlayPokemon(card=db.get("Kadabra"))
    b.bench = [bopp]
    st.active_index = 0
    outgoing = a.active
    game.apply_action(st, game.Action("play_trainer", hand_index=0))
    check(b.active is bopp, "Prime Catcher should gust the opponent's benched mon up")
    check(a.active is strong,
          f"Prime Catcher should bring in own healthiest bench mon, got "
          f"{a.active.card.name if a.active else None}")
    check(outgoing in a.bench, "outgoing Active should now be benched")
    check(len(a.bench) == 2, f"bench should hold outgoing + weak Dreepy, got {len(a.bench)}")

    # --- 1b. Unplayable with no opponent Bench (nothing to gust). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.hand = [db.get("Prime Catcher")]
    b.active = InPlayPokemon(card=db.get("Kadabra"))
    b.bench = []
    check(fx.can_play_prime_catcher(st, a) is False,
          "Prime Catcher should be unplayable with no opponent bench")

    # --- 1c. Own switch is a no-op (not a crash) when we have no Bench —
    # the gust still happens even though the "if you do" half can't fire. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.hand = [db.get("Prime Catcher")]
    bopp2 = InPlayPokemon(card=db.get("Dreepy"))
    b.active = InPlayPokemon(card=db.get("Kadabra"))
    b.bench = [bopp2]
    st.active_index = 0
    orig_active = a.active
    game.apply_action(st, game.Action("play_trainer", hand_index=0))
    check(b.active is bopp2, "gust half should still fire with no own Bench")
    check(a.active is orig_active, "own switch should no-op with an empty Bench")

    # =================================================================== #
    # LILLIE'S PEARL
    # =================================================================== #

    # --- 2a. POSITIVE: a Lillie's-named Pokémon KO'd by an opponent's attack
    # with Lillie's Pearl attached gives up 1 fewer Prize (2 -> 1 for an ex). ---
    st, a, b = fresh_state(db)
    clefairy = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    clefairy.tool = db.get("Lillie's Pearl")
    clefairy.damage = 1000
    a.active = clefairy
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    clefairy.koed_by_opponent_attack_damage = True
    prizes_before = len(b.prizes)
    fx.process_knockouts(st)
    check(len(b.prizes) == prizes_before - 1,
          f"Lillie's Pearl should reduce a 2-prize ex KO to 1, "
          f"prizes={len(b.prizes)} before={prizes_before}")
    check(any(c.name == "Lillie's Pearl" for c in a.discard),
          "Lillie's Pearl should discard along with its KO'd holder")

    # --- 2b. NEGATIVE: name-gated to "Lillie's" Pokémon — a non-Lillie's
    # holder gets no reduction even with the Tool attached. ---
    st, a, b = fresh_state(db)
    mon = InPlayPokemon(card=db.get("Dreepy"))
    mon.tool = db.get("Lillie's Pearl")
    mon.damage = 1000
    a.active = mon
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    mon.koed_by_opponent_attack_damage = True
    prizes_before = len(b.prizes)
    fx.process_knockouts(st)
    check(len(b.prizes) == prizes_before - 1,
          f"non-Lillie's holder must NOT get the reduction, "
          f"prizes={len(b.prizes)} before={prizes_before}")

    # --- 2c. NEGATIVE: scoped to "Knocked Out by damage from an attack from
    # your opponent's Pokémon" — no reduction if the KO wasn't attack damage
    # from the opponent (e.g. a self-KO / counter-damage source). ---
    st, a, b = fresh_state(db)
    clefairy2 = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    clefairy2.tool = db.get("Lillie's Pearl")
    clefairy2.damage = 1000
    a.active = clefairy2
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    clefairy2.koed_by_opponent_attack_damage = False
    prizes_before = len(b.prizes)
    fx.process_knockouts(st)
    check(len(b.prizes) == prizes_before - 2,
          f"no reduction when not KO'd by opponent attack damage, "
          f"prizes={len(b.prizes)} before={prizes_before}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Prime Catcher (gust + self-switch, empty-bench/empty-opp-bench "
          "edge cases) and Lillie's Pearl (prize reduction, name-gate, "
          "attack-source-gate) all hold.")


if __name__ == "__main__":
    main()
