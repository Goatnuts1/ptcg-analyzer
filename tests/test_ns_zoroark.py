#!/usr/bin/env python3
"""
test_ns_zoroark.py — the N's Zoroark ex archetype (Öjvind Svinhufvud, World
Championships 2026, 9th place) and every engine piece the §NS-ZOROARK-2026-09
build added.

CARD TEXT SOURCE for every assertion below: limitlesstcg card pages fetched
during the build (limitlesstcg.com/cards/<SET>/<NUM>), with N's Zoroark ex
additionally cross-checked against Bulbapedia. Quoted inline so a future reader
can re-verify without re-fetching.

  N's Zoroark ex (JTG 98)  Ability "Trade": "You must discard a card from your
        hand in order to use this Ability. Once during your turn, you may draw
        2 cards."
        [D][D] "Night Joker": "Choose 1 of your Benched N's Pokémon's attacks
        and use it as this attack."   <- NOT a discard-pile copy.
  N's Zekrom (ASC 155)  [C][C][C] "Shred" 70: "This attack's damage isn't
        affected by any effects on your opponent's Active Pokémon."
        [R][L][L][C] "Rampaging Thunder" 250: "During your next turn, this
        Pokémon can't use attacks."
  N's Darmanitan (JTG 27)  [C][C] "Back Draft" 30x: "This attack does 30 damage
        for each Basic Energy card in your opponent's discard pile."
        [R][R][C] "Flamebody Cannon" 90: "Discard all Energy from this Pokémon,
        and this attack also does 90 damage to 1 of your opponent's Benched
        Pokémon. (Don't apply Weakness and Resistance for Benched Pokémon.)"
  Pecharunt ex (SFA 39)  Ability "Subjugating Chains": "Once during your turn,
        you may switch 1 of your Benched [D] Pokémon, except any Pecharunt ex,
        with your Active Pokémon. If you do, the new Active Pokémon is now
        Poisoned. You can't use more than 1 Subjugating Chains Ability each
        turn."
        [D][D] "Irritated Outburst" 60x: "This attack does 60 damage for each
        Prize card your opponent has taken."
  Black Belt's Training (JTG 143, Supporter): "During this turn, attacks used by
        your Pokémon do 40 more damage to your opponent's Active Pokémon ex
        (before applying Weakness and Resistance)."
  Transformation Tome (CRI 83, Item): "You must play 2 Transformation Tome cards
        at once. (This effect works one time for 2 cards.) Choose a Basic
        Pokémon in your discard pile and switch it with 1 of your Basic Pokémon
        in play. Any attached cards, damage counters, Special Conditions, turns
        in play, and any other effects remain on the new Pokémon."
  N's PP Up (JTG 153, Item): "Attach a Basic Energy card from your discard pile
        to 1 of your Benched N's Pokémon."
  Binding Mochi (PRE 95, Tool): "Attacks used by the Poisoned Pokémon this card
        is attached to do 40 more damage to your opponent's Active Pokémon
        (before applying Weakness and Resistance)."
  N's Castle (JTG 152, Stadium): "N's Pokémon in play (both yours and your
        opponent's) have no Retreat Cost."

Every effect gets at least one NEGATIVE case.
Run: python3 tests/test_ns_zoroark.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game, effects as fx
from src.engine.decks import load_deck
from src.engine.game import Action
from src.engine.mcts import _semantic_key, _deduped_legal

db = CardDB.from_pool()
fails = 0


def check(c, m):
    global fails
    print(("  ok  " if c else "  FAIL") + " " + m)
    if not c:
        fails += 1


def mk(name):
    return db.get(name)


def blank_state(a_active, b_active):
    a = PlayerState(name="A", deck=[mk("Basic Darkness Energy")] * 20,
                    active=InPlayPokemon(card=mk(a_active)))
    b = PlayerState(name="B", deck=[mk("Basic Darkness Energy")] * 20,
                    active=InPlayPokemon(card=mk(b_active)))
    st = GameState(players=[a, b], db=db, rng=random.Random(7))
    st.phase = Phase.MAIN
    a.prizes = [mk("Basic Darkness Energy")] * 6
    b.prizes = [mk("Basic Darkness Energy")] * 6
    return st, a, b


def ctx_for(st, a, b, src=None, kind="attack", copy_choice=None):
    return fx.EffectContext(state=st, me=a, opp=b, source=src, db=db,
                            rng=st.rng, effect_kind=kind, copy_choice=copy_choice)


# --------------------------------------------------------------------------- #
print("== card text matches the primary source we coded against ==")
z = mk("N's Zoroark ex")
nj = next(a for a in z.attacks if a.name == "Night Joker")
check(nj.text == "Choose 1 of your Benched N's Pokémon's attacks and use it as this attack.",
      "Night Joker text is the Bench-copy wording (NOT a discard-pile copy)")
check([e for e in nj.cost] == ["Darkness", "Darkness"], "Night Joker costs [D][D]")
check(nj.damage == 0, "Night Joker has no printed damage of its own")
trade = next(a for a in z.abilities if a.name == "Trade")
check("You must discard a card from your hand" in trade.text
      and "you may draw 2 cards" in trade.text, "Trade text is discard-then-draw-2")
check("more than 1 Trade" not in trade.text,
      "Trade has NO once-across-copies clause -> every Zoroark gets its own use")

print("\n== deck registration ==")
deck = load_deck(db, "ns_zoroark")
check(len(deck) == 60, "ns_zoroark is exactly 60 cards")
for name, qty in [("N's Zoroark ex", 4), ("N's Zorua", 4), ("N's Zekrom", 2),
                  ("Transformation Tome", 4), ("N's PP Up", 3), ("Binding Mochi", 2),
                  ("N's Castle", 2), ("Pecharunt ex", 1), ("Black Belt's Training", 1),
                  ("Basic Darkness Energy", 8)]:
    check(sum(1 for c in deck if c.name == name) == qty, f"{qty}x {name}")

print("\n== p_ns_pokemon ==")
check(fx.p_ns_pokemon(mk("N's Zorua")) and fx.p_ns_pokemon(mk("N's Zekrom")),
      "N's Zorua / N's Zekrom are N's Pokémon")
check(not fx.p_ns_pokemon(mk("Munkidori")), "NEGATIVE: Munkidori is not an N's Pokémon")
check(not fx.p_ns_pokemon(mk("N's Castle")),
      "NEGATIVE: N's Castle is a Stadium, not an N's Pokémon")

# --------------------------------------------------------------------------- #
print("\n== Night Joker: 'Choose 1 of your Benched N's Pokémon's attacks' ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.bench.append(InPlayPokemon(card=mk("N's Zekrom")))       # bench 0
a.bench.append(InPlayPokemon(card=mk("N's Zorua")))        # bench 1
opts = fx.copy_attack_options(st, a, a.active, nj)
check(opts is not None, "Night Joker is registered as a copy-attack")
# N's Zekrom has 2 attacks, N's Zorua has 1 -> 3 options
check(sorted(opts) == [(0, 0), (0, 1), (1, 0)],
      f"enumerates every Benched N's attack: {sorted(opts)}")

# the copy IGNORES the copied attack's cost: Rampaging Thunder is [R][L][L][C]
# and Zoroark pays only Night Joker's [D][D].
a.active.energy = [mk("Basic Darkness Energy")] * 2
rt_i = next(i for i, atk in enumerate(mk("N's Zekrom").attacks)
            if atk.name == "Rampaging Thunder")
ctx = ctx_for(st, a, b, a.active, copy_choice=(0, rt_i))
fx._night_joker(ctx)
check(b.active.damage == 250,
      f"copied Rampaging Thunder dealt its full 250 off a [D][D] cost (got {b.active.damage})")
check(a.active.pending_cannot_attack,
      "the copied attack's rider lands on the COPIER (Zoroark can't attack next turn)")
check(not a.bench[0].pending_cannot_attack,
      "NEGATIVE: the Benched N's Zekrom it was copied from is unaffected")

# NEGATIVE: no Benched N's Pokémon -> the attack does nothing at all
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.bench.append(InPlayPokemon(card=mk("Munkidori")))
check(fx.copy_attack_options(st, a, a.active, nj) == [],
      "NEGATIVE: a non-N's Bench offers zero copy options")
before = b.active.damage
fx._night_joker(ctx_for(st, a, b, a.active, copy_choice=None))
check(b.active.damage == before, "NEGATIVE: Night Joker with nothing to copy deals 0")

# NEGATIVE: Night Joker never offers ITSELF (infinite recursion guard)
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.bench.append(InPlayPokemon(card=mk("N's Zoroark ex")))
check(fx.copy_attack_options(st, a, a.active, nj) == [],
      "NEGATIVE: a Benched N's Zoroark ex's own Night Joker is not a copy target")

# --------------------------------------------------------------------------- #
print("\n== Trade: discard a card, then draw 2 ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.hand = [mk("Basic Darkness Energy"), mk("Ultra Ball"), mk("Boss's Orders")]
a.deck = [mk("N's Zorua")] * 5
fx._trade(ctx_for(st, a, b, a.active, kind="ability"))
check(len(a.discard) == 1, "exactly 1 card was discarded (the cost)")
check(len(a.hand) == 3 - 1 + 2, f"hand went 3 -> 4 (paid 1, drew 2), got {len(a.hand)}")
check(len(a.deck) == 3, "2 cards left the deck")
# NEGATIVE: the discard is a COST, so an empty hand blocks the Ability entirely
guard = fx.get_ability_can_use("N's Zoroark ex", "Trade")
a2 = PlayerState(name="A", deck=[mk("N's Zorua")] * 5, hand=[])
check(not guard(st, a2, a.active), "NEGATIVE: empty hand -> Trade is not usable")
a3 = PlayerState(name="A", deck=[], hand=[mk("Ultra Ball")])
check(not guard(st, a3, a.active), "NEGATIVE: empty deck -> Trade is not usable")
# the payload-protection policy: never bin an N's Pokémon better than the Bench
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.bench.append(InPlayPokemon(card=mk("N's Zorua")))     # Bench best = Scratch, 20
a.hand = [mk("N's Zekrom"), mk("Basic Darkness Energy")]
a.deck = [mk("N's Zorua")] * 5
fx._trade(ctx_for(st, a, b, a.active, kind="ability"))
check(all(c.name != "N's Zekrom" for c in a.discard),
      "Trade protects the Night Joker payload (discarded the Energy, kept N's Zekrom)")

# --------------------------------------------------------------------------- #
print("\n== N's Zekrom ==")
# Shred: "damage isn't affected by any effects on your opponent's Active"
st, a, b = blank_state("N's Zekrom", "Mega Excadrill ex")
b.active.shielded = True
fx._shred(ctx_for(st, a, b, a.active))
check(b.active.damage == 70, f"Shred's 70 goes through a shield (got {b.active.damage})")
check(("N's Zekrom", "Shred") in fx.ATTACK_EFFECT_OWNS_DAMAGE,
      "Shred owns its damage so the engine doesn't also apply the printed 70")
# NEGATIVE: a normal attack IS stopped by the same shield
st, a, b = blank_state("N's Zekrom", "Mega Excadrill ex")
b.active.shielded = True
fx.apply_attack_damage(ctx_for(st, a, b, a.active), b.active, 70, owner=b, source=a.active)
check(b.active.damage == 0, "NEGATIVE: an ordinary 70 is fully blocked by the shield")

# Rampaging Thunder: only the rider (the 250 is engine-applied)
st, a, b = blank_state("N's Zekrom", "Mega Excadrill ex")
fx._rampaging_thunder(ctx_for(st, a, b, a.active))
check(a.active.pending_cannot_attack, "Rampaging Thunder arms the self-lock")
check(b.active.damage == 0, "NEGATIVE: the effect itself adds no damage (engine owns the 250)")

# --------------------------------------------------------------------------- #
print("\n== N's Darmanitan ==")
# Back Draft: 30 per BASIC Energy card in the OPPONENT's discard.
# Defender is Dragapult ex (NO Weakness) so the scaling is read clean — Mega
# Excadrill ex is Metal and weak to Fire ×2, which would double the whole total.
st, a, b = blank_state("N's Darmanitan", "Dragapult ex")
b.discard = [mk("Basic Darkness Energy")] * 3 + [mk("Ultra Ball")]
fx._back_draft(ctx_for(st, a, b, a.active))
check(b.active.damage == 90, f"3 Basic Energy in opp discard -> 90 (got {b.active.damage})")
# and Weakness multiplies the SCALED TOTAL exactly once (not the printed 30)
st, a, b = blank_state("N's Darmanitan", "Mega Excadrill ex")   # Metal, weak to Fire ×2
b.discard = [mk("Basic Darkness Energy")] * 3
fx._back_draft(ctx_for(st, a, b, a.active))
check(b.active.damage == 180, f"×2 Fire Weakness applies once to the 90 (got {b.active.damage})")
# NEGATIVE: non-Energy cards don't count, and an empty discard is 0
st, a, b = blank_state("N's Darmanitan", "Dragapult ex")
b.discard = [mk("Ultra Ball"), mk("Boss's Orders")]
fx._back_draft(ctx_for(st, a, b, a.active))
check(b.active.damage == 0, "NEGATIVE: Trainers in the discard add nothing")
# NEGATIVE: it reads the OPPONENT's discard, not our own
st, a, b = blank_state("N's Darmanitan", "Dragapult ex")
a.discard = [mk("Basic Darkness Energy")] * 4
fx._back_draft(ctx_for(st, a, b, a.active))
check(b.active.damage == 0, "NEGATIVE: our own discard pile is not counted")

# Flamebody Cannon: discard all our Energy + 90 to a Benched Pokémon
st, a, b = blank_state("N's Darmanitan", "Mega Excadrill ex")
a.active.energy = [mk("Basic Darkness Energy")] * 3
b.bench.append(InPlayPokemon(card=mk("Munkidori")))
fx._flamebody_cannon(ctx_for(st, a, b, a.active))
check(a.active.energy_count() == 0 and len(a.discard) == 3,
      "Flamebody Cannon discarded ALL Energy from the attacker")
check(b.bench[0].damage == 90, f"90 to a Benched Pokémon (got {b.bench[0].damage})")
check(b.active.damage == 0, "NEGATIVE: the effect adds nothing to the Active (engine owns the 90)")
# NEGATIVE: an empty opposing Bench means no second hit, and the Energy still goes
st, a, b = blank_state("N's Darmanitan", "Mega Excadrill ex")
a.active.energy = [mk("Basic Darkness Energy")] * 2
fx._flamebody_cannon(ctx_for(st, a, b, a.active))
check(a.active.energy_count() == 0, "NEGATIVE: Energy is discarded even with no Bench target")

# --------------------------------------------------------------------------- #
print("\n== Pecharunt ex ==")
# Irritated Outburst: 60 per prize the OPPONENT has taken
st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex")
b.prizes = [mk("Basic Darkness Energy")] * 4          # opponent has taken 2
fx._irritated_outburst(ctx_for(st, a, b, a.active))
check(b.active.damage == 120, f"2 prizes taken -> 120 (got {b.active.damage})")
# NEGATIVE: nobody has scored yet -> 0
st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex")
fx._irritated_outburst(ctx_for(st, a, b, a.active))
check(b.active.damage == 0, "NEGATIVE: opponent on 6 prizes -> 0 damage")
# NEGATIVE: it counts the OPPONENT's taken prizes, not ours
st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex")
a.prizes = [mk("Basic Darkness Energy")] * 1          # WE have taken 5
fx._irritated_outburst(ctx_for(st, a, b, a.active))
check(b.active.damage == 0, "NEGATIVE: our own taken prizes don't count")

# Subjugating Chains: switch a Benched [D] (never a Pecharunt ex) up, and Poison it
st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex")
a.bench.append(InPlayPokemon(card=mk("Pecharunt ex")))      # excluded by name
a.bench.append(InPlayPokemon(card=mk("N's Zoroark ex")))    # Darkness, legal
fx._subjugating_chains(ctx_for(st, a, b, a.active, kind="ability"))
check(a.active.card.name == "N's Zoroark ex", "promoted the Benched Darkness Pokémon")
check(a.active.poisoned, "the new Active is now Poisoned")
check(any(m.card.name == "Pecharunt ex" for m in a.bench),
      "the old Active went to the Bench")
# NEGATIVE: "except any Pecharunt ex" — a Bench of only Pecharunt ex can't be used
st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex")
a.bench.append(InPlayPokemon(card=mk("Pecharunt ex")))
fx._subjugating_chains(ctx_for(st, a, b, a.active, kind="ability"))
check(a.active.card.name == "Pecharunt ex" and not a.active.poisoned,
      "NEGATIVE: another Pecharunt ex is not a legal switch target")
# NEGATIVE: a non-Darkness Benched Pokémon is not a legal target either
st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex")
a.bench.append(InPlayPokemon(card=mk("Munkidori")))         # Psychic in this pool
fx._subjugating_chains(ctx_for(st, a, b, a.active, kind="ability"))
check(a.active.card.name == "Pecharunt ex", "NEGATIVE: a non-[D] Benched Pokémon is skipped")

# --------------------------------------------------------------------------- #
print("\n== Poison (new Special Condition) ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.active.poisoned = True
fx.pokemon_checkup(st)
check(a.active.damage == 10, f"Poison puts 1 damage counter at Checkup (got {a.active.damage})")
fx.pokemon_checkup(st)
check(a.active.damage == 20, "and again on the next Checkup")
# NEGATIVE: an un-Poisoned Pokémon takes nothing
check(b.active.damage == 0, "NEGATIVE: the un-Poisoned Active takes no Checkup damage")
# Poison clears when the Pokémon leaves the Active Spot (same as Confusion)
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.active.poisoned = True
a.active.energy = [mk("Basic Darkness Energy")] * 3
a.bench.append(InPlayPokemon(card=mk("N's Zorua")))
game.apply_action(st, Action("retreat", target_index=0))
check(not a.bench[-1].poisoned, "NEGATIVE: retreating clears Poison off the Active Spot")
check(a.active.card.name == "N's Zorua" and not a.active.poisoned,
      "NEGATIVE: the incoming Pokémon is not Poisoned")

# --------------------------------------------------------------------------- #
print("\n== Binding Mochi: +40 only while the holder is Poisoned ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.active.tool = mk("Binding Mochi")
a.active.poisoned = True
fx.apply_attack_damage(ctx_for(st, a, b, a.active), b.active, 100, owner=b, source=a.active)
check(b.active.damage == 140, f"Poisoned Mochi holder: 100 -> 140 (got {b.active.damage})")
# NEGATIVE: same board, holder NOT Poisoned
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.active.tool = mk("Binding Mochi")
fx.apply_attack_damage(ctx_for(st, a, b, a.active), b.active, 100, owner=b, source=a.active)
check(b.active.damage == 100, "NEGATIVE: un-Poisoned holder gets no bonus")
# NEGATIVE: the bonus is Active-only — a Benched target gets nothing
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.active.tool = mk("Binding Mochi")
a.active.poisoned = True
b.bench.append(InPlayPokemon(card=mk("Munkidori")))
fx.apply_attack_damage(ctx_for(st, a, b, a.active), b.bench[0], 100, owner=b, source=a.active)
check(b.bench[0].damage == 100, "NEGATIVE: a Benched target gets no Mochi bonus")
# NEGATIVE: Jamming Tower switches every Tool off
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.active.tool = mk("Binding Mochi")
a.active.poisoned = True
st.stadium = mk("Jamming Tower")
st.stadium_owner = 1
fx.apply_attack_damage(ctx_for(st, a, b, a.active), b.active, 100, owner=b, source=a.active)
check(b.active.damage == 100, "NEGATIVE: Jamming Tower blanks Binding Mochi")

# --------------------------------------------------------------------------- #
print("\n== N's Castle: N's Pokémon have no Retreat Cost (BOTH players) ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
base = mk("N's Zoroark ex").retreat_cost
check(base == 2, f"N's Zoroark ex prints a retreat cost of 2 (got {base})")
check(game.retreat_cost(a.active, st, a) == 2, "no Stadium -> the printed cost stands")
st.stadium = mk("N's Castle")
st.stadium_owner = 1                     # the OPPONENT played it — still symmetric
check(game.retreat_cost(a.active, st, a) == 0, "under N's Castle an N's Pokémon retreats free")
check(game.retreat_cost(b.active, st, b) == mk("Mega Excadrill ex").retreat_cost,
      "NEGATIVE: a non-N's Pokémon keeps its printed retreat cost")

# --------------------------------------------------------------------------- #
print("\n== Black Belt's Training: +40 vs the opponent's Active ex ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
check(fx.can_play_trainer(st, a, "Black Belt's Training"),
      "playable while the opponent's Active is a Pokémon ex")
fx._black_belts_training(ctx_for(st, a, b, kind="trainer"))
fx.apply_attack_damage(ctx_for(st, a, b, a.active), b.active, 100, owner=b, source=a.active)
check(b.active.damage == 140, f"100 -> 140 vs an Active ex (got {b.active.damage})")
# NEGATIVE: a non-ex Active is not a legal target and gets no bonus
st, a, b = blank_state("N's Zoroark ex", "Munkidori")
st.active_index = 0
check(not fx.can_play_trainer(st, a, "Black Belt's Training"),
      "NEGATIVE: not playable when the opponent's Active is not a Pokémon ex")
check(fx._black_belts_training(ctx_for(st, a, b, kind="trainer")) is False,
      "NEGATIVE: the effect reports 'did nothing' so the card returns to hand")
# NEGATIVE: it is Active-only, never a Benched ex
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
fx._black_belts_training(ctx_for(st, a, b, kind="trainer"))
b.bench.append(InPlayPokemon(card=mk("Pecharunt ex")))
fx.apply_attack_damage(ctx_for(st, a, b, a.active), b.bench[0], 100, owner=b, source=a.active)
check(b.bench[0].damage == 100, "NEGATIVE: a Benched ex gets no Black Belt's bonus")

# --------------------------------------------------------------------------- #
print("\n== Transformation Tome: 2 cards, 1 effect, attachments stay ==")
st, a, b = blank_state("N's Zorua", "Mega Excadrill ex")
st.active_index = 0
a.hand = [mk("Transformation Tome"), mk("Transformation Tome")]
a.discard = [mk("N's Zekrom")]
check(fx.can_play_trainer(st, a, "Transformation Tome"),
      "playable with 2 copies in hand + a Basic in discard + a Basic in play")
a.hand = [mk("Transformation Tome")]          # engine already popped the first copy
a.active.damage = 30
a.active.energy = [mk("Basic Darkness Energy")] * 2
a.active.poisoned = True
did = fx._transformation_tome(ctx_for(st, a, b, kind="trainer"))
check(did is True, "the swap resolved")
check(a.active.card.name == "N's Zekrom", "the discard's Basic is now in play")
check(a.active.damage == 30, "damage counters REMAIN on the new Pokémon")
check(a.active.energy_count() == 2, "attached cards REMAIN on the new Pokémon")
check(a.active.poisoned, "Special Conditions REMAIN on the new Pokémon")
check(any(c.name == "N's Zorua" for c in a.discard), "the old Basic went to the discard")
check(sum(1 for c in a.discard if c.name == "Transformation Tome") == 1
      and not a.hand, "the mandatory SECOND Tome was paid out of hand")
# NEGATIVE: only 1 copy in hand -> not playable ("You must play 2 ... at once")
st, a, b = blank_state("N's Zorua", "Mega Excadrill ex")
st.active_index = 0
a.hand = [mk("Transformation Tome")]
a.discard = [mk("N's Zekrom")]
check(not fx.can_play_trainer(st, a, "Transformation Tome"),
      "NEGATIVE: a single Transformation Tome cannot be played")
# NEGATIVE: nothing Basic in the discard -> not playable
st, a, b = blank_state("N's Zorua", "Mega Excadrill ex")
st.active_index = 0
a.hand = [mk("Transformation Tome")] * 2
a.discard = [mk("Ultra Ball")]
check(not fx.can_play_trainer(st, a, "Transformation Tome"),
      "NEGATIVE: no Basic Pokémon in the discard -> not playable")
# NEGATIVE: it must never Knock Out our own Pokémon on arrival
st, a, b = blank_state("N's Zekrom", "Mega Excadrill ex")
st.active_index = 0
a.hand = [mk("Transformation Tome")]
a.discard = [mk("N's Zorua")]            # 70 HP
a.active.damage = 120                    # would be dead as a Zorua
check(fx._transformation_tome(ctx_for(st, a, b, kind="trainer")) is False,
      "NEGATIVE: refuses a swap that would KO our own Pokémon")

# --------------------------------------------------------------------------- #
print("\n== N's PP Up: Basic Energy from discard onto a BENCHED N's Pokémon ==")
st, a, b = blank_state("Munkidori", "Mega Excadrill ex")
st.active_index = 0
a.discard = [mk("Basic Darkness Energy")]
a.bench.append(InPlayPokemon(card=mk("N's Zoroark ex")))
check(fx.can_play_trainer(st, a, "N's PP Up"), "playable with Energy in discard + Benched N's")
check(fx._ns_pp_up(ctx_for(st, a, b, kind="trainer")) is True, "the attach resolved")
check(a.bench[0].energy_count() == 1, "the Benched N's Pokémon got the Energy")
check(not a.discard, "the Energy left the discard pile")
# concentrate, don't spread: the Zoroark already on 1 gets the next one
st, a, b = blank_state("Munkidori", "Mega Excadrill ex")
a.discard = [mk("Basic Darkness Energy")]
a.bench.append(InPlayPokemon(card=mk("N's Zoroark ex")))                       # 0 Energy
one = InPlayPokemon(card=mk("N's Zoroark ex"), energy=[mk("Basic Darkness Energy")])
a.bench.append(one)                                                            # 1 Energy
fx._ns_pp_up(ctx_for(st, a, b, kind="trainer"))
check(one.energy_count() == 2 and a.bench[0].energy_count() == 0,
      "completes the Zoroark closest to [D][D] instead of spreading")
# NEGATIVE: the ACTIVE N's Pokémon is never a legal target ("Benched")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
st.active_index = 0
a.discard = [mk("Basic Darkness Energy")]
check(not fx.can_play_trainer(st, a, "N's PP Up"),
      "NEGATIVE: an Active N's Zoroark ex with an empty Bench -> not playable")
check(fx._ns_pp_up(ctx_for(st, a, b, kind="trainer")) is False,
      "NEGATIVE: the effect refuses to fuel the Active")
# NEGATIVE: a Benched NON-N's Pokémon is not a target
st, a, b = blank_state("Munkidori", "Mega Excadrill ex")
st.active_index = 0
a.discard = [mk("Basic Darkness Energy")]
a.bench.append(InPlayPokemon(card=mk("Munkidori")))
check(not fx.can_play_trainer(st, a, "N's PP Up"),
      "NEGATIVE: a Bench with no N's Pokémon -> not playable")
# NEGATIVE: only BASIC Energy, never a Special Energy
st, a, b = blank_state("Munkidori", "Mega Excadrill ex")
st.active_index = 0
a.discard = [mk("Legacy Energy")]
a.bench.append(InPlayPokemon(card=mk("N's Zoroark ex")))
check(not fx.can_play_trainer(st, a, "N's PP Up"),
      "NEGATIVE: a Special Energy in the discard doesn't enable N's PP Up")

# --------------------------------------------------------------------------- #
print("\n== MCTS: the copy choice is a DISTINCT searchable decision ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
st.active_index = 0
st.turn_number = 4
a.active.energy = [mk("Basic Darkness Energy")] * 2
a.bench.append(InPlayPokemon(card=mk("N's Zekrom")))
acts = [x for x in game.legal_actions(st) if x.kind == "attack"]
check(len(acts) == 2, f"both N's Zekrom attacks are enumerated as actions (got {len(acts)})")
keys = {_semantic_key(st, x) for x in acts}
check(len(keys) == 2, "the two copy choices get DIFFERENT semantic keys (neither vanishes)")
check(all(k[0] == "attack" for k in keys), "and both keys still start with their kind")
dedup = _deduped_legal(st)
check(sum(1 for k in dedup if k[0] == "attack") == 2,
      "_deduped_legal keeps both copy options")
# NEGATIVE: an ordinary attack still produces exactly one action and an all-int key
st, a, b = blank_state("N's Zekrom", "Mega Excadrill ex")
st.active_index = 0
st.turn_number = 4
a.active.energy = [mk("Basic Darkness Energy")] * 3
ord_acts = [x for x in game.legal_actions(st) if x.kind == "attack"]
check(len(ord_acts) == 1 and ord_acts[0].copy_attack_index is None,
      "NEGATIVE: an ordinary attack carries no copy index")
check(_semantic_key(st, ord_acts[0]) == ("attack", 0, -1, -1),
      "NEGATIVE: ordinary attack keys use -1 sentinels, never None")

# --------------------------------------------------------------------------- #
print("\n== live fire: the archetype's effects actually fire in real games ==")
import re
from src.engine.agents import GreedyAgent
seen = set()
for seed in range(12):
    st = game.setup_game(load_deck(db, "ns_zoroark"), load_deck(db, "dragapult"),
                         seed=seed, db=db)
    game.start_turn(st)
    ag = GreedyAgent(random.Random(seed))
    guard = 0
    while st.phase != Phase.GAME_OVER and st.turn_number < 60 and guard < 3000:
        guard += 1
        if st.phase == Phase.MAIN:
            act = ag.choose(st)
            game.apply_action(st, act)
            if act.kind in ("attack", "pass"):
                st.phase = Phase.BETWEEN_TURNS
        if st.phase == Phase.BETWEEN_TURNS:
            game.end_turn(st)
            if not game.start_turn(st):
                break
    for line in st.log:
        for token in ("Night Joker", "Trade:", "N's PP Up", "Transformation Tome",
                      "Black Belt's Training", "Poison:", "Subjugating Chains"):
            if token in line:
                seen.add(token)
        # NOTE the possessive trap CLAUDE.md flags for the log importer: card names
        # themselves contain "'s" ("N's Zekrom"), so anchor on the LAST "'s " in the
        # line, not the first — a lazy `.+?'s` splits "N" off and reports the attack
        # as "Zekrom's Rampaging Thunder".
        m = re.search(r"Night Joker: used .+'s (.+?) for ", line)
        if m:
            seen.add("copied:" + m.group(1))
for token in ("Night Joker", "Trade:", "N's PP Up", "Transformation Tome"):
    check(token in seen, f"{token} fired in a real greedy game")
check(any(s.startswith("copied:") for s in seen), "Night Joker really copied a Bench attack")
check("copied:Rampaging Thunder" in seen,
      "Night Joker reached N's Zekrom's 250 (the cost-free copy actually pays off)")

print()
if fails:
    print(f"FAIL ({fails} issue(s))")
    sys.exit(1)
print("OK — N's Zoroark ex archetype verified against its real card text")
sys.exit(0)
