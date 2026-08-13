#!/usr/bin/env python3
"""
test_slowking_ogerpon_trainers.py — the Slowking / Ogerpon Box Trainer + Special
Energy suite added this session. Card text quoted from data/standard_pool.json
`rules` fields, cross-checked against limitlesstcg.com per the implementer notes.

Covers:
  - Wondrous Patch (me2-94, Item): "Attach a Basic Psychic Energy card from your
    discard pile to 1 of your Benched Psychic Pokémon."
  - Secret Box (sv6-163, ACE SPEC Item): "You can use this card only if you
    discard 3 other cards from your hand. Search your deck for an Item card, a
    Pokémon Tool card, a Supporter card, and a Stadium card, reveal them, and put
    them into your hand. Then, shuffle your deck."
  - Brave Bangle (rsv10pt5-80, Pokémon Tool): "If the Pokémon this card is
    attached to doesn't have a Rule Box, the attacks it uses do 30 more damage to
    your opponent's Active Pokémon ex (before applying Weakness and Resistance)."
  - Lucky Helmet (sv6-158, Pokémon Tool): "If the Pokémon this card is attached
    to is in the Active Spot and is damaged by an attack from your opponent's
    Pokémon (even if this Pokémon is Knocked Out), draw 2 cards."
  - Academy at Night (sv6pt5-54, Stadium): "Once during each player's turn, that
    player may put a card from their hand on top of their deck." (v0: playable in
    the Stadium zone; the active effect is a documented, NOT-modeled limitation.)
  - N's Plan (zsv10pt5-83, Supporter): "Move up to 2 Energy from your Benched
    Pokémon to your Active Pokémon."
  - Bug Catching Set (sv6-143, Item): "Look at the top 7 cards of your deck. You
    may reveal up to 2 in any combination of Grass Pokémon and Basic Grass Energy
    cards you find there and put them into your hand. Shuffle the other cards
    back into your deck."
  - Tera Orb (sv8-189, Item): "Search your deck for a Tera Pokémon, reveal it,
    and put it into your hand. Then, shuffle your deck."
  - Area Zero Underdepths (sv7-131, Stadium): "Each player who has any Tera
    Pokémon in play can have up to 8 Pokémon on their Bench. If a player no
    longer has any Tera Pokémon in play, that player discards Pokémon from their
    Bench until they have 5. When this card leaves play, both players discard
    Pokémon from their Bench until they have 5, and the player who played this
    card discards first." (Was a documented NOT-modeled limitation here; the
    per-player 8-Bench cap and both shrink clauses are now real engine hooks —
    effects.bench_limit / effects.enforce_bench_limits. Full coverage lives in
    tests/test_area_zero_underdepths.py; this file keeps the Stadium-ZONE checks
    plus a regression guard that the cap really is expanded.)
  - Telepathic Psychic Energy (por-88, Special Energy): "As long as this card is
    attached to a Pokémon, it provides Psychic Energy. When you attach this card
    from your hand to a Psychic Pokémon, search your deck for up to 2 Basic
    Psychic Pokémon and put them onto your Bench. Then, shuffle your deck."

Run from project root:  python3 tests/test_slowking_ogerpon_trainers.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx
from src.engine.game import Action


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db                    # effects read state.db for searches/chains
    st.turn_number = 5            # past turn-1 attack restriction
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source,
                            db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # =================================================================== #
    # WONDROUS PATCH (me2-94, Item)
    # Pool text: "Attach a Basic Psychic Energy card from your discard pile to
    # 1 of your Benched Psychic Pokémon."
    # =================================================================== #

    wondrous_patch = db.get("Wondrous Patch")
    check(wondrous_patch.supertype == "Trainer" and "Item" in wondrous_patch.subtypes,
          f"Wondrous Patch should be a Trainer Item, got {wondrous_patch.supertype} {wondrous_patch.subtypes}")

    # --- 1a. POSITIVE: 1 Basic Psychic Energy in discard, 1 Benched Psychic mon
    # with 0 energy -> attaches, removed from discard. ---
    st, a, b = fresh_state(db)
    bench_mon = InPlayPokemon(card=db.get("Indeedee"))          # Basic, Psychic
    a.bench = [bench_mon]
    psy_energy = db.get("Basic Psychic Energy")
    a.discard = [psy_energy]
    check(fx._TRAINER_CAN_PLAY["Wondrous Patch"](st, a),
          "can_play should be True with a Psychic bencher and Basic Psychic Energy in discard")
    ok = fx._wondrous_patch(ctx_for(st, a, b))
    check(ok, "Wondrous Patch should report success")
    check(len(bench_mon.energy) == 1 and bench_mon.energy[0].name == "Basic Psychic Energy",
          f"expected Basic Psychic Energy attached to the bencher, got {bench_mon.energy}")
    check(psy_energy not in a.discard, "the attached Energy must be removed from discard")

    # --- 1b. NEGATIVE: a Benched Psychic Pokémon exists but discard has NO Basic
    # Psychic Energy (a Fire one instead) -> can_play False, no-op. ---
    st, a, b = fresh_state(db)
    bench_mon2 = InPlayPokemon(card=db.get("Indeedee"))
    a.bench = [bench_mon2]
    fire_energy = db.get("Basic Fire Energy")
    a.discard = [fire_energy]
    check(not fx._TRAINER_CAN_PLAY["Wondrous Patch"](st, a),
          "can_play should be False with no Basic Psychic Energy in discard")
    ok = fx._wondrous_patch(ctx_for(st, a, b))
    check(not ok, "Wondrous Patch should no-op when discard has no Basic Psychic Energy")
    check(len(bench_mon2.energy) == 0, "no Energy should be attached")
    check(fire_energy in a.discard, "the unrelated Fire Energy must stay in discard")

    # --- 1c. NEGATIVE: discard has Basic Psychic Energy but NO Benched Psychic
    # Pokémon (bench is empty) -> can_play False, effect doesn't touch discard. ---
    st, a, b = fresh_state(db)
    a.bench = []
    a.discard = [db.get("Basic Psychic Energy")]
    check(not fx._TRAINER_CAN_PLAY["Wondrous Patch"](st, a),
          "can_play should be False with no Benched Psychic Pokémon")
    ok = fx._wondrous_patch(ctx_for(st, a, b))
    check(not ok, "Wondrous Patch should no-op with no Benched Psychic Pokémon")
    check(len(a.discard) == 1, "discard must be untouched when there's no valid target")

    # --- 1d. Multiple Benched Psychic Pokémon: attaches to the LEAST-LOADED one
    # (v0 policy). ---
    st, a, b = fresh_state(db)
    loaded = InPlayPokemon(card=db.get("Indeedee"))
    loaded.energy = [db.get("Basic Psychic Energy")]            # already has 1
    empty_mon = InPlayPokemon(card=db.get("Mr. Mime"))           # has 0
    a.bench = [loaded, empty_mon]
    a.discard = [db.get("Basic Psychic Energy")]
    ok = fx._wondrous_patch(ctx_for(st, a, b))
    check(ok, "Wondrous Patch should fire with 2 candidates")
    check(len(empty_mon.energy) == 1 and len(loaded.energy) == 1,
          f"must attach to the LEAST-LOADED bencher (Mr. Mime, 0 energy), not the "
          f"already-loaded one; got empty_mon={len(empty_mon.energy)} loaded={len(loaded.energy)}")

    # --- 1e. Multiple Basic Psychic Energy in discard: only 1 is attached (the
    # card text says "a Basic Psychic Energy card", singular). ---
    st, a, b = fresh_state(db)
    bench_mon3 = InPlayPokemon(card=db.get("Indeedee"))
    a.bench = [bench_mon3]
    a.discard = [db.get("Basic Psychic Energy"), db.get("Basic Psychic Energy")]
    ok = fx._wondrous_patch(ctx_for(st, a, b))
    check(ok, "Wondrous Patch should fire")
    check(len(bench_mon3.energy) == 1, f"expected exactly 1 Energy attached, got {len(bench_mon3.energy)}")
    check(len(a.discard) == 1, f"expected exactly 1 Basic Psychic Energy left in discard, got {len(a.discard)}")

    # =================================================================== #
    # SECRET BOX (sv6-163, ACE SPEC Item)
    # Pool text: "You can use this card only if you discard 3 other cards from
    # your hand. Search your deck for an Item card, a Pokémon Tool card, a
    # Supporter card, and a Stadium card, reveal them, and put them into your
    # hand. Then, shuffle your deck."
    # =================================================================== #

    secret_box = db.get("Secret Box")
    check("ACE SPEC" in secret_box.subtypes and "Item" in secret_box.subtypes,
          f"Secret Box should be an ACE SPEC Item, got {secret_box.subtypes}")

    # --- 2a. can_play: needs >=4 cards in hand (Secret Box itself + 3 others),
    # counted BEFORE the engine pops it from hand. ---
    st, a, b = fresh_state(db)
    a.hand = [secret_box, db.get("Ultra Ball"), db.get("Cheren"), db.get("Air Balloon")]
    check(fx._TRAINER_CAN_PLAY["Secret Box"](st, a),
          "can_play should be True with 4 cards in hand (Secret Box + 3 others)")
    a.hand = [secret_box, db.get("Ultra Ball"), db.get("Cheren")]
    check(not fx._TRAINER_CAN_PLAY["Secret Box"](st, a),
          "can_play should be False with only 3 cards in hand (Secret Box + 2 others)")

    # --- 2b. POSITIVE: per the hard rule "card popped from hand BEFORE the effect
    # runs" (CLAUDE.md), simulate that pop, then run the effect on exactly 3 other
    # hand cards. All 3 discarded; deck has one of each searchable type. ---
    st, a, b = fresh_state(db)
    filler1, filler2, filler3 = db.get("Ultra Ball"), db.get("Switch"), db.get("Judge")
    a.hand = [filler1, filler2, filler3]                # Secret Box already popped
    a.deck = ([db.get("Ultra Ball"), db.get("Air Balloon"),
              db.get("Cheren"), db.get("Battle Cage")]
             + [db.get("Basic Fire Energy")] * 4)
    deck_len_before = len(a.deck)
    ok = fx._secret_box(ctx_for(st, a, b))
    check(ok, "Secret Box should report success with 3 other cards to discard")
    hand_names = {c.name for c in a.hand}
    check(hand_names == {"Ultra Ball", "Air Balloon", "Cheren", "Battle Cage"},
          f"expected hand to be exactly the 4 searched cards (1 Item, 1 Tool, 1 Supporter, "
          f"1 Stadium), got {hand_names}")
    check(len(a.hand) == 4, f"expected 4 cards found (Item+Tool+Supporter+Stadium), got {len(a.hand)}")
    check(all(c in a.discard for c in (filler1, filler2, filler3)),
          "all 3 original hand cards must be discarded")
    check(len(a.deck) == deck_len_before - 4,
          f"deck should shrink by exactly the 4 found cards, got {len(a.deck)} vs {deck_len_before}")

    # --- 2c. NEGATIVE: fewer than 3 OTHER cards in hand (post-pop) -> no-op, no
    # discard, no search. ---
    st, a, b = fresh_state(db)
    a.hand = [db.get("Ultra Ball"), db.get("Switch")]     # only 2
    a.deck = [db.get("Cheren")]
    ok = fx._secret_box(ctx_for(st, a, b))
    check(not ok, "Secret Box must no-op with fewer than 3 other cards in hand")
    check(len(a.hand) == 2 and len(a.discard) == 0,
          "hand/discard must be untouched on a Secret Box no-op")

    # --- 2d. Deck missing one searchable type (no Stadium available): the search
    # still returns True (the discard already happened) and finds only 3. ---
    st, a, b = fresh_state(db)
    a.hand = [db.get("Ultra Ball"), db.get("Switch"), db.get("Judge")]
    a.deck = [db.get("Ultra Ball"), db.get("Air Balloon"), db.get("Cheren")] + [db.get("Basic Water Energy")] * 3
    ok = fx._secret_box(ctx_for(st, a, b))
    check(ok, "Secret Box must still succeed (discard-3 already happened) even if a type is missing in deck")
    check(len(a.hand) == 3, f"expected only 3 found (no Stadium available), got {len(a.hand)}: {[c.name for c in a.hand]}")
    check(not any(c.is_trainer and "Stadium" in c.subtypes for c in a.hand),
          "no Stadium should be found since none was in the deck")

    # =================================================================== #
    # BRAVE BANGLE (rsv10pt5-80, Pokémon Tool)
    # Pool text: "If the Pokémon this card is attached to doesn't have a Rule
    # Box, the attacks it uses do 30 more damage to your opponent's Active
    # Pokémon ex (before applying Weakness and Resistance)."
    # =================================================================== #

    brave_bangle = db.get("Brave Bangle")
    check(brave_bangle.supertype == "Trainer" and "Pokémon Tool" in brave_bangle.subtypes,
          f"Brave Bangle should be a Trainer Pokémon Tool, got {brave_bangle.subtypes}")
    check("Brave Bangle" in fx.TOOL_IMPLEMENTED, "Brave Bangle must be registered in TOOL_IMPLEMENTED")

    # --- 3a. POSITIVE: non-Rule-Box holder, target is the opponent's Active ex ->
    # +30 damage. Dwebble (Basic, no Rule Box) with Brave Bangle vs Dragapult ex
    # (ex, no printed Weakness) Active. ---
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Dwebble"))
    holder.tool = brave_bangle
    a.active = holder
    target = InPlayPokemon(card=db.get("Dragapult ex"))          # ex, 320 HP, no Weakness
    b.active = target
    dealt = fx.apply_attack_damage(ctx_for(st, a, b), target, 50, owner=b, source=holder)
    check(dealt == 80 and target.damage == 80,
          f"expected 50+30=80 (holder has no Rule Box, target is ex, Active), got {dealt}")

    # --- 3b. NEGATIVE: the holder itself HAS a Rule Box (is a Pokémon ex) -> no
    # bonus, even though the target is a legal (Active, ex) target. ---
    st, a, b = fresh_state(db)
    holder2 = InPlayPokemon(card=db.get("Latias ex"))            # ex holder
    holder2.tool = brave_bangle
    a.active = holder2
    target2 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = target2
    dealt2 = fx.apply_attack_damage(ctx_for(st, a, b), target2, 50, owner=b, source=holder2)
    check(dealt2 == 50, f"holder has a Rule Box (ex) -> no +30 bonus, expected 50, got {dealt2}")

    # --- 3c. NEGATIVE: target is NOT a Pokémon ex (Crustle, plain Stage 1) -> no
    # bonus even though the holder qualifies. ---
    st, a, b = fresh_state(db)
    holder3 = InPlayPokemon(card=db.get("Dwebble"))
    holder3.tool = brave_bangle
    a.active = holder3
    target3 = InPlayPokemon(card=db.get("Crustle"))              # no 'ex' subtype
    b.active = target3
    dealt3 = fx.apply_attack_damage(ctx_for(st, a, b), target3, 50, owner=b, source=holder3)
    check(dealt3 == 50, f"target is not a Pokémon ex -> no +30 bonus, expected 50, got {dealt3}")

    # --- 3d. NEGATIVE: target is a Pokémon ex but on the BENCH (not the Active
    # Spot) -> no bonus (text says "your opponent's Active Pokémon ex"). Uses
    # Latias ex (ex, but NOT Tera) so the separate Tera bench-immunity chokepoint
    # (line ~591) doesn't confound this assertion. ---
    st, a, b = fresh_state(db)
    holder4 = InPlayPokemon(card=db.get("Dwebble"))
    holder4.tool = brave_bangle
    a.active = holder4
    b.active = InPlayPokemon(card=db.get("Dwebble"))
    benched_ex = InPlayPokemon(card=db.get("Latias ex"))          # ex, but NOT Tera
    check("Tera" not in benched_ex.card.subtypes,
          "setup: Latias ex must NOT be Tera-typed (isolates the Active-only check "
          "from the unrelated Tera bench-immunity chokepoint)")
    b.bench = [benched_ex]
    dealt4 = fx.apply_attack_damage(ctx_for(st, a, b), benched_ex, 50, owner=b, source=holder4)
    check(dealt4 == 50, f"a Benched Pokémon ex must NOT get the +30 (Active-only), expected 50, got {dealt4}")

    # --- 3e. NEGATIVE: the attacker has no Brave Bangle attached at all -> no
    # bonus. ---
    st, a, b = fresh_state(db)
    holder5 = InPlayPokemon(card=db.get("Dwebble"))               # no .tool
    a.active = holder5
    target5 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = target5
    dealt5 = fx.apply_attack_damage(ctx_for(st, a, b), target5, 50, owner=b, source=holder5)
    check(dealt5 == 50, f"no Brave Bangle attached -> no bonus, expected 50, got {dealt5}")

    # --- 3f. ORDERING: the +30 is added BEFORE Weakness/Resistance. Staryu
    # (Water, no Rule Box) with Brave Bangle vs Magcargo ex (Fire, ex, Weak Water
    # x2): (50 + 30) * 2 = 160, NOT 50*2 + 30 = 130. ---
    st, a, b = fresh_state(db)
    holder6 = InPlayPokemon(card=db.get("Staryu"))                # Water, no Rule Box
    holder6.tool = brave_bangle
    a.active = holder6
    target6 = InPlayPokemon(card=db.get("Magcargo ex"))           # Fire, ex, Weak Water x2
    b.active = target6
    dealt6 = fx.apply_attack_damage(ctx_for(st, a, b), target6, 50, owner=b, source=holder6)
    check(dealt6 == 160,
          f"expected (50+30)*2=160 (bonus applied BEFORE Weakness), got {dealt6}")

    # =================================================================== #
    # LUCKY HELMET (sv6-158, Pokémon Tool)
    # Pool text: "If the Pokémon this card is attached to is in the Active Spot
    # and is damaged by an attack from your opponent's Pokémon (even if this
    # Pokémon is Knocked Out), draw 2 cards."
    # =================================================================== #

    lucky_helmet = db.get("Lucky Helmet")
    check(lucky_helmet.supertype == "Trainer" and "Pokémon Tool" in lucky_helmet.subtypes,
          f"Lucky Helmet should be a Trainer Pokémon Tool, got {lucky_helmet.subtypes}")
    check("Lucky Helmet" in fx.TOOL_IMPLEMENTED, "Lucky Helmet must be registered in TOOL_IMPLEMENTED")

    # --- 4a. POSITIVE: holder is Active, damaged by an opponent's attack -> its
    # controller draws 2. ---
    st, a, b = fresh_state(db)
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active = attacker
    holder_active = InPlayPokemon(card=db.get("Indeedee"))
    holder_active.tool = lucky_helmet
    b.active = holder_active
    b.deck = [db.get("Basic Fire Energy"), db.get("Basic Water Energy"), db.get("Basic Grass Energy")]
    hand_before = len(b.hand)
    fx.apply_attack_damage(ctx_for(st, a, b), holder_active, 30, owner=b, source=attacker)
    check(len(b.hand) == hand_before + 2,
          f"Lucky Helmet's controller should draw 2 when its Active is hit by an opponent's "
          f"attack, got hand growth of {len(b.hand) - hand_before}")

    # --- 4b. NEGATIVE: holder is on the BENCH (not Active) when hit -> no draw. ---
    st, a, b = fresh_state(db)
    attacker2 = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active = attacker2
    b.active = InPlayPokemon(card=db.get("Crustle"))
    bench_victim = InPlayPokemon(card=db.get("Indeedee"))
    bench_victim.tool = lucky_helmet
    b.bench = [bench_victim]
    b.deck = [db.get("Basic Fire Energy"), db.get("Basic Water Energy")]
    hand_before2 = len(b.hand)
    fx.apply_attack_damage(ctx_for(st, a, b), bench_victim, 50, owner=b, source=attacker2)
    check(len(b.hand) == hand_before2,
          f"Lucky Helmet on a BENCHED holder must NOT draw, got hand growth of "
          f"{len(b.hand) - hand_before2}")

    # --- 4c. NEGATIVE: damage from a FRIENDLY source (same owner as the holder) —
    # the text says "damaged by an attack from YOUR OPPONENT's Pokémon", so a
    # same-side "attacker" must not trigger the draw. ---
    st, a, b = fresh_state(db)
    friendly_holder = InPlayPokemon(card=db.get("Indeedee"))
    friendly_holder.tool = lucky_helmet
    a.active = friendly_holder
    friendly_source = InPlayPokemon(card=db.get("Dwebble"))
    a.bench = [friendly_source]
    b.active = InPlayPokemon(card=db.get("Crustle"))
    a.deck = [db.get("Basic Fire Energy"), db.get("Basic Water Energy")]
    hand_before3 = len(a.hand)
    fx.apply_attack_damage(ctx_for(st, a, b), friendly_holder, 20, owner=a, source=friendly_source)
    check(len(a.hand) == hand_before3,
          f"a same-side 'attacker' must NOT trigger Lucky Helmet's draw, got hand growth of "
          f"{len(a.hand) - hand_before3}")

    # --- 4d. POSITIVE: draws even when the damage KNOCKS OUT the holder ("even if
    # this Pokémon is Knocked Out"). ---
    st, a, b = fresh_state(db)
    attacker3 = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active = attacker3
    lethal_holder = InPlayPokemon(card=db.get("Indeedee"))        # 100 HP
    lethal_holder.tool = lucky_helmet
    b.active = lethal_holder
    b.deck = [db.get("Basic Fire Energy"), db.get("Basic Water Energy")]
    hand_before4 = len(b.hand)
    fx.apply_attack_damage(ctx_for(st, a, b), lethal_holder, 200, owner=b, source=attacker3)
    check(lethal_holder.is_knocked_out, "setup: 200 damage to a 100-HP mon must KO it")
    check(len(b.hand) == hand_before4 + 2,
          f"Lucky Helmet must still draw 2 even on a KO hit, got hand growth of "
          f"{len(b.hand) - hand_before4}")

    # --- 4e. NEGATIVE: no Lucky Helmet attached -> no draw. ---
    st, a, b = fresh_state(db)
    attacker4 = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active = attacker4
    plain_holder = InPlayPokemon(card=db.get("Indeedee"))         # no .tool
    b.active = plain_holder
    b.deck = [db.get("Basic Fire Energy"), db.get("Basic Water Energy")]
    hand_before5 = len(b.hand)
    fx.apply_attack_damage(ctx_for(st, a, b), plain_holder, 20, owner=b, source=attacker4)
    check(len(b.hand) == hand_before5,
          f"no Lucky Helmet attached -> no draw, got hand growth of {len(b.hand) - hand_before5}")

    # --- 4f. Draw caps at the deck size (no crash with <2 cards left). ---
    st, a, b = fresh_state(db)
    attacker5 = InPlayPokemon(card=db.get("Dragapult ex"))
    a.active = attacker5
    thin_deck_holder = InPlayPokemon(card=db.get("Indeedee"))
    thin_deck_holder.tool = lucky_helmet
    b.active = thin_deck_holder
    b.deck = [db.get("Basic Fire Energy")]                        # only 1 card left
    fx.apply_attack_damage(ctx_for(st, a, b), thin_deck_holder, 10, owner=b, source=attacker5)
    check(len(b.hand) == 1 and len(b.deck) == 0,
          f"Lucky Helmet's draw must cap at deck size with no crash, got hand={len(b.hand)} deck={len(b.deck)}")

    # =================================================================== #
    # ACADEMY AT NIGHT (sv6pt5-54, Stadium)
    # Pool text: "Once during each player's turn, that player may put a card
    # from their hand on top of their deck."
    # =================================================================== #

    academy = db.get("Academy at Night")
    check(academy.supertype == "Trainer" and "Stadium" in academy.subtypes,
          f"Academy at Night should be a Trainer Stadium, got {academy.subtypes}")
    # The once-per-turn top-decking effect IS now modeled — an ACTIVATED Stadium
    # action ("stadium_academy", budgeted by stadium_academy_used_this_turn; full
    # behavior covered in tests/test_slowking_annihilape.py). The shared
    # Stadium-zone mechanics are exercised below.
    check("Academy at Night" in fx.STADIUM_IMPLEMENTED,
          "Academy at Night's activated effect is implemented — it must be listed "
          "in STADIUM_IMPLEMENTED")

    # --- 5a. Playable when no Stadium is in play; installs into the zone. ---
    st, a, b = fresh_state(db)
    check(fx.can_play_stadium(st, academy), "Academy at Night should be playable with no Stadium in play")
    a.hand = [academy]
    game.apply_action(st, Action("play_stadium", hand_index=0))
    check(st.stadium is academy and st.stadium_owner == 0,
          "Academy at Night should be installed as the active Stadium, owned by player 0")
    check(academy not in a.hand, "Academy at Night must be popped from hand once played")
    check(a.stadium_played_this_turn, "stadium_played_this_turn should be set")

    # --- 5b. A same-named Stadium can't be played while one is already in play. ---
    check(not fx.can_play_stadium(st, db.get("Academy at Night")),
          "a second copy of Academy at Night must be unplayable while one is already in play")

    # --- 5c. Replaced by a DIFFERENT Stadium: the outgoing one is discarded to
    # whichever player played it. ---
    b.hand = [db.get("Battle Cage")]
    st.active_index = 1
    game.apply_action(st, Action("play_stadium", hand_index=0))
    check(st.stadium.name == "Battle Cage" and st.stadium_owner == 1,
          "Battle Cage should replace Academy at Night as the active Stadium")
    check(academy in a.discard,
          "the outgoing Academy at Night must be discarded to player 0 (who played it)")

    # =================================================================== #
    # N'S PLAN (zsv10pt5-83, Supporter)
    # Pool text: "Move up to 2 Energy from your Benched Pokémon to your Active
    # Pokémon."
    # =================================================================== #

    ns_plan = db.get("N's Plan")
    check(ns_plan.supertype == "Trainer" and "Supporter" in ns_plan.subtypes,
          f"N's Plan should be a Trainer Supporter, got {ns_plan.subtypes}")

    # --- 6a. can_play: False with no Active. ---
    st, a, b = fresh_state(db)
    a.active = None
    a.bench = [InPlayPokemon(card=db.get("Dwebble"))]
    a.bench[0].energy = [db.get("Basic Grass Energy")]
    check(not fx._TRAINER_CAN_PLAY["N's Plan"](st, a),
          "can_play should be False with no Active Pokémon")

    # --- 6b. can_play: False with an Active but no Energy anywhere on the Bench. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Indeedee"))
    a.bench = [InPlayPokemon(card=db.get("Dwebble"))]      # no energy
    check(not fx._TRAINER_CAN_PLAY["N's Plan"](st, a),
          "can_play should be False with no Energy on any Benched Pokémon")

    # --- 6c. POSITIVE + cap: 2 Benched Pokémon; benchA has 1 Energy, benchB has 3.
    # Moves 1 from benchA, then 1 from benchB (LIFO — .pop() takes the last-
    # attached), stopping at the 2-Energy cap. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Indeedee"))
    e_grass = db.get("Basic Grass Energy")
    benchA = InPlayPokemon(card=db.get("Dwebble"))
    benchA.energy = [e_grass]
    e_fire, e_water, e_metal = (db.get("Basic Fire Energy"), db.get("Basic Water Energy"),
                                db.get("Basic Metal Energy"))
    benchB = InPlayPokemon(card=db.get("Crustle"))
    benchB.energy = [e_fire, e_water, e_metal]
    a.bench = [benchA, benchB]
    check(fx._TRAINER_CAN_PLAY["N's Plan"](st, a), "can_play should be True")
    ok = fx._ns_plan(ctx_for(st, a, b))
    check(ok, "N's Plan should report success")
    check(len(a.active.energy) == 2,
          f"expected exactly 2 Energy moved to the Active (the printed cap), got {len(a.active.energy)}")
    check(a.active.energy == [e_grass, e_metal],
          f"expected [grass (benchA's only), metal (benchB's LAST-attached)] moved in that "
          f"order, got {[c.name for c in a.active.energy]}")
    check(benchA.energy == [] and benchB.energy == [e_fire, e_water],
          f"benchA should be fully drained (1 moved) and benchB should keep its first 2 "
          f"Energy (only its last was moved), got benchA={benchA.energy} benchB="
          f"{[c.name for c in benchB.energy]}")

    # --- 6d. NEGATIVE: only 1 Energy total available anywhere -> moves exactly 1,
    # no crash from trying to hit the cap of 2. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Indeedee"))
    lone_mon = InPlayPokemon(card=db.get("Dwebble"))
    lone_energy = db.get("Basic Grass Energy")
    lone_mon.energy = [lone_energy]
    a.bench = [lone_mon]
    ok = fx._ns_plan(ctx_for(st, a, b))
    check(ok, "N's Plan should still report success moving fewer than 2")
    check(a.active.energy == [lone_energy] and lone_mon.energy == [],
          "should move exactly the 1 available Energy with no crash")

    # =================================================================== #
    # BUG CATCHING SET (sv6-143, Item)
    # Pool text: "Look at the top 7 cards of your deck. You may reveal up to 2 in
    # any combination of Grass Pokémon and Basic Grass Energy cards you find
    # there and put them into your hand. Shuffle the other cards back into your
    # deck."
    # =================================================================== #

    bug_catching_set = db.get("Bug Catching Set")
    check(bug_catching_set.supertype == "Trainer" and "Item" in bug_catching_set.subtypes,
          f"Bug Catching Set should be a Trainer Item, got {bug_catching_set.subtypes}")

    # --- 7a. POSITIVE: exactly 2 matches (1 Grass Pokémon + 1 Basic Grass Energy)
    # within the top-7 window; a 3rd match sitting at position 8 (beyond the
    # window) must NOT be found. ---
    st, a, b = fresh_state(db)
    grass_energy = db.get("Basic Grass Energy")
    grass_mon = db.get("Teal Mask Ogerpon")                       # Basic Grass, no Rule Box
    window = [db.get("Indeedee"), grass_energy, db.get("Mr. Mime"),
             grass_mon, db.get("Basic Fire Energy"), db.get("Indeedee"), db.get("Mr. Mime")]
    beyond_window = db.get("Dwebble")                             # Grass Pokémon, position 8
    a.deck = window + [beyond_window]
    deck_len_before = len(a.deck)
    check(fx._TRAINER_CAN_PLAY["Bug Catching Set"](st, a),
          "can_play should be True (a Grass card exists in the deck)")
    ok = fx._bug_catching_set(ctx_for(st, a, b))
    check(ok, "Bug Catching Set should report success")
    hand_names = [c.name for c in a.hand]
    check(sorted(hand_names) == sorted(["Basic Grass Energy", "Teal Mask Ogerpon"]),
          f"expected exactly the Grass Energy + Grass Pokémon from the TOP 7, got {hand_names}")
    check(len(a.deck) == deck_len_before - 2,
          f"deck should shrink by exactly the 2 taken cards, got {len(a.deck)} vs {deck_len_before}")
    check(any(c.name == "Dwebble" for c in a.deck),
          "the Grass Pokémon sitting at position 8 (beyond the top-7 window) must "
          "remain in the deck, NOT be taken")

    # --- 7b. NEGATIVE: no Grass Pokémon / Basic Grass Energy anywhere in the
    # top-7 window -> no-op. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Indeedee"), db.get("Mr. Mime"), db.get("Basic Fire Energy"),
             db.get("Basic Water Energy"), db.get("Indeedee"), db.get("Mr. Mime"),
             db.get("Basic Metal Energy")]
    deck_len_before2 = len(a.deck)
    ok = fx._bug_catching_set(ctx_for(st, a, b))
    check(not ok, "Bug Catching Set should no-op with no Grass matches in the top 7")
    check(len(a.hand) == 0, "hand should be untouched on a no-op")
    check(len(a.deck) == deck_len_before2,
          "deck size should be unchanged (only re-shuffled) on a no-op")

    # =================================================================== #
    # TERA ORB (sv8-189, Item)
    # Pool text: "Search your deck for a Tera Pokémon, reveal it, and put it
    # into your hand. Then, shuffle your deck."
    # =================================================================== #

    tera_orb = db.get("Tera Orb")
    check(tera_orb.supertype == "Trainer" and "Item" in tera_orb.subtypes,
          f"Tera Orb should be a Trainer Item, got {tera_orb.subtypes}")

    # --- 8a. POSITIVE: deck has 1 Tera Pokémon -> found and moved to hand. ---
    st, a, b = fresh_state(db)
    terapagos = db.get("Terapagos ex")
    check("Tera" in terapagos.subtypes, "setup: Terapagos ex must carry the 'Tera' subtype")
    a.deck = [db.get("Indeedee"), terapagos, db.get("Basic Fire Energy")]
    check(fx._TRAINER_CAN_PLAY["Tera Orb"](st, a), "can_play should be True with a Tera Pokémon in deck")
    ok = fx._tera_orb(ctx_for(st, a, b))
    check(ok, "Tera Orb should report success")
    check(len(a.hand) == 1 and a.hand[0].name == "Terapagos ex",
          f"expected Terapagos ex found into hand, got {[c.name for c in a.hand]}")
    check(len(a.deck) == 2, f"deck should shrink by exactly 1, got {len(a.deck)}")

    # --- 8b. NEGATIVE: no Tera Pokémon anywhere in the deck -> can_play False,
    # no-op. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Indeedee"), db.get("Dwebble"), db.get("Basic Fire Energy")]
    check(not fx._TRAINER_CAN_PLAY["Tera Orb"](st, a),
          "can_play should be False with no Tera Pokémon in deck")
    ok = fx._tera_orb(ctx_for(st, a, b))
    check(not ok, "Tera Orb should no-op with no Tera Pokémon in deck")
    check(len(a.hand) == 0, "hand should be untouched on a no-op")

    # --- 8c. Only ONE Tera Pokémon is fetched even when several are in the deck
    # ("a Tera Pokémon", singular). ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Terapagos ex"), db.get("Dragapult ex"), db.get("Indeedee")]
    ok = fx._tera_orb(ctx_for(st, a, b))
    check(ok, "Tera Orb should report success")
    tera_in_hand = [c for c in a.hand if "Tera" in c.subtypes]
    tera_in_deck = [c for c in a.deck if "Tera" in c.subtypes]
    check(len(tera_in_hand) == 1,
          f"expected exactly 1 Tera Pokémon fetched, got {len(tera_in_hand)}: "
          f"{[c.name for c in tera_in_hand]}")
    check(len(tera_in_deck) == 1,
          f"expected exactly 1 Tera Pokémon left behind in the deck, got {len(tera_in_deck)}")

    # =================================================================== #
    # AREA ZERO UNDERDEPTHS (sv7-131, Stadium)
    # Pool text: "Each player who has any Tera Pokémon in play can have up to 8
    # Pokémon on their Bench. If a player no longer has any Tera Pokémon in
    # play, that player discards Pokémon from their Bench until they have 5.
    # When this card leaves play, both players discard Pokémon from their
    # Bench until they have 5, and the player who played this card discards
    # first."
    # =================================================================== #

    area_zero = db.get("Area Zero Underdepths")
    check(area_zero.supertype == "Trainer" and "Stadium" in area_zero.subtypes,
          f"Area Zero Underdepths should be a Trainer Stadium, got {area_zero.subtypes}")
    check("Area Zero Underdepths" in fx.STADIUM_IMPLEMENTED,
          "Area Zero Underdepths is now fully implemented (per-player 8-Bench cap + "
          "both shrink clauses) and must be listed as such")

    # --- 9a. Playable / replaces the prior Stadium (shared Stadium-zone
    # mechanics, same as 5a/5c). ---
    st, a, b = fresh_state(db)
    check(fx.can_play_stadium(st, area_zero), "Area Zero Underdepths should be playable with no Stadium in play")
    a.hand = [area_zero]
    game.apply_action(st, Action("play_stadium", hand_index=0))
    check(st.stadium is area_zero and st.stadium_owner == 0,
          "Area Zero Underdepths should be installed as the active Stadium")
    b.hand = [db.get("Nighttime Mine")]
    st.active_index = 1
    game.apply_action(st, Action("play_stadium", hand_index=0))
    check(st.stadium.name == "Nighttime Mine" and area_zero in a.discard,
          "Area Zero Underdepths should be discarded to player 0 when replaced")

    # --- 9b. WAS a documented limitation, now IMPLEMENTED: with Area Zero
    # Underdepths in play and a Tera Pokémon in play for player A, that player's
    # Bench cap really is 8, so a 6th Pokémon can be searched onto it. (Kept here
    # as a regression guard on the exact case this file used to record as a gap;
    # the full behavior — symmetry, both shrink clauses, discard order — is
    # covered in tests/test_area_zero_underdepths.py.) ---
    st, a, b = fresh_state(db)
    st.stadium = area_zero
    st.stadium_owner = 0
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))          # a Tera Pokémon in play
    check("Tera" in a.active.card.subtypes, "setup: Dragapult ex must be Tera-typed")
    a.bench = [InPlayPokemon(card=db.get("Dwebble")) for _ in range(PlayerState.MAX_BENCH)]
    check(len(a.bench) == 5, "setup: bench pre-filled to the DEFAULT cap of 5")
    a.deck = [db.get("Indeedee")]                                  # a 6th Basic to try to bench
    found = fx.search_deck(ctx_for(st, a, b), [fx.p_basic_pokemon], dest="bench")
    check(found == 1,
          f"with Area Zero Underdepths + a Tera Pokémon in play, this player's Bench cap "
          f"is 8, so a 6th Pokémon must be placeable; expected 1 found, got {found}")
    check(len(a.bench) == 6, f"bench must expand past 5, got {len(a.bench)}")
    check(PlayerState.MAX_BENCH == 5,
          "the MAX_BENCH constant stays 5 — it is now only the DEFAULT; the per-player "
          "rule lives in fx.bench_limit(state, player)")

    # =================================================================== #
    # TELEPATHIC PSYCHIC ENERGY (por-88, Special Energy)
    # Pool text: "As long as this card is attached to a Pokémon, it provides
    # Psychic Energy. When you attach this card from your hand to a Psychic
    # Pokémon, search your deck for up to 2 Basic Psychic Pokémon and put them
    # onto your Bench. Then, shuffle your deck."
    # =================================================================== #

    telepathic = db.get("Telepathic Psychic Energy")
    check(telepathic.supertype == "Energy" and "Special" in telepathic.subtypes,
          f"Telepathic Psychic Energy should be a Special Energy, got {telepathic.subtypes} "
          f"{telepathic.supertype}")
    check(tuple(telepathic.types) == ("Psychic",),
          f"Telepathic Psychic Energy should provide Psychic Energy, got types={telepathic.types}")
    check("Telepathic Psychic Energy" in fx.SPECIAL_ENERGY_IMPLEMENTED,
          "Telepathic Psychic Energy must be registered as an implemented Special Energy")

    # --- 10a. "Provides Psychic Energy": once attached, provided_types() reports
    # Psychic. ---
    holder7 = InPlayPokemon(card=db.get("Indeedee"))
    holder7.energy = [telepathic]
    check(holder7.provided_types() == ["Psychic"],
          f"attached Telepathic Psychic Energy should provide exactly ['Psychic'], got "
          f"{holder7.provided_types()}")

    # --- 10b. POSITIVE: attached from hand to a Psychic Pokémon -> searches up
    # to 2 Basic Psychic Pokémon onto the Bench. ---
    st, a, b = fresh_state(db)
    psychic_holder = InPlayPokemon(card=db.get("Indeedee"))
    a.active = psychic_holder
    a.deck = [db.get("Mr. Mime"), db.get("Dwebble"), db.get("Marill")]
    fx._telepathic_on_attach(ctx_for(st, a, b, source=psychic_holder))
    benched_names = {m.card.name for m in a.bench}
    check("Mr. Mime" in benched_names,
          f"expected Mr. Mime (a Basic Psychic Pokémon) benched, got {benched_names}")
    check(len(a.bench) <= 2, f"expected at most 2 benched, got {len(a.bench)}")

    # --- 10c. NEGATIVE: attached to a NON-Psychic Pokémon -> no search fires. ---
    st, a, b = fresh_state(db)
    fire_holder = InPlayPokemon(card=db.get("Dwebble"))            # Grass, not Psychic
    a.active = fire_holder
    a.deck = [db.get("Mr. Mime"), db.get("Indeedee")]
    fx._telepathic_on_attach(ctx_for(st, a, b, source=fire_holder))
    check(len(a.bench) == 0,
          f"attaching to a non-Psychic Pokémon must NOT trigger the Bench-search, got "
          f"{len(a.bench)} benched")

    # --- 10d. NEGATIVE: Bench already at the (fixed, 5) cap -> no room, no crash,
    # search finds nothing even though qualifying cards exist in the deck. ---
    st, a, b = fresh_state(db)
    full_holder = InPlayPokemon(card=db.get("Indeedee"))
    a.active = full_holder
    a.bench = [InPlayPokemon(card=db.get("Dwebble")) for _ in range(PlayerState.MAX_BENCH)]
    a.deck = [db.get("Mr. Mime")]
    fx._telepathic_on_attach(ctx_for(st, a, b, source=full_holder))
    check(len(a.bench) == 5, "a full Bench must stay at 5 — no crash, no overflow")
    check(any(c.name == "Mr. Mime" for c in a.deck),
          "with no Bench room, the qualifying Pokémon must remain in the deck, unfetched")

    # --- 10e. INTEGRATION: the on-attach hook actually fires through the real
    # engine action, not just when called directly (guards against a wiring
    # regression — "implemented != exercised"). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Indeedee"))
    a.hand = [telepathic]
    a.deck = [db.get("Mr. Mime")]
    game.apply_action(st, Action("attach_energy", hand_index=0, target_index=-1))
    check(a.active.energy == [telepathic], "Telepathic Psychic Energy should be attached to the Active")
    check(any(m.card.name == "Mr. Mime" for m in a.bench),
          "attaching Telepathic Psychic Energy via the real attach_energy action must "
          "still fire the Bench-search on-attach hook")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_slowking_ogerpon_trainers.py: all checks passed (Wondrous Patch, Secret Box, "
          "Brave Bangle, Lucky Helmet, Academy at Night, N's Plan, Bug Catching Set, Tera Orb, "
          "Area Zero Underdepths, Telepathic Psychic Energy)")


if __name__ == "__main__":
    main()
