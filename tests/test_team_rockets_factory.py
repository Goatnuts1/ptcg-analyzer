#!/usr/bin/env python3
"""
test_team_rockets_factory.py — Team Rocket's Factory (Stadium, DRI 173/182):

    "Once during each player's turn, if they played a Supporter card that has
     'Team Rocket' in its name from their hand this turn, they may draw 2 cards."
    (+ the standard Stadium rule.)

This is an ACTIVATED Stadium with a CONDITION, so it follows the Prism Tower shape —
an engine action ("stadium_factory") with its own once-per-turn budget on PlayerState —
plus one extra piece the other Stadiums don't need: the condition itself, tracked as
PlayerState.team_rocket_supporter_played_this_turn and set by game.apply_action at the
moment such a Supporter actually resolves.

What this pins down: the draw is exactly 2; it is once per turn PER PLAYER with
independent budgets; the condition is REQUIRED and is scoped to THIS turn (it resets,
so last turn's Petrel does not switch it on again); a non-Team-Rocket Supporter does
NOT switch it on; an Item with "Team Rocket" in its name (Transceiver) does NOT switch
it on, because the card says Supporter; playing the Supporter BEFORE the Stadium
arrives still counts; and it is not offered without the Factory in play.

NOTE: this card is NOT an ACE SPEC (an early web result conflated it with an unrelated
ACE SPEC line on the same page). The pool entry is the authority and is asserted below.

Run: python3 tests/test_team_rockets_factory.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import effects as fx
from src.engine.game import legal_actions, apply_action, start_turn, end_turn, Action

RULE = ("Once during each player's turn, if they played a Supporter card that has "
        "\"Team Rocket\" in its name from their hand this turn, they may draw 2 cards.")


def board(db, stadium="Team Rocket's Factory", deck_n=10):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.active = InPlayPokemon(card=db.get("Doublade"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.turns_taken = 3
    b.turns_taken = 3
    # Both decks carry a couple of Trainers so Team Rocket's Petrel ("search your deck
    # for a Trainer card") actually resolves — a Supporter that does nothing is put back
    # in hand by the engine and was never played, which is its own case in section 11.
    a.deck = ([db.get("Rare Candy")] * 2 + [db.get("Basic Metal Energy")] * deck_n)[:deck_n]
    b.deck = ([db.get("Rare Candy")] * 2 + [db.get("Basic Psychic Energy")] * deck_n)[:deck_n]
    if stadium is not None:
        st.stadium = db.get(stadium)
        st.stadium_owner = 0
    return st, a, b


def play_named(st, p, name):
    """Play the named Trainer from p's hand through the real engine. Returns True if
    the engine offered and applied it."""
    acts = [x for x in legal_actions(st) if x.kind == "play_trainer"
            and p.hand[x.hand_index].name == name]
    if not acts:
        return False
    apply_action(st, acts[0])
    return True


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 0. the pool entry is the card, and it is a plain (non-ACE SPEC) Stadium. ---
    fac = db.get("Team Rocket's Factory")
    check("Stadium" in fac.subtypes, f"it must be a Stadium, got {fac.subtypes}")
    check("ACE SPEC" not in fac.subtypes,
          f"Team Rocket's Factory is NOT an ACE SPEC, got {fac.subtypes}")
    check(fac.rules and fac.rules[0] == RULE,
          f"the pool's rule text must match the printed card, got {fac.rules}")
    check("Team Rocket's Factory" in fx.STADIUM_IMPLEMENTED,
          "it must be listed in STADIUM_IMPLEMENTED")

    # --- 1. NEGATIVE FIRST: with the Factory in play but NO Team Rocket Supporter
    #        played this turn, the action must not be offered at all. ---
    st, a, b = board(db)
    a.hand = [db.get("Rare Candy")]
    check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
          "no Team Rocket Supporter played this turn -> no draw")
    check(a.team_rocket_supporter_played_this_turn is False,
          "the condition flag must start off")

    # --- 2. POSITIVE: play Team Rocket's Petrel (a Supporter with 'Team Rocket' in its
    #        name), then the draw-2 becomes available and draws exactly 2. ---
    st, a, b = board(db)
    a.hand = [db.get("Team Rocket's Petrel")]
    check(play_named(st, a, "Team Rocket's Petrel"),
          "sanity: Team Rocket's Petrel must be playable (it searches a Trainer)")
    check(a.team_rocket_supporter_played_this_turn is True,
          "playing a 'Team Rocket' Supporter must set the Factory's condition")
    acts = [x for x in legal_actions(st) if x.kind == "stadium_factory"]
    check(len(acts) == 1, f"exactly one stadium_factory action should be offered, got {len(acts)}")
    if acts:
        hand_before, deck_before = len(a.hand), len(a.deck)
        apply_action(st, acts[0])
        check(len(a.hand) == hand_before + 2,
              f"the Factory draws exactly 2, got {len(a.hand) - hand_before}")
        check(len(a.deck) == deck_before - 2,
              f"...off the top of the deck, got {deck_before - len(a.deck)} taken")
        check(a.discard and a.discard[-1].name == "Team Rocket's Petrel",
              "sanity: the Supporter itself went to the discard when it was played")
        check(st.phase is Phase.MAIN,
              f"the draw is a FREE action and must not end the turn, got {st.phase}")
        check(any("Team Rocket's Factory: drew 2" in line for line in st.log),
              f"the draw must be visible in the log, got {st.log[-3:]}")

    # --- 3. ONCE per turn: gone for the rest of this turn, back next turn (but only
    #        if the condition is met again — see 4). ---
        check(a.stadium_factory_used_this_turn is True,
              "using it must consume this turn's Factory budget")
        check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
              "'Once during each player's turn' — no second draw this turn")

    # --- 4. the condition is scoped to THIS TURN: it resets, so last turn's Petrel
    #        does not switch the Factory on again. This is the clause most likely to
    #        be implemented as a sticky flag by accident. ---
    st.active_index = 1
    start_turn(st)
    st.active_index = 0
    start_turn(st)
    check(a.stadium_factory_used_this_turn is False,
          "start_turn must reset the Factory's once-per-turn budget")
    check(a.team_rocket_supporter_played_this_turn is False,
          "start_turn must ALSO reset the condition — 'played ... this turn' means THIS turn")
    check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
          "a new turn with no Team Rocket Supporter played must not offer the draw, even "
          "though one was played last turn")

    # --- 5. NEGATIVE: a Supporter WITHOUT 'Team Rocket' in its name doesn't count. ---
    st, a, b = board(db)
    a.hand = [db.get("Lillie's Determination")]
    check(play_named(st, a, "Lillie's Determination"),
          "sanity: Lillie's Determination must be playable")
    check(a.team_rocket_supporter_played_this_turn is False,
          "Lillie's Determination has no 'Team Rocket' in its name — it must NOT arm "
          "the Factory")
    check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
          "and therefore no draw is offered")

    # --- 6. NEGATIVE: Team Rocket's Transceiver has 'Team Rocket' in its name but is an
    #        ITEM, and the card says Supporter. It must NOT arm the Factory. ---
    st, a, b = board(db)
    a.hand = [db.get("Team Rocket's Transceiver")]
    a.deck = [db.get("Team Rocket's Petrel")] + a.deck      # give it something to find
    check(play_named(st, a, "Team Rocket's Transceiver"),
          "sanity: Team Rocket's Transceiver must be playable with a target in deck")
    check(a.team_rocket_supporter_played_this_turn is False,
          "Team Rocket's Transceiver is an ITEM — the Factory names a SUPPORTER, so it "
          "must not be armed")
    check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
          "and therefore no draw is offered")
    check(fx.p_team_rocket_supporter(db.get("Team Rocket's Transceiver")) is False,
          "p_team_rocket_supporter must reject the Item")
    check(fx.p_team_rocket_supporter(db.get("Team Rocket's Petrel")) is True,
          "p_team_rocket_supporter must accept the Supporter")

    # --- 7. ORDERING: the Supporter may be played BEFORE the Stadium arrives and still
    #        counts — the card asks what you played this turn, not what was in play. ---
    st, a, b = board(db, stadium=None)
    a.hand = [db.get("Team Rocket's Petrel"), db.get("Team Rocket's Factory")]
    check(play_named(st, a, "Team Rocket's Petrel"), "sanity: Petrel playable")
    check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
          "with no Factory in play there is no action yet")
    stad = [x for x in legal_actions(st) if x.kind == "play_stadium"]
    check(len(stad) == 1, f"the Factory must be playable as a Stadium, got {len(stad)}")
    if stad:
        apply_action(st, stad[0])
        check(fx.team_rocket_factory_active(st),
              "the Factory must now be the Stadium in play")
        check([x for x in legal_actions(st) if x.kind == "stadium_factory"],
              "a Supporter played EARLIER in the same turn still satisfies the condition")

    # --- 8. 'each player': the two players' budgets are fully independent, and each
    #        needs its OWN Team Rocket Supporter. ---
    st, a, b = board(db)
    a.hand = [db.get("Team Rocket's Petrel")]
    play_named(st, a, "Team Rocket's Petrel")
    apply_action(st, Action("stadium_factory"))
    check(a.stadium_factory_used_this_turn and not b.stadium_factory_used_this_turn,
          "A's use must not consume B's")
    st.active_index = 1
    check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
          "B has not played a Team Rocket Supporter — the shared Stadium still gives "
          "them nothing")
    b.hand = [db.get("Team Rocket's Petrel")]
    check(play_named(st, b, "Team Rocket's Petrel"), "sanity: B can play Petrel too")
    acts_b = [x for x in legal_actions(st) if x.kind == "stadium_factory"]
    check(len(acts_b) == 1, "with their own Supporter played, B gets their own use")
    if acts_b:
        hand_before = len(b.hand)
        apply_action(st, acts_b[0])
        check(len(b.hand) == hand_before + 2, "B draws 2 as well")

    # --- 9. NEGATIVE: no Factory in play (or a different Stadium) -> never offered,
    #        even with the condition satisfied. ---
    for stadium in (None, "Gravity Mountain"):
        st, a, b = board(db, stadium=stadium)
        a.hand = [db.get("Team Rocket's Petrel")]
        play_named(st, a, "Team Rocket's Petrel")
        check(a.team_rocket_supporter_played_this_turn is True,
              "sanity: the condition is armed")
        check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
              f"with stadium={stadium!r} the Factory's draw must not exist")

    # --- 10. NEGATIVE: an empty deck means the draw would do nothing -> not offered
    #         (the engine never offers a no-op action). ---
    st, a, b = board(db, deck_n=0)
    a.hand = [db.get("Team Rocket's Petrel"), db.get("Rare Candy")]
    a.team_rocket_supporter_played_this_turn = True     # condition satisfied directly
    check(not [x for x in legal_actions(st) if x.kind == "stadium_factory"],
          "with an empty deck there is nothing to draw — don't offer it")

    # --- 11. a Supporter that did NOTHING was never "played": the engine puts it back
    #         in hand, so it must not arm the Factory either. ---
    st, a, b = board(db, deck_n=0)
    a.hand = [db.get("Team Rocket's Petrel")]            # no deck -> nothing to search
    played = play_named(st, a, "Team Rocket's Petrel")
    check(not played or a.team_rocket_supporter_played_this_turn is False,
          "a Supporter whose effect failed is returned to hand and was never played — "
          "it must not arm the Factory")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_team_rockets_factory.py: all checks passed — draw exactly 2, once per "
          "turn per player, only after a 'Team Rocket' SUPPORTER was played THIS turn, "
          "and only while the Factory is the Stadium in play")


if __name__ == "__main__":
    main()
