#!/usr/bin/env python3
"""
test_metallic_signal.py — Genesect ex (Black Bolt 67) Ability Metallic Signal:
"Once during your turn, you may search your deck for up to 2 Evolution Metal Pokémon,
reveal them, and put them into your hand. Then, shuffle your deck."

The load-bearing clause is "Evolution Metal Pokémon": BOTH conditions, so a Basic
Metal Pokémon (Beldum) and a non-Metal Evolution Pokémon (Frogadier) are both
negative cases. "Up to 2" = at most 2, even with more available.

Run: python3 tests/test_metallic_signal.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    gen_card = db.get("Genesect ex")

    # --- 0. card data + registry wiring. ---
    check(gen_card.id == "zsv10pt5-67",
          f"expected the Black Bolt Genesect ex (zsv10pt5-67), pool has {gen_card.id}")
    ab = next(a for a in gen_card.abilities if a.name == "Metallic Signal")
    check("up to 2 Evolution Metal Pokémon" in ab.text, f"unexpected ability text: {ab.text!r}")
    check(("Genesect ex", "Metallic Signal") in fx.ABILITY_EFFECTS,
          "Metallic Signal must be registered")
    check(not fx.is_repeatable_ability("Genesect ex", "Metallic Signal"),
          "Metallic Signal is once per turn")

    # --- 0b. the predicate itself: Evolution AND Metal. ---
    check(fx.p_evolution_metal_pokemon(db.get("Metang")) is True, "Metang (Stage 1 Metal) qualifies")
    check(fx.p_evolution_metal_pokemon(db.get("Metagross")) is True, "Metagross (Stage 2 Metal) qualifies")
    check(fx.p_evolution_metal_pokemon(db.get("Mega Excadrill ex")) is True,
          "Mega Excadrill ex (Stage 1 Metal) qualifies")
    check(fx.p_evolution_metal_pokemon(db.get("Beldum")) is False,
          "NEGATIVE: Beldum is Metal but BASIC — not an Evolution Pokémon")
    check(fx.p_evolution_metal_pokemon(db.get("Frogadier")) is False,
          "NEGATIVE: Frogadier is an Evolution Pokémon but not Metal")
    check(fx.p_evolution_metal_pokemon(db.get("Basic Metal Energy")) is False,
          "NEGATIVE: an Energy card is not a Pokémon")

    # --- 1. up to 2 come to hand; non-qualifying cards stay in the deck. ---
    st, a, b = fresh_state(db)
    gen = InPlayPokemon(card=gen_card)
    a.active = gen
    a.deck = [db.get("Metang"), db.get("Metagross"), db.get("Mega Excadrill ex"),
              db.get("Beldum"), db.get("Frogadier"), db.get("Basic Metal Energy")]
    fx._metallic_signal(ctx_for(st, a, b, source=gen))
    check(len(a.hand) == 2, f"'up to 2' must take exactly 2 when 3 qualify, got {len(a.hand)}")
    check(all(fx.p_evolution_metal_pokemon(c) for c in a.hand),
          f"only Evolution Metal Pokémon may be taken, got {[c.name for c in a.hand]}")
    check(len(a.deck) == 4, f"deck must shrink by exactly 2, got {len(a.deck)}")
    check({c.name for c in a.deck} >= {"Beldum", "Frogadier", "Basic Metal Energy"},
          f"non-qualifying cards must stay in the deck, got {[c.name for c in a.deck]}")

    # --- 2. only 1 available -> takes 1. ---
    st, a, b = fresh_state(db)
    gen2 = InPlayPokemon(card=gen_card)
    a.active = gen2
    a.deck = [db.get("Metang"), db.get("Beldum")]
    fx._metallic_signal(ctx_for(st, a, b, source=gen2))
    check([c.name for c in a.hand] == ["Metang"],
          f"only the 1 qualifying card comes to hand, got {[c.name for c in a.hand]}")

    # --- 3. NEGATIVE: nothing qualifying -> hand untouched, and the guard refuses it. ---
    st, a, b = fresh_state(db)
    gen3 = InPlayPokemon(card=gen_card)
    a.active = gen3
    a.deck = [db.get("Beldum"), db.get("Frogadier"), db.get("Basic Metal Energy")]
    fx._metallic_signal(ctx_for(st, a, b, source=gen3))
    check(a.hand == [] and len(a.deck) == 3,
          f"nothing to find -> nothing happens, got hand={[c.name for c in a.hand]}")
    guard = fx.get_ability_can_use("Genesect ex", "Metallic Signal")
    check(guard is not None and guard(st, a, gen3) is False,
          "the guard must not offer Metallic Signal with no Evolution Metal Pokémon in deck")
    a.deck.append(db.get("Metang"))
    check(guard(st, a, gen3) is True, "the guard must offer it once one is in the deck")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_metallic_signal.py: all checks passed — Metallic Signal fetches up to 2 "
          "Evolution Metal Pokémon and nothing else")


if __name__ == "__main__":
    main()
