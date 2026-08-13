#!/usr/bin/env python3
"""
test_prism_tower.py — Prism Tower (Stadium, CRI 80 / pool id me4-80):
"Once during each player's turn, that player may discard 2 cards from their hand in
order to draw a card."

This is an ACTIVATED Stadium ability, so unlike the passive Stadiums (Battle Cage,
Gravity Mountain, Team Rocket's Watchtower) it is an engine ACTION — the same shape
as Surfing Beach's free once-per-turn switch:
  game.legal_actions offers Action("stadium_draw"), game.apply_action resolves it,
  and PlayerState.stadium_draw_used_this_turn is its own once-per-turn budget,
  reset by start_turn.

What this pins down: the cost is paid BEFORE the draw and is exactly 2 cards; it is
once per turn PER PLAYER (both players get one, and the two budgets are independent);
it is not offered without 2 cards in hand or without a deck to draw from; and it
disappears the moment Prism Tower leaves the Stadium zone.

Run: python3 tests/test_prism_tower.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import effects as fx
from src.engine.game import legal_actions, apply_action, start_turn, Action


def board(db, hand_names, deck_n=10, stadium="Prism Tower"):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.active = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.hand = [db.get(n) for n in hand_names]
    a.deck = [db.get("Basic Psychic Energy")] * deck_n
    b.deck = [db.get("Basic Psychic Energy")] * deck_n
    b.hand = [db.get("Boss's Orders")] * 3
    a.turns_taken = 3
    b.turns_taken = 3
    if stadium is not None:
        st.stadium = db.get(stadium)
        st.stadium_owner = 0
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 0. registered as an implemented Stadium. ---
    check("Prism Tower" in fx.STADIUM_IMPLEMENTED,
          "Prism Tower must be listed in STADIUM_IMPLEMENTED")
    check(db.get("Prism Tower").rules[0].startswith("Once during each player's turn"),
          "sanity: the pool's Prism Tower text must be the once-per-turn draw")

    # --- 1. POSITIVE: the action is offered, costs exactly 2 cards, draws exactly 1. ---
    st, a, b = board(db, ["Boss's Orders", "Ultra Ball", "Shuppet (PBL)", "Poké Pad"])
    acts = [x for x in legal_actions(st) if x.kind == "stadium_draw"]
    check(len(acts) == 1, f"exactly one stadium_draw action should be offered, got {len(acts)}")
    apply_action(st, acts[0])
    check(len(a.hand) == 4 - 2 + 1,
          f"discard 2 then draw 1 -> a 4-card hand becomes 3, got {len(a.hand)}")
    check(len(a.discard) == 2,
          f"exactly 2 cards must reach the discard pile, got {len(a.discard)}")
    check(len(a.deck) == 9, f"exactly 1 card is drawn, got deck={len(a.deck)}")

    # --- 2. ONCE per turn: it is gone for the rest of this turn... ---
    check(a.stadium_draw_used_this_turn is True,
          "using it must consume this turn's Prism Tower budget")
    check(not [x for x in legal_actions(st) if x.kind == "stadium_draw"],
          "Prism Tower must not be offered twice in the same turn")

    # --- 3. ...and comes back next turn. ---
    start_turn(st)
    check(a.stadium_draw_used_this_turn is False,
          "start_turn must reset the Prism Tower budget")
    check([x for x in legal_actions(st) if x.kind == "stadium_draw"],
          "Prism Tower must be available again on the next turn")

    # --- 4. "each player" — the opponent has their OWN independent use. ---
    st, a, b = board(db, ["Boss's Orders", "Ultra Ball", "Shuppet (PBL)", "Poké Pad"])
    apply_action(st, Action("stadium_draw"))
    st.active_index = 1                     # over to B
    acts_b = [x for x in legal_actions(st) if x.kind == "stadium_draw"]
    check(len(acts_b) == 1,
          "A using Prism Tower must not consume B's use — 'each player' gets one")
    apply_action(st, acts_b[0])
    check(len(b.discard) == 2 and len(b.hand) == 3 - 2 + 1,
          f"B's own use must resolve normally, got discard={len(b.discard)} "
          f"hand={len(b.hand)}")

    # --- 5. NEGATIVE: not offered when the cost can't be paid (fewer than 2 cards)... ---
    st, a, b = board(db, ["Boss's Orders"])
    check(not [x for x in legal_actions(st) if x.kind == "stadium_draw"],
          "with only 1 card in hand the 2-card cost can't be paid — don't offer it")

    # --- 6. ...nor when there is nothing left to draw. ---
    st, a, b = board(db, ["Boss's Orders", "Ultra Ball"], deck_n=0)
    check(not [x for x in legal_actions(st) if x.kind == "stadium_draw"],
          "with an empty deck the draw does nothing — don't offer it")

    # --- 7. NEGATIVE: no Prism Tower in the Stadium zone, no action. A DIFFERENT
    #        Stadium must not grant it either. ---
    st, a, b = board(db, ["Boss's Orders", "Ultra Ball", "Shuppet (PBL)"], stadium=None)
    check(not [x for x in legal_actions(st) if x.kind == "stadium_draw"],
          "with no Stadium in play there is no Prism Tower action")
    st, a, b = board(db, ["Boss's Orders", "Ultra Ball", "Shuppet (PBL)"],
                     stadium="Battle Cage")
    check(not [x for x in legal_actions(st) if x.kind == "stadium_draw"],
          "Battle Cage must not grant Prism Tower's draw")

    # --- 8. the action doesn't end the turn (it is a free action, like Surfing Beach). ---
    st, a, b = board(db, ["Boss's Orders", "Ultra Ball", "Shuppet (PBL)"])
    apply_action(st, Action("stadium_draw"))
    check(st.phase is Phase.MAIN,
          f"Prism Tower's draw is a free action and must leave the phase in MAIN, "
          f"got {st.phase}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_prism_tower.py: all checks passed — discard 2 / draw 1, once per turn "
          "per player, gated on being payable and on Prism Tower actually being in play")


if __name__ == "__main__":
    main()
