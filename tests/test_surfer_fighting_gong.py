#!/usr/bin/env python3
"""
test_surfer_fighting_gong.py — the two support Trainers of the Cynthia's Garchomp ex
list, each asserted against its exact card text.

  Surfer (sv8 187, Supporter): "Switch your Active Pokémon with 1 of your Benched
  Pokémon. If you do, draw cards until you have 5 cards in your hand."

  Fighting Gong (me1 116, Item): "Search your deck for a Basic {F} Energy card or a
  Basic {F} Pokémon, reveal it, and put it into your hand. Then, shuffle your deck."

The load-bearing clauses: Surfer's draw is CONDITIONAL on the switch ("if you do"), and
counts UP TO 5 (never discarding down); Fighting Gong finds exactly ONE card, and its two
"Basic"s mean different things — a Basic Energy CARD or a Basic-stage Fighting Pokémon
(so a Stage 1 Fighting Pokémon and a Special Energy must both be unfindable).

Run: python3 tests/test_surfer_fighting_gong.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.active_index = 0
    return st, a, b


def ctx_for(st, me, opp):
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=st.rng,
                            effect_kind="trainer")


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    check(db.get("Surfer").is_supporter, "Surfer must be a Supporter (1 per turn)")
    check(db.get("Fighting Gong").is_item, "Fighting Gong must be an Item")

    # ===================================================================== #
    # SURFER
    # ===================================================================== #
    # --- 1. Switch happens AND the hand is refilled to exactly 5. The Surfer card itself
    # is already out of hand when the effect runs (play_trainer pops first), so 5 means 5. ---
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))   # healthiest -> comes up
    a.active = gible
    a.bench = [chomp]
    a.hand = [db.get("Basic Fighting Energy")]
    a.deck = [db.get("Basic Fighting Energy")] * 10
    check(fx._surfer(ctx_for(st, a, b)) is True, "Surfer must report that it acted")
    check(a.active is chomp, "the Benched Pokémon must become the Active")
    check(len(a.bench) == 1 and a.bench[0] is gible,
          "the old Active must go to the Bench (a switch, not a promotion)")
    check(len(a.hand) == 5, f"the hand must be filled to exactly 5, got {len(a.hand)}")
    check(len(a.deck) == 6, f"it must draw exactly 4 here (deck 10 -> 6), got {len(a.deck)}")

    # --- 2. NEGATIVE: a hand already at/above 5 draws NOTHING (never discards down). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))]
    a.hand = [db.get("Basic Fighting Energy")] * 7
    a.deck = [db.get("Basic Fighting Energy")] * 10
    check(fx._surfer(ctx_for(st, a, b)) is True,
          "the switch still happens with a full hand, so the card is still played")
    check(len(a.hand) == 7 and len(a.deck) == 10,
          f"with 7 cards in hand it must draw 0 and discard none, got hand={len(a.hand)}")

    # --- 3. NEGATIVE: "If you do" — with an empty Bench there is no switch, so there is
    # NO draw and the card reports that it did nothing (play_trainer puts it back). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.bench = []
    a.hand = []
    a.deck = [db.get("Basic Fighting Energy")] * 10
    check(fx._surfer(ctx_for(st, a, b)) is False,
          "with no Bench the switch is impossible, so Surfer must return False")
    check(a.hand == [], "no switch -> no draw ('if you do')")
    check(fx.can_play_trainer(st, a, "Surfer") is False,
          "can_play must also refuse Surfer with an empty Bench")
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))]
    check(fx.can_play_trainer(st, a, "Surfer") is True,
          "can_play must allow Surfer once there is a Benched Pokémon")

    # --- 4. A short deck draws only what's left (no crash, no phantom cards). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))]
    a.hand = []
    a.deck = [db.get("Basic Fighting Energy")] * 2
    fx._surfer(ctx_for(st, a, b))
    check(len(a.hand) == 2 and a.deck == [],
          f"a 2-card deck must yield a 2-card hand, got {len(a.hand)}")

    # ===================================================================== #
    # FIGHTING GONG
    # ===================================================================== #
    # --- 5. Finds exactly ONE card. With both kinds available the v0 search policy takes
    # the Pokémon (evolution fodder ranks above Energy) — either is legal by the text; the
    # assertion that matters is "exactly one card moved". ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Basic Fighting Energy"), db.get("Cynthia's Gible"),
              db.get("Basic Grass Energy"), db.get("Cynthia's Roselia")]
    check(fx._fighting_gong(ctx_for(st, a, b)) is True, "Fighting Gong must report success")
    check(len(a.hand) == 1, f"exactly 1 card must be found ('a ... or a ...'), got "
                            f"{[c.name for c in a.hand]}")
    check(a.hand[0].name in ("Basic Fighting Energy", "Cynthia's Gible"),
          f"the found card must be a Basic Fighting Energy or Basic Fighting Pokémon, got "
          f"{a.hand[0].name}")
    check(len(a.deck) == 3, f"the deck must shrink by exactly 1, got {len(a.deck)}")

    # --- 6. It can find the Energy when that's the only match. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Basic Grass Energy"), db.get("Basic Fighting Energy")]
    fx._fighting_gong(ctx_for(st, a, b))
    check([c.name for c in a.hand] == ["Basic Fighting Energy"],
          f"with only the Energy matching, that's what must be found, got "
          f"{[c.name for c in a.hand]}")

    # --- 7. NEGATIVE: wrong type, wrong stage, and wrong Energy kind are all unfindable.
    #   Cynthia's Gabite  -> Fighting but STAGE 1, not a Basic Pokémon
    #   Rocky Fighting Energy -> provides {F} but is a SPECIAL Energy, not a Basic Energy
    #   Cynthia's Roselia / Basic Grass Energy -> Grass ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Cynthia's Gabite"), db.get("Rocky Fighting Energy"),
              db.get("Cynthia's Roselia"), db.get("Basic Grass Energy")]
    check(fx._fighting_gong(ctx_for(st, a, b)) is False,
          "none of these match 'a Basic {F} Energy card or a Basic {F} Pokémon'")
    check(a.hand == [], f"nothing may be put into hand, got {[c.name for c in a.hand]}")
    check(fx.can_play_trainer(st, a, "Fighting Gong") is False,
          "can_play must refuse Fighting Gong with no legal target in the deck")
    a.deck.append(db.get("Cynthia's Gible"))
    check(fx.can_play_trainer(st, a, "Fighting Gong") is True,
          "can_play must allow it once a Basic Fighting Pokémon is in the deck")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_surfer_fighting_gong.py: all checks passed — Surfer only draws when the "
          "switch happens (up to 5), Fighting Gong finds exactly one Basic Fighting "
          "Energy/Basic Fighting Pokémon and nothing else")


if __name__ == "__main__":
    main()
