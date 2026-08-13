#!/usr/bin/env python3
"""
test_gardevoir_real_trainers.py — the Trainer/Stadium cards added for Anar Guliyev's
real Mega Gardevoir list (`gardevoir_real`), each asserted against its exact text:

  Wally's Compassion (MEG 132, Supporter)
      "Heal all damage from 1 of your Mega Evolution Pokémon ex. If you healed any
      damage in this way, put all Energy attached to that Pokémon into your hand."
  Grand Tree (SCR 136, Stadium / ACE SPEC)
      "Once during each player's turn, that player may search their deck for a
      Stage 1 Pokémon that evolves from 1 of their Basic Pokémon and put it onto
      that Pokémon to evolve it. If that Pokémon was evolved in this way, that
      player may search their deck for a Stage 2 Pokémon that evolves from that
      Pokémon and put it onto that Pokémon to evolve it. Then, that player shuffles
      their deck. (Players can't evolve a Basic Pokémon during their first turn or a
      Basic Pokémon that was put into play this turn.)"
  Jamming Tower (TWM 153, Stadium)
      "Pokémon Tools attached to each Pokémon (both yours and your opponent's) have
      no effect."
  Mystery Garden (MEG 122, Stadium)
      "Once during each player's turn, that player may discard an Energy card from
      their hand in order to draw cards until they have as many cards in their hand
      as they have Psychic Pokémon in play."

Run: python3 tests/test_gardevoir_real_trainers.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import legal_actions, apply_action, retreat_cost, start_turn


def fresh_state(db, seed=0):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(seed))
    st.db = db
    st.turn_number = 5
    a.turns_taken = 3
    b.turns_taken = 3
    return st, a, b


def ctx_for(st, me, opp, source=None, kind="trainer"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=st.rng, effect_kind=kind)


def put_stadium(st, name, db, owner=0):
    st.stadium = db.get(name)
    st.stadium_owner = owner


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    psy = lambda: db.get("Basic Psychic Energy")   # noqa: E731

    # ------------------------------------------------------------------ #
    # 0. REGISTRATION
    # ------------------------------------------------------------------ #
    check("Wally's Compassion" in fx.TRAINER_EFFECTS,
          "Wally's Compassion must be in TRAINER_EFFECTS")
    for stadium in ("Grand Tree", "Jamming Tower", "Mystery Garden"):
        check(stadium in fx.STADIUM_IMPLEMENTED,
              f"{stadium} must be recorded in STADIUM_IMPLEMENTED")
        check(stadium not in fx.TRAINER_EFFECTS,
              f"{stadium} is a Stadium handled at engine chokepoints/actions — it must "
              f"NOT be in TRAINER_EFFECTS (that registry is for played-and-discarded "
              f"Trainers)")

    # ------------------------------------------------------------------ #
    # 1. WALLY'S COMPASSION
    # ------------------------------------------------------------------ #
    st, a, b = fresh_state(db)
    mega = InPlayPokemon(card=db.get("Mega Gardevoir ex"))
    mega.damage = 200
    mega.energy = [psy(), psy(), db.get("Prism Energy")]
    a.active = mega
    ok = fx._wallys_compassion(ctx_for(st, a, b))
    check(ok is True, "Wally's Compassion must report that it did something")
    check(mega.damage == 0, f"it heals ALL damage, got {mega.damage} left")
    check(mega.energy == [], "having healed, ALL Energy comes off the Pokémon")
    check(len(a.hand) == 3, f"the Energy goes to HAND (not the discard), got "
                            f"{len(a.hand)} in hand / {len(a.discard)} in discard")
    check(a.discard == [], "NEGATIVE: the Energy must not be discarded")

    # It picks the MOST damaged Mega ex, and leaves everything else alone.
    st, a, b = fresh_state(db)
    m1 = InPlayPokemon(card=db.get("Mega Gardevoir ex"))
    m1.damage = 60
    m1.energy = [psy()]
    m2 = InPlayPokemon(card=db.get("Mega Diancie ex"))
    m2.damage = 200
    m2.energy = [psy(), psy()]
    a.active = m1
    a.bench = [m2]
    fx._wallys_compassion(ctx_for(st, a, b))
    check(m2.damage == 0 and m2.energy == [], "policy: heals the most-damaged Mega ex")
    check(m1.damage == 60 and len(m1.energy) == 1,
          "NEGATIVE: the other Mega ex is untouched — the card heals exactly 1 Pokémon")

    # NEGATIVE: a damaged NON-Mega ex is not a legal target ("1 of your Mega Evolution
    # Pokémon ex"), so the card does nothing and reports False.
    st, a, b = fresh_state(db)
    latias = InPlayPokemon(card=db.get("Latias ex"))     # a plain Pokémon ex
    latias.damage = 150
    latias.energy = [psy()]
    a.active = latias
    check(fx._wallys_compassion(ctx_for(st, a, b)) is False,
          "NEGATIVE: a plain Pokémon ex is not a Mega Evolution Pokémon ex")
    check(latias.damage == 150 and len(latias.energy) == 1,
          "NEGATIVE: nothing may be healed or bounced off a non-Mega ex")

    # NEGATIVE: an UNDAMAGED Mega ex — "if you healed any damage in this way" is
    # conditional, so its Energy must never be stripped.
    st, a, b = fresh_state(db)
    mega = InPlayPokemon(card=db.get("Mega Gardevoir ex"))
    mega.energy = [psy(), psy()]
    a.active = mega
    check(fx._wallys_compassion(ctx_for(st, a, b)) is False,
          "NEGATIVE: with no damage to heal the card does nothing")
    check(len(mega.energy) == 2,
          "NEGATIVE: the Energy-bounce clause is conditional on having healed")

    # And it isn't OFFERED in either of those cases (v0 policy: at least half the
    # Pokémon's max HP in damage, since the heal also disarms it).
    st, a, b = fresh_state(db)
    mega = InPlayPokemon(card=db.get("Mega Gardevoir ex"))    # 360 HP
    a.active = mega
    mega.damage = 0
    check(fx.can_play_trainer(st, a, "Wally's Compassion") is False,
          "NEGATIVE: not offered with an undamaged Mega ex")
    mega.damage = 30
    check(fx.can_play_trainer(st, a, "Wally's Compassion") is False,
          "NEGATIVE: v0 policy — not offered for a chip hit (it would disarm the "
          "attacker to undo 30)")
    mega.damage = 200
    check(fx.can_play_trainer(st, a, "Wally's Compassion") is True,
          "offered once the Mega ex is at or past half its HP in damage")

    # ------------------------------------------------------------------ #
    # 2. GRAND TREE
    # ------------------------------------------------------------------ #
    # Full chain: Ralts -> Kirlia -> Mega Gardevoir ex, all out of the DECK, in one use.
    st, a, b = fresh_state(db)
    ralts = InPlayPokemon(card=db.get("Ralts"))
    a.active = ralts
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [db.get("Kirlia"), db.get("Mega Gardevoir ex"), psy(), psy()]
    put_stadium(st, "Grand Tree", db)
    acts = [x for x in legal_actions(st) if x.kind == "stadium_evolve"]
    check(len(acts) == 1 and acts[0].target_index == -1,
          f"Grand Tree must offer exactly the Active Ralts, got {acts}")
    apply_action(st, acts[0])
    check(a.active.card.name == "Mega Gardevoir ex",
          f"the chain must run Basic -> Stage 1 -> Stage 2, got {a.active.card.name}")
    check([c.name for c in a.active.evolved_from] == ["Ralts", "Kirlia"],
          f"both pre-evolutions must be recorded, got "
          f"{[c.name for c in a.active.evolved_from]}")
    check(not any(c.name in ("Kirlia", "Mega Gardevoir ex") for c in a.deck),
          "both evolution cards must have LEFT the deck")
    check(a.stadium_evolve_used_this_turn is True, "the once-per-turn budget is spent")
    check([x for x in legal_actions(st) if x.kind == "stadium_evolve"] == [],
          "NEGATIVE: 'once during each player's turn' — no second use this turn")

    # Stage 1 only, when no Stage 2 is in the deck (the second step is optional).
    st, a, b = fresh_state(db)
    ralts = InPlayPokemon(card=db.get("Ralts"))
    a.active = ralts
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [db.get("Kirlia"), psy()]
    put_stadium(st, "Grand Tree", db)
    acts = [x for x in legal_actions(st) if x.kind == "stadium_evolve"]
    check(len(acts) == 1, "a Basic with only a Stage 1 available is still a target")
    apply_action(st, acts[0])
    check(a.active.card.name == "Kirlia",
          f"it stops at the Stage 1 when there's no Stage 2, got {a.active.card.name}")

    # NEGATIVE: the two printed timing clauses.
    st, a, b = fresh_state(db)
    a.turns_taken = 1                                   # "during their first turn"
    a.active = InPlayPokemon(card=db.get("Ralts"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [db.get("Kirlia")]
    put_stadium(st, "Grand Tree", db)
    check([x for x in legal_actions(st) if x.kind == "stadium_evolve"] == [],
          "NEGATIVE: can't evolve a Basic during your first turn")

    st, a, b = fresh_state(db)
    mon = InPlayPokemon(card=db.get("Ralts"), played_this_turn=True)
    a.active = mon
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [db.get("Kirlia")]
    put_stadium(st, "Grand Tree", db)
    check([x for x in legal_actions(st) if x.kind == "stadium_evolve"] == [],
          "NEGATIVE: can't evolve a Basic that was put into play this turn")

    # NEGATIVE: it only works off a BASIC ("a Stage 1 Pokémon that evolves from 1 of
    # their Basic Pokémon"), so an in-play Kirlia is not a Grand Tree target.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Kirlia"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [db.get("Mega Gardevoir ex")]
    put_stadium(st, "Grand Tree", db)
    check([x for x in legal_actions(st) if x.kind == "stadium_evolve"] == [],
          "NEGATIVE: the search starts from a BASIC, not from an in-play Stage 1")

    # NEGATIVE: no matching Stage 1 in the deck -> not offered at all.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Ralts"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [psy(), psy()]
    put_stadium(st, "Grand Tree", db)
    check([x for x in legal_actions(st) if x.kind == "stadium_evolve"] == [],
          "NEGATIVE: with no Stage 1 in the deck the action must not be offered")

    # NEGATIVE: no Grand Tree in play -> no such action, ever.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Ralts"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [db.get("Kirlia")]
    check([x for x in legal_actions(st) if x.kind == "stadium_evolve"] == [],
          "NEGATIVE: the action only exists while Grand Tree is the Stadium")

    # Its budget resets on the owner's next turn.
    st, a, b = fresh_state(db)
    a.stadium_evolve_used_this_turn = True
    a.active = InPlayPokemon(card=db.get("Ralts"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.deck = [db.get("Kirlia")]
    put_stadium(st, "Grand Tree", db)
    start_turn(st)
    check(a.stadium_evolve_used_this_turn is False,
          "the Grand Tree budget must reset at the start of the turn")

    # ------------------------------------------------------------------ #
    # 3. JAMMING TOWER
    # ------------------------------------------------------------------ #
    st, a, b = fresh_state(db)
    mon = InPlayPokemon(card=db.get("Snorlax ex"))       # printed retreat 4
    mon.tool = db.get("Air Balloon")
    a.active = mon
    base = db.get("Snorlax ex").retreat_cost
    check(retreat_cost(mon, st, a) == max(0, base - 2),
          "without Jamming Tower, Air Balloon still gives −2 retreat")
    put_stadium(st, "Jamming Tower", db)
    check(fx.tools_disabled(st) is True, "tools_disabled must be True under Jamming Tower")
    check(retreat_cost(mon, st, a) == base,
          f"under Jamming Tower Air Balloon has no effect -> full retreat {base}, got "
          f"{retreat_cost(mon, st, a)}")

    # Max-HP Tools too (Cynthia's Power Weight: +70 HP to a Cynthia's Pokémon).
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    gible.tool = db.get("Cynthia's Power Weight")
    a.active = gible
    fx.refresh_hp_modifiers(st)
    check(gible.hp_modifier == 70, f"without Jamming Tower the Tool gives +70 HP, got "
                                   f"{gible.hp_modifier}")
    put_stadium(st, "Jamming Tower", db)
    fx.refresh_hp_modifiers(st)
    check(gible.hp_modifier == 0,
          f"under Jamming Tower the +70 HP is switched off, got {gible.hp_modifier}")

    # Damage Tools too (Brave Bangle: +30 for a non-Rule-Box holder vs an Active ex).
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Ralts"))         # no Rule Box
    holder.tool = db.get("Brave Bangle")
    a.active = holder
    victim = InPlayPokemon(card=db.get("Snorlax ex"))    # a Pokémon ex
    b.active = victim
    put_stadium(st, "Jamming Tower", db)
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=holder, kind="attack"),
                                   victim, 50, owner=b, source=holder)
    check(dealt == 50,
          f"under Jamming Tower Brave Bangle's +30 is off -> 50, got {dealt}")

    # End-of-turn Tool triggers too (Powerglass).
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Ralts"))
    holder.tool = db.get("Powerglass")
    a.active = holder
    a.discard = [psy()]
    put_stadium(st, "Jamming Tower", db)
    fx.end_of_turn_tools(st, a)
    check(holder.energy == [] and len(a.discard) == 1,
          "under Jamming Tower Powerglass must not attach anything")
    st.stadium = None
    fx.end_of_turn_tools(st, a)
    check(len(holder.energy) == 1,
          "control: with the Stadium gone, Powerglass works again (Tools are not "
          "discarded or destroyed, only switched off)")

    # NEGATIVE: it is not an Ability, so ability suppression is irrelevant, and it does
    # not stop a Tool being ATTACHED — only its effect.
    st, a, b = fresh_state(db)
    mon = InPlayPokemon(card=db.get("Ralts"))
    a.active = mon
    a.hand = [db.get("Air Balloon")]
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    put_stadium(st, "Jamming Tower", db)
    check(any(x.kind == "attach_tool" for x in legal_actions(st)),
          "Jamming Tower must not make a Tool unattachable — it only blanks its effect")

    # ------------------------------------------------------------------ #
    # 4. MYSTERY GARDEN
    # ------------------------------------------------------------------ #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Ralts"))                  # Psychic
    a.bench = [InPlayPokemon(card=db.get("Kirlia")),                # Psychic
               InPlayPokemon(card=db.get("Mega Gardevoir ex")),     # Psychic
               InPlayPokemon(card=db.get("Snorlax ex"))]            # Colorless — not counted
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    check(fx.mystery_garden_target(st, a) == 3,
          f"the hand target is YOUR Psychic Pokémon in play (3 here), got "
          f"{fx.mystery_garden_target(st, a)}")
    a.hand = [psy()]                       # 1 card, and it's the Energy we must discard
    a.deck = [db.get("Ultra Ball"), db.get("Judge"), db.get("Rare Candy"), psy()]
    put_stadium(st, "Mystery Garden", db)
    acts = [x for x in legal_actions(st) if x.kind == "stadium_garden"]
    check(len(acts) == 1, f"Mystery Garden's activated draw must be offered, got {acts}")
    apply_action(st, acts[0])
    check(len(a.hand) == 3,
          f"draw UNTIL the hand equals the Psychic count (3), got {len(a.hand)}")
    check(len(a.discard) == 1 and a.discard[0].is_energy,
          "the cost is discarding an Energy card from hand")
    check(a.stadium_garden_used_this_turn is True, "the once-per-turn budget is spent")
    check([x for x in legal_actions(st) if x.kind == "stadium_garden"] == [],
          "NEGATIVE: 'once during each player's turn' — no second use this turn")

    # NEGATIVE: no Energy in hand -> nothing to pay with.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Ralts"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.hand = [db.get("Ultra Ball")]
    a.deck = [db.get("Judge")] * 5
    put_stadium(st, "Mystery Garden", db)
    check(fx.mystery_garden_playable(st, a) is False,
          "NEGATIVE: with no Energy card in hand the ability can't be paid for")
    check([x for x in legal_actions(st) if x.kind == "stadium_garden"] == [],
          "NEGATIVE: and so it isn't offered")

    # NEGATIVE: a hand already at/above the target draws nothing -> not offered.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Ralts"))          # exactly 1 Psychic in play
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.hand = [psy(), db.get("Ultra Ball"), db.get("Judge")]
    a.deck = [db.get("Judge")] * 5
    put_stadium(st, "Mystery Garden", db)
    check(fx.mystery_garden_playable(st, a) is False,
          "NEGATIVE: a hand already at/over the Psychic-count target draws nothing")

    # NEGATIVE: no Psychic Pokémon in play at all -> target 0, never playable.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Snorlax ex"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.hand = [psy()]
    a.deck = [db.get("Judge")] * 5
    put_stadium(st, "Mystery Garden", db)
    check(fx.mystery_garden_target(st, a) == 0,
          "NEGATIVE: no Psychic Pokémon in play -> a hand target of 0")
    check([x for x in legal_actions(st) if x.kind == "stadium_garden"] == [],
          "NEGATIVE: and so the action isn't offered")

    # NEGATIVE: it's the STADIUM's ability — no Mystery Garden, no action.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Ralts"))
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    a.hand = [psy()]
    a.deck = [db.get("Judge")] * 5
    check([x for x in legal_actions(st) if x.kind == "stadium_garden"] == [],
          "NEGATIVE: without Mystery Garden in play the action must not exist")

    # BOTH players get their own use ("each player's turn"), on their own budget.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Ralts"))
    b.active = InPlayPokemon(card=db.get("Ralts"))
    b.bench = [InPlayPokemon(card=db.get("Kirlia"))]
    a.hand = [psy()]
    b.hand = [psy()]
    a.deck = [db.get("Judge")] * 5
    b.deck = [db.get("Judge")] * 5
    put_stadium(st, "Mystery Garden", db, owner=0)     # A played it
    st.active_index = 1                                 # ...but it's B's turn
    check(len([x for x in legal_actions(st) if x.kind == "stadium_garden"]) == 1,
          "the opponent gets the Stadium's once-per-turn use too")

    if fails:
        print(f"test_gardevoir_real_trainers.py: {len(fails)} FAILURE(S)")
        for f in fails:
            print("  -", f)
        return 1
    print("test_gardevoir_real_trainers.py: all checks passed — Wally's Compassion, "
          "Grand Tree, Jamming Tower and Mystery Garden match their card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
