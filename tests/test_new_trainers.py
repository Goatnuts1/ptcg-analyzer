#!/usr/bin/env python3
"""
test_new_trainers.py — assert Enhanced Hammer, Eri, Special Red Card, and
Scoop Up Cyclone each do EXACTLY what their card text says (data/standard_pool.json
is the legality/name-matching source; exact wording is quoted per-block below).

Run from project root:

    python3 tests/test_new_trainers.py
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
    st.active_index = 0     # a is "me" / the acting player, b is "opp"
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # =================================================================== #
    # ENHANCED HAMMER (sv6-148, Item)
    # pool text: "Discard a Special Energy from 1 of your opponent's
    # Pokémon." / "You may play any number of Item cards during your turn."
    # =================================================================== #

    # --- picks the Pokémon carrying the most Special Energy, strips only
    #     ONE Special Energy from it, and leaves Basic Energy untouched ---
    st, a, b = fresh_state(db)
    b.active = InPlayPokemon(card=db.get("Dreepy"))
    b.active.energy = [db.get("Basic Fire Energy"), db.get("Jet Energy")]
    bench_mon = InPlayPokemon(card=db.get("Pikachu ex"))
    bench_mon.energy = [db.get("Jet Energy"), db.get("Prism Energy")]   # 2 Special > active's 1
    b.bench = [bench_mon]

    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._enhanced_hammer(ctx)

    check(did, "Enhanced Hammer should succeed when opponent has Special Energy in play")
    check(len(bench_mon.energy) == 1,
          f"Enhanced Hammer should discard exactly 1 Special Energy from the target, "
          f"bench_mon has {len(bench_mon.energy)} energy left")
    check(len(b.active.energy) == 2,
          "Enhanced Hammer should target the most-loaded Pokémon (bench), not the active")
    check(sum(1 for c in b.discard if c.name in ("Jet Energy", "Prism Energy")) == 1,
          "exactly 1 Special Energy card should land in the discard pile")
    check(any(c.name == "Basic Fire Energy" for c in b.active.energy),
          "Basic Energy must NOT be discarded by Enhanced Hammer")

    # --- negative: no Special Energy anywhere in play -> no-op, false ---
    st, a, b = fresh_state(db)
    b.active = InPlayPokemon(card=db.get("Dreepy"))
    b.active.energy = [db.get("Basic Fire Energy")]
    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._enhanced_hammer(ctx)
    check(not did, "Enhanced Hammer should fail with no Special Energy in play")
    check(len(b.active.energy) == 1 and len(b.discard) == 0,
          "Enhanced Hammer must not touch Basic Energy when no Special Energy exists")

    # --- can_play gate ---
    st, a, b = fresh_state(db)
    b.active = InPlayPokemon(card=db.get("Dreepy"))
    b.active.energy = [db.get("Jet Energy")]
    check(fx.can_play_trainer(st, a, "Enhanced Hammer"),
          "Enhanced Hammer should be playable when opponent has Special Energy attached")

    st, a, b = fresh_state(db)
    b.active = InPlayPokemon(card=db.get("Dreepy"))
    b.active.energy = [db.get("Basic Fire Energy")]
    check(not fx.can_play_trainer(st, a, "Enhanced Hammer"),
          "Enhanced Hammer should be unplayable with only Basic Energy in play")

    # =================================================================== #
    # ERI (sv5-146, Supporter)
    # pool text: "Your opponent reveals their hand, and you discard up to 2
    # Item cards you find there." / "You may play only 1 Supporter card
    # during your turn."
    # =================================================================== #

    # --- 2+ Items in opponent's hand -> exactly 2 discarded, non-Items kept ---
    st, a, b = fresh_state(db)
    b.hand = [db.get("Ultra Ball"), db.get("Ultra Ball"), db.get("Boss's Orders"), db.get("Dreepy")]
    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._eri(ctx)
    check(did, "Eri should succeed when opponent's hand has Items")
    check(sum(1 for c in b.discard if c.name == "Ultra Ball") == 2,
          "Eri should discard exactly 2 Items when 2+ are present")
    check(not any(c.name == "Ultra Ball" for c in b.hand),
          "both Ultra Balls should have left the hand")
    check(any(c.name == "Boss's Orders" for c in b.hand) and any(c.name == "Dreepy" for c in b.hand),
          "Eri must not discard the Supporter or the Pokémon in hand")
    check(len(b.hand) == 2, "hand should shrink by exactly 2 (the Items)")

    # --- only 1 Item present -> discards that 1 (not an error, not 2) ---
    st, a, b = fresh_state(db)
    b.hand = [db.get("Ultra Ball"), db.get("Dreepy")]
    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._eri(ctx)
    check(did, "Eri should succeed with a single Item present")
    check(len(b.discard) == 1 and b.discard[0].name == "Ultra Ball",
          "Eri should discard the lone Item")
    check(len(b.hand) == 1 and b.hand[0].name == "Dreepy",
          "Eri should discard 'up to 2' -- exactly 1 here, not more")

    # --- negative: no Items in hand -> no-op, false ---
    st, a, b = fresh_state(db)
    b.hand = [db.get("Dreepy"), db.get("Boss's Orders")]
    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._eri(ctx)
    check(not did, "Eri should fail when opponent's hand has no Items")
    check(len(b.discard) == 0 and len(b.hand) == 2,
          "Eri must not discard anything when there are no Items to find")

    # --- can_play gate ---
    st, a, b = fresh_state(db)
    b.hand = [db.get("Ultra Ball")]
    check(fx.can_play_trainer(st, a, "Eri"),
          "Eri should be playable when opponent holds an Item")
    st, a, b = fresh_state(db)
    b.hand = [db.get("Dreepy"), db.get("Boss's Orders")]
    check(not fx.can_play_trainer(st, a, "Eri"),
          "Eri should be unplayable when opponent holds no Items")

    # =================================================================== #
    # SPECIAL RED CARD (me4-82, Item)
    # pool text: "You can use this card only if your opponent has 3 or fewer
    # Prize cards remaining.\n\nYour opponent shuffles their hand and puts
    # it on the bottom of their deck. If they put any cards on the bottom
    # of their deck in this way, they draw 3 cards."
    # =================================================================== #

    # --- gate: playable at exactly 3 prizes remaining, full effect fires ---
    st, a, b = fresh_state(db)
    b.prizes = [db.get("Basic Fire Energy")] * 3          # 3 remaining -> gate passes
    b.hand = [db.get("Dreepy"), db.get("Pikachu ex")]
    b.deck = [db.get("Cheren"), db.get("Judge"), db.get("Boss's Orders")] + \
             [db.get("Basic Water Energy")] * 5
    deck_len_before = len(b.deck)
    check(fx.can_play_trainer(st, a, "Special Red Card"),
          "Special Red Card should be playable at exactly 3 prizes remaining")

    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._special_red_card(ctx)
    check(did, "Special Red Card should succeed against a non-empty hand")
    check(len(b.hand) == 3, "opponent should draw exactly 3 cards")
    check([c.name for c in b.hand] == ["Cheren", "Judge", "Boss's Orders"],
          "opponent draws from the TOP of the deck (the pre-existing cards), not the bottomed hand")
    check(len(b.deck) == deck_len_before - 3 + 2,
          "deck nets -3 (drawn) +2 (bottomed hand)")
    check(any(c.name == "Dreepy" for c in b.deck) and any(c.name == "Pikachu ex" for c in b.deck),
          "the original hand should have been shuffled onto the BOTTOM of the deck")

    # --- gate: unplayable at 4+ prizes remaining ---
    st, a, b = fresh_state(db)
    b.prizes = [db.get("Basic Fire Energy")] * 4
    b.hand = [db.get("Dreepy")]
    check(not fx.can_play_trainer(st, a, "Special Red Card"),
          "Special Red Card should be unplayable once opponent has 4+ prizes remaining")

    # --- negative: opponent has an empty hand -> no shuffle, no draw ---
    st, a, b = fresh_state(db)
    b.prizes = [db.get("Basic Fire Energy")] * 2
    b.hand = []
    b.deck = [db.get("Cheren")] * 5
    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._special_red_card(ctx)
    check(not did, "Special Red Card should fail against an empty hand")
    check(len(b.hand) == 0 and len(b.deck) == 5,
          "'if they put any cards on the bottom...' -- empty hand means no shuffle and no draw")
    check(not fx.can_play_trainer(st, a, "Special Red Card"),
          "Special Red Card should be unplayable when opponent's hand is empty, even at <=3 prizes")

    # =================================================================== #
    # SCOOP UP CYCLONE (sv6-162, Item, ACE SPEC)
    # pool text: "You can't have more than 1 ACE SPEC card in your deck." /
    # "Put 1 of your Pokémon and all attached cards into your hand." /
    # "You may play any number of Item cards during your turn." /
    # "ACE SPEC: You can't have more than 1 ACE SPEC card in your deck."
    # =================================================================== #

    # --- returns the most-damaged bench Pokémon + all attached cards
    #     (energy, Tool, evolved-from stage) to hand; active is untouched ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))       # healthy, untouched
    mon1 = InPlayPokemon(card=db.get("Dreepy"))
    mon1.damage = 30
    mon2 = InPlayPokemon(card=db.get("Drakloak"))
    mon2.damage = 60                                            # most damaged -> the target
    mon2.energy = [db.get("Basic Fire Energy"), db.get("Jet Energy")]
    mon2.tool = db.get("Air Balloon")
    mon2.evolved_from = [db.get("Dreepy")]
    a.bench = [mon1, mon2]
    hand_before = len(a.hand)

    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._scoop_up_cyclone(ctx)

    check(did, "Scoop Up Cyclone should succeed with a damaged bench Pokémon present")
    check(mon2 not in a.bench and mon1 in a.bench,
          "should pick up the MOST damaged Pokémon (mon2), leaving the less-damaged one")
    check(any(c.name == "Drakloak" for c in a.hand), "the Pokémon card itself returns to hand")
    check(any(c.name == "Dreepy" for c in a.hand),
          "'all attached cards' includes the prior evolution stage")
    check(any(c.name == "Basic Fire Energy" for c in a.hand) and
          any(c.name == "Jet Energy" for c in a.hand),
          "all attached Energy returns to hand")
    check(any(c.name == "Air Balloon" for c in a.hand), "the attached Tool returns to hand")
    check(len(a.hand) == hand_before + 5,
          "card + 2 energy + 1 evolved-from + 1 tool = 5 new cards in hand")
    check(a.active.card.name == "Dragapult ex", "the Active should be left alone")

    # --- negative: never orphan the Active (damaged Active, empty bench) ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active.damage = 100
    a.bench = []
    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._scoop_up_cyclone(ctx)
    check(not did, "Scoop Up Cyclone must not pick up the Active when there's no Bench to promote")
    check(a.active is not None and a.active.damage == 100,
          "Active must be left in place when it can't legally be picked up")
    check(not fx.can_play_trainer(st, a, "Scoop Up Cyclone"),
          "can_play should refuse Scoop Up Cyclone when it would orphan the Active")

    # --- picking up the Active when a Bench exists promotes the healthiest
    #     Bench Pokémon (never leaves the player without an Active) ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dreepy"))
    a.active.damage = 60                                        # only damaged mon among candidates
    bench_hi = InPlayPokemon(card=db.get("Pikachu ex"))          # 200 HP, remaining 200
    bench_lo = InPlayPokemon(card=db.get("Flutter Mane"))        # 90 HP, remaining 90
    a.bench = [bench_lo, bench_hi]
    ctx = fx.EffectContext(state=st, me=a, opp=b, rng=st.rng)
    did = fx._scoop_up_cyclone(ctx)
    check(did, "Scoop Up Cyclone should succeed picking up a damaged Active with a Bench present")
    check(any(c.name == "Dreepy" for c in a.hand), "the picked-up Active should return to hand")
    check(a.active is not None and a.active.card.name == "Pikachu ex",
          "should promote the Bench Pokémon with the most remaining HP")
    check(len(a.bench) == 1 and a.bench[0].card.name == "Flutter Mane",
          "the non-promoted Bench Pokémon should remain benched")

    # --- can_play positive: a damaged Bench Pokémon alone is enough ---
    st, a, b = fresh_state(db)
    dreepy = InPlayPokemon(card=db.get("Dreepy"))
    dreepy.damage = 10
    a.bench = [dreepy]
    check(fx.can_play_trainer(st, a, "Scoop Up Cyclone"),
          "Scoop Up Cyclone should be playable with any damaged Bench Pokémon")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Enhanced Hammer / Eri / Special Red Card / Scoop Up Cyclone invariants hold.")


if __name__ == "__main__":
    main()
