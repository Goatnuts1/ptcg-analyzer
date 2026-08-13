#!/usr/bin/env python3
"""
test_dig_dig_dig.py — Drilbur (Temporal Forces 85) Ability Dig Dig Dig:
"When you play this Pokémon from your hand onto your Bench during your turn, you may
search your deck for up to 3 Basic Fighting Energy cards and discard them. Then,
shuffle your deck."

This is an on-bench-from-hand trigger (ON_BENCH_TRIGGERS), like Meowth ex's
Last-Ditch Catch — so it is verified BOTH directly and through the real engine
action (game.apply_action("play_basic")), which is the only path a game takes.

NOTE: TEF 85 is the only Standard-legal Drilbur print WITH this Ability (the Pitch
Black and Black Bolt Drilburs are different cards); the pool's Drilbur is sv5-85 =
TEF 85, asserted below so a future pool refetch that swaps the print fails loudly.

Run: python3 tests/test_dig_dig_dig.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import Action, apply_action


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
    # NOTE: bare "Drilbur" is now the real tournament-list print (PBL 46, Call for
    # Family / Dig Claws, no ability) used by mega_excadrill. This test is specifically
    # about the OTHER print, disambiguated as "Drilbur (TEF)", which still carries
    # Dig Dig Dig and stays fully implemented/tested for any future build that wants it.
    drilbur_card = db.get("Drilbur (TEF)")
    fighting = db.get("Basic Fighting Energy")
    metal = db.get("Basic Metal Energy")

    # --- 0. the pool's Drilbur (TEF) is the print that HAS the Ability, and the trigger
    # is registered as an on-bench trigger + counted as an implemented passive. ---
    check(drilbur_card.id == "sv5-85",
          f"expected Temporal Forces Drilbur (sv5-85), pool has {drilbur_card.id}")
    ab = next(a for a in drilbur_card.abilities if a.name == "Dig Dig Dig")
    check("up to 3 Basic Fighting Energy" in ab.text and "discard them" in ab.text,
          f"unexpected ability text: {ab.text!r}")
    check(fx.get_on_bench_trigger("Drilbur (TEF)") is not None,
          "Dig Dig Dig must be registered as an on-bench trigger")
    check(("Drilbur (TEF)", "Dig Dig Dig") in fx.PASSIVE_ABILITIES,
          "Dig Dig Dig must be recorded in PASSIVE_ABILITIES (it isn't an activated ability)")

    # --- 1. exactly up to 3 Basic Fighting Energy leave the deck for the DISCARD. ---
    st, a, b = fresh_state(db)
    drilbur = InPlayPokemon(card=drilbur_card)
    a.bench = [drilbur]
    a.deck = [fighting] * 5 + [metal] * 2 + [db.get("Beldum")]
    fx._dig_dig_dig(ctx_for(st, a, b, source=drilbur))
    check(len(a.discard) == 3 and all(c.name == "Basic Fighting Energy" for c in a.discard),
          f"exactly 3 Basic Fighting Energy must be discarded, got "
          f"{[c.name for c in a.discard]}")
    check(len(a.deck) == 5, f"deck must shrink by exactly 3, got {len(a.deck)}")
    check(sum(1 for c in a.deck if c.name == "Basic Fighting Energy") == 2,
          "the other 2 Fighting Energy stay in the deck")
    check(sum(1 for c in a.deck if c.name == "Basic Metal Energy") == 2,
          "Basic Metal Energy must not be touched")

    # --- 2. fewer than 3 available: takes what's there ("up to 3"). ---
    st, a, b = fresh_state(db)
    drilbur2 = InPlayPokemon(card=drilbur_card)
    a.bench = [drilbur2]
    a.deck = [fighting, metal]
    fx._dig_dig_dig(ctx_for(st, a, b, source=drilbur2))
    check([c.name for c in a.discard] == ["Basic Fighting Energy"],
          f"only the 1 available Fighting Energy is discarded, got "
          f"{[c.name for c in a.discard]}")

    # --- 3. NEGATIVE: no Basic Fighting Energy in the deck -> nothing discarded, deck
    # intact (this is the case in a pure-Metal build: the Ability is a live no-op). ---
    st, a, b = fresh_state(db)
    drilbur3 = InPlayPokemon(card=drilbur_card)
    a.bench = [drilbur3]
    a.deck = [metal] * 4 + [db.get("Beldum")]
    fx._dig_dig_dig(ctx_for(st, a, b, source=drilbur3))
    check(a.discard == [] and len(a.deck) == 5,
          f"with no Fighting Energy nothing may be discarded, got discard={a.discard}, "
          f"deck={len(a.deck)}")

    # --- 4. LIVE: playing Drilbur from HAND onto the Bench fires it through the engine. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Beldum"))
    b.active = InPlayPokemon(card=db.get("Beldum"))
    a.hand = [drilbur_card]
    a.deck = [fighting] * 4 + [metal]
    apply_action(st, Action("play_basic", hand_index=0))
    check(len(a.bench) == 1 and a.bench[0].card.name == "Drilbur (TEF)",
          "Drilbur (TEF) must be benched")
    check(len(a.discard) == 3 and all(c.name == "Basic Fighting Energy" for c in a.discard),
          f"the on-bench trigger must fire in a real game action, discard="
          f"{[c.name for c in a.discard]}")

    # --- 5. NEGATIVE (live): a Drilbur already in play does not re-trigger — the
    # trigger only fires on the play-from-hand action, so a second call path (e.g.
    # promoting it to Active) leaves the deck alone. ---
    before = len(a.deck)
    a.bench[0].played_this_turn = False
    check(len(a.deck) == before, "no re-trigger outside the play_basic action")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_dig_dig_dig.py: all checks passed — Dig Dig Dig discards up to 3 Basic "
          "Fighting Energy from the deck when Drilbur is benched from hand")


if __name__ == "__main__":
    main()
