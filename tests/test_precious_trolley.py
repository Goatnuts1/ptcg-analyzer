#!/usr/bin/env python3
"""
test_precious_trolley.py — Precious Trolley (Surging Sparks 185), ACE SPEC Item:
"Search your deck for any number of Basic Pokémon and put them onto your Bench. Then,
shuffle your deck." / "You can't have more than 1 ACE SPEC card in your deck."

Load-bearing: BASIC Pokémon only (Evolution Pokémon and Energy are negative cases),
they go to the BENCH (not the hand), and "any number" is still capped by the 5-Bench
limit — v0 policy fills the Bench.

Run: python3 tests/test_precious_trolley.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.legality import validate_deck
from src.engine.decks import DECKS


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def trainer_ctx(st, me, opp):
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    card = db.get("Precious Trolley")

    # --- 0. card data + registry wiring. ---
    check(card.is_item and "ACE SPEC" in card.subtypes,
          f"Precious Trolley is an ACE SPEC Item, got {card.subtypes}")
    check(any("any number of Basic Pokémon and put them onto your Bench" in r
              for r in card.rules), f"unexpected card text: {card.rules}")
    check("Precious Trolley" in fx.TRAINER_EFFECTS, "Precious Trolley must be registered")

    # --- 1. it fills the Bench with Basics from the deck (bench cap 5 respected). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.deck = [db.get("Beldum")] * 4 + [db.get("Drilbur")] * 3 + [db.get("Metagross")] \
        + [db.get("Basic Metal Energy")] * 2
    did = fx._precious_trolley(trainer_ctx(st, a, b))
    check(did is True, "it must report that it acted")
    check(len(a.bench) == PlayerState.MAX_BENCH,
          f"the Bench must be filled to {PlayerState.MAX_BENCH}, got {len(a.bench)}")
    check(all(m.card.is_basic and m.card.is_pokemon for m in a.bench),
          f"only Basic Pokémon may be benched, got {[m.card.name for m in a.bench]}")
    check(all(m.played_this_turn for m in a.bench),
          "newly benched Pokémon must be marked played_this_turn (can't evolve this turn)")
    check(len(a.deck) == 5, f"the deck must lose exactly the 5 benched, got {len(a.deck)}")
    check(a.hand == [], "the Pokémon go to the BENCH, never to the hand")

    # --- 2. NEGATIVE: Evolution Pokémon and Energy are left in the deck. ---
    check(any(c.name == "Metagross" for c in a.deck), "the Stage 2 must stay in the deck")
    check(sum(1 for c in a.deck if c.name == "Basic Metal Energy") == 2,
          "Energy cards must stay in the deck")

    # --- 3. partial fill: fewer Basics available than Bench space. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.deck = [db.get("Beldum"), db.get("Metagross"), db.get("Basic Metal Energy")]
    fx._precious_trolley(trainer_ctx(st, a, b))
    check(len(a.bench) == 1 and a.bench[0].card.name == "Beldum",
          f"only the 1 available Basic is benched, got {[m.card.name for m in a.bench]}")

    # --- 4. NEGATIVE: a full Bench -> the card does nothing. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.bench = [InPlayPokemon(card=db.get("Beldum")) for _ in range(PlayerState.MAX_BENCH)]
    a.deck = [db.get("Drilbur")] * 3
    did = fx._precious_trolley(trainer_ctx(st, a, b))
    check(did is False and len(a.deck) == 3,
          f"a full Bench means nothing happens, got did={did}, deck={len(a.deck)}")
    check(fx.can_play_trainer(st, a, "Precious Trolley") is False,
          "a full Bench -> must not be offered")

    # --- 5. NEGATIVE: no Basic Pokémon in the deck -> nothing happens. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.deck = [db.get("Metagross"), db.get("Basic Metal Energy")]
    check(fx._precious_trolley(trainer_ctx(st, a, b)) is False,
          "no Basic in the deck -> must report it did nothing")
    check(a.bench == [], "nothing may be benched")
    check(fx.can_play_trainer(st, a, "Precious Trolley") is False,
          "no Basic in the deck -> must not be offered")

    # --- 6. the ACE SPEC rule holds for the deck that runs it (1 ACE SPEC total). ---
    check(validate_deck(db, DECKS["mega_excadrill"]) == [],
          "DECK_MEGA_EXCADRILL must stay legal with its single ACE SPEC (Precious Trolley)")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_precious_trolley.py: all checks passed — Precious Trolley benches only "
          "Basic Pokémon, up to the Bench limit")


if __name__ == "__main__":
    main()
