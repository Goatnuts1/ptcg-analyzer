#!/usr/bin/env python3
"""
test_slowking.py — assert Slowking (Seek Inspiration attack-redirection) and its
pre-evolution Slowpoke (Dangle Tail) do EXACTLY what their card text says. Both
verified against limitlesstcg.com and matched against the pool entries this
session (sv7-58 Slowking, sv7-57 Slowpoke).

Covers:
  - Slowking "Seek Inspiration" [1 Psychic + 1 Colorless] — pool text: "Discard
    the top card of your deck, and if that card is a Pokémon that doesn't have a
    Rule Box, choose 1 of its attacks and use it as this attack. (Pokémon ex,
    Pokémon V, etc. have Rule Boxes.)" v0 scope: only the copied attack's printed
    base damage lands (no recursive effect dispatch — documented limitation).
    Positive copy-and-hit, weakness-keyed-off-Slowking (not the copied mon),
    deterministic tie-break, and every documented miss case (empty deck,
    Trainer/Energy on top, Rule-Box Pokémon on top, Pokémon with only a 0-damage
    attack).
  - Slowking "Super Psy Bolt" [2 Psychic + 1 Colorless] — pool text: plain "120"
    damage, no additional text. Needs no registered effect; sanity-checked so a
    future regression that accidentally wires an effect onto it gets caught.
  - Slowpoke "Dangle Tail" [1 Colorless] — pool text: "Put a Pokémon from your
    discard pile into your hand." Positive recovery, negative no-Pokémon-in-
    discard no-op, and the multi-candidate _search_value policy pick.

Run from project root:  python3 tests/test_slowking.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


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
    # SLOWKING (sv7-58, Stage 1 Psychic, HP 120, evolves from Slowpoke,
    # Weakness Darkness x2, Resistance Fighting -30, Retreat 3)
    # =================================================================== #

    slowking_card = db.get("Slowking")
    check(slowking_card.hp == 120, f"Slowking should be 120 HP, got {slowking_card.hp}")
    check(tuple(slowking_card.types) == ("Psychic",),
          f"Slowking should be Psychic-typed, got {slowking_card.types}")
    check(slowking_card.evolves_from == "Slowpoke",
          f"Slowking should evolve from Slowpoke, got {slowking_card.evolves_from}")
    check(any(w == ("Darkness", "×2") for w in slowking_card.weaknesses),
          f"Slowking should be Weak to Darkness x2, got {slowking_card.weaknesses}")

    seek_atk = next(a for a in slowking_card.attacks if a.name == "Seek Inspiration")
    check(seek_atk.cost == ("Psychic", "Colorless"),
          f"Seek Inspiration cost should be [Psychic, Colorless], got {seek_atk.cost}")
    check(seek_atk.damage == 0,
          f"Seek Inspiration's printed damage should parse to 0, got {seek_atk.damage}")

    bolt_atk = next(a for a in slowking_card.attacks if a.name == "Super Psy Bolt")
    check(bolt_atk.cost == ("Psychic", "Psychic", "Colorless"),
          f"Super Psy Bolt cost should be [Psychic, Psychic, Colorless], got {bolt_atk.cost}")
    check(bolt_atk.damage == 120,
          f"Super Psy Bolt should be 120 damage, got {bolt_atk.damage}")
    check(bolt_atk.text == "",
          f"Super Psy Bolt should carry no additional text, got {bolt_atk.text!r}")

    # =================================================================== #
    # Seek Inspiration — pool text: "Discard the top card of your deck, and if
    # that card is a Pokémon that doesn't have a Rule Box, choose 1 of its
    # attacks and use it as this attack."
    # =================================================================== #

    # --- 1a. POSITIVE: top card is Crustle (Stage 1, non-Rule-Box, ONE attack
    # "Superb Scissors" 120 dmg) -> discarded, and Slowking deals 120 to the
    # opponent's Active using Superb Scissors' printed base damage. ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    defender = InPlayPokemon(card=db.get("Dragapult ex"))     # 320 HP, no listed Weakness
    b.active = defender
    crustle_card = db.get("Crustle")
    a.deck = [crustle_card]
    ctx = ctx_for(st, a, b, source=slowking)
    fx._seek_inspiration(ctx)
    check(a.deck == [], "the top deck card must be removed from the deck")
    check(crustle_card in a.discard, "the discarded card must land in the discard pile")
    check(defender.damage == 120,
          f"Seek Inspiration should copy Crustle's Superb Scissors for 120, got {defender.damage}")

    # --- 1b. WEAKNESS KEYS OFF SLOWKING, NOT THE COPIED MON: same Crustle-copy
    # (Superb Scissors, 120) against Timburr (80 HP, Weak Psychic x2) — Slowking
    # is Psychic-typed, so Weakness doubles the 120 to 240. This proves "copying
    # an attack doesn't change who the physical attacker is" (Slowking's own
    # type governs Weakness/Resistance, per apply_attack_damage's chokepoint). ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    timburr = InPlayPokemon(card=db.get("Timburr"))            # 80 HP, Weak Psychic x2
    b.active = timburr
    a.deck = [db.get("Crustle")]
    ctx = ctx_for(st, a, b, source=slowking)
    fx._seek_inspiration(ctx)
    check(timburr.damage == 240,
          f"Weakness must apply as 120*2=240 (Slowking is Psychic-typed, Timburr is "
          f"Weak to Psychic x2), got {timburr.damage}")

    # --- 1c. DETERMINISTIC TIE-BREAK: Walking Wake (non-Rule-Box Basic) has TWO
    # attacks both printed at 20 damage ("Aurora Gain" 20, "Undulating Slice"
    # "20x" -> parses to base 20 too). max() over a fixed-order tuple keeps the
    # FIRST maximal element on a tie, so "Aurora Gain" (listed first in the pool)
    # must be the one chosen — byte-reproducible, no RNG draw. ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    walking_wake_card = db.get("Walking Wake")
    check([atk.name for atk in walking_wake_card.attacks] == ["Aurora Gain", "Undulating Slice"],
          f"setup: expected Aurora Gain listed before Undulating Slice, got "
          f"{[atk.name for atk in walking_wake_card.attacks]}")
    check(walking_wake_card.attacks[0].damage == walking_wake_card.attacks[1].damage == 20,
          "setup: both Walking Wake attacks must parse to 20 base damage (a real tie)")
    defender2 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender2
    a.deck = [walking_wake_card]
    ctx = ctx_for(st, a, b, source=slowking)
    fx._seek_inspiration(ctx)
    check(defender2.damage == 20,
          f"tie-broken choice must still deal exactly 20 (the tied base damage), "
          f"got {defender2.damage}")

    # --- 1d. NEGATIVE (Rule Box miss): top card is Magcargo ex (subtypes include
    # 'ex' -> has a Rule Box) -> discarded, but 0 damage dealt (a real miss). ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    defender3 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender3
    magcargo_ex = db.get("Magcargo ex")
    check("ex" in magcargo_ex.subtypes, "setup: Magcargo ex must carry a Rule Box (ex)")
    a.deck = [magcargo_ex]
    ctx = ctx_for(st, a, b, source=slowking)
    fx._seek_inspiration(ctx)
    check(a.deck == [] and magcargo_ex in a.discard,
          "a Rule-Box Pokémon must still be discarded even though it's a miss")
    check(defender3.damage == 0,
          f"discarding a Rule-Box Pokémon must deal 0 damage (a real miss), got {defender3.damage}")

    # --- 1e. NEGATIVE (Trainer/Energy miss): top card is a Basic Energy (not a
    # Pokémon at all) -> discarded, 0 damage. ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    defender4 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender4
    energy_card = db.get("Basic Psychic Energy")
    a.deck = [energy_card]
    ctx = ctx_for(st, a, b, source=slowking)
    fx._seek_inspiration(ctx)
    check(a.deck == [] and energy_card in a.discard,
          "a non-Pokémon top card must still be discarded")
    check(defender4.damage == 0,
          f"discarding Basic Psychic Energy (not a Pokémon) must deal 0 damage, got {defender4.damage}")

    # --- 1f. NEGATIVE (0-damage-attack miss): top card is Dwebble (Basic,
    # non-Rule-Box) whose only attack "Ascension" prints no damage (parses to 0)
    # -> discarded, but 0 damage dealt (a real miss even though it IS a
    # qualifying Pokémon with an attack). ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    defender5 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender5
    dwebble_card = db.get("Dwebble")
    check(dwebble_card.attacks[0].name == "Ascension" and dwebble_card.attacks[0].damage == 0,
          "setup: Dwebble's only attack (Ascension) must parse to 0 damage")
    a.deck = [dwebble_card]
    ctx = ctx_for(st, a, b, source=slowking)
    fx._seek_inspiration(ctx)
    check(a.deck == [] and dwebble_card in a.discard,
          "Dwebble must still be discarded")
    check(defender5.damage == 0,
          f"a Pokémon whose best attack is 0 damage must still be a miss, got {defender5.damage}")

    # --- 1g. NEGATIVE (empty deck): deck is empty -> no crash, no discard growth,
    # 0 damage. ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    defender6 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender6
    a.deck = []
    ctx = ctx_for(st, a, b, source=slowking)
    fx._seek_inspiration(ctx)               # must not raise
    check(a.deck == [] and a.discard == [],
          "an empty deck must not add anything to the discard pile")
    check(defender6.damage == 0,
          f"an empty deck must deal 0 damage with no crash, got {defender6.damage}")

    # --- 1h. INTEGRATION via game._resolve_attack: Seek Inspiration's own
    # printed damage (0) must not be separately engine-applied ON TOP OF the
    # effect's copied hit (would double 120 -> 120, i.e. no observable
    # difference here since base=0, but this confirms end-to-end wiring:
    # attack index resolves, cost/energy aside, defender takes exactly 120). ---
    st, a, b = fresh_state(db)
    st.active_index = 0
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    defender7 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender7
    a.deck = [db.get("Crustle")]
    si_i = next(i for i, atk in enumerate(slowking.card.attacks) if atk.name == "Seek Inspiration")
    game._resolve_attack(st, si_i)
    check(defender7.damage == 120,
          f"end-to-end via game._resolve_attack, Seek Inspiration should deal exactly "
          f"120 (Crustle's Superb Scissors, no double-apply of the printed 0 base), "
          f"got {defender7.damage}")

    # --- 1i. INTEGRATION sanity: Super Psy Bolt (no registered effect) deals a
    # plain 120 via game._resolve_attack, confirming it needs no implementation. ---
    st, a, b = fresh_state(db)
    st.active_index = 0
    slowking = InPlayPokemon(card=slowking_card)
    a.active = slowking
    defender8 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender8
    spb_i = next(i for i, atk in enumerate(slowking.card.attacks) if atk.name == "Super Psy Bolt")
    game._resolve_attack(st, spb_i)
    check(defender8.damage == 120,
          f"Super Psy Bolt should deal a plain 120 with no additional effect, got "
          f"{defender8.damage}")

    # =================================================================== #
    # SLOWPOKE (sv7-57, Basic Psychic, HP 80, evolves to Slowking, Weakness
    # Darkness x2, Resistance Fighting -30, Retreat 2)
    # Attack "Dangle Tail" [1 Colorless] — pool text: "Put a Pokémon from your
    # discard pile into your hand."
    # =================================================================== #

    slowpoke_card = db.get("Slowpoke")
    check(slowpoke_card.hp == 80, f"Slowpoke should be 80 HP, got {slowpoke_card.hp}")
    check("Slowking" in slowpoke_card.evolves_to,
          f"Slowpoke should evolve into Slowking, got {slowpoke_card.evolves_to}")
    dangle_atk = next(a for a in slowpoke_card.attacks if a.name == "Dangle Tail")
    check(dangle_atk.cost == ("Colorless",),
          f"Dangle Tail cost should be [Colorless], got {dangle_atk.cost}")
    check(dangle_atk.damage == 0,
          f"Dangle Tail's printed damage should parse to 0, got {dangle_atk.damage}")

    # --- 2a. POSITIVE: one Pokémon in the discard pile -> recovered to hand,
    # removed from discard. ---
    st, a, b = fresh_state(db)
    slowpoke = InPlayPokemon(card=slowpoke_card)
    a.active = slowpoke
    crustle_disc = db.get("Crustle")
    a.discard = [crustle_disc]
    ctx = ctx_for(st, a, b, source=slowpoke)
    fx._dangle_tail(ctx)
    check(crustle_disc in a.hand, "Dangle Tail should put the discarded Pokémon into hand")
    check(crustle_disc not in a.discard, "the recovered card must be removed from discard")

    # --- 2b. NEGATIVE: discard pile has cards but NO Pokémon (only a Trainer)
    # -> no-op, hand and discard both untouched. ---
    st, a, b = fresh_state(db)
    slowpoke = InPlayPokemon(card=slowpoke_card)
    a.active = slowpoke
    ultra_ball = db.get("Ultra Ball")
    a.discard = [ultra_ball]
    ctx = ctx_for(st, a, b, source=slowpoke)
    result = fx._dangle_tail(ctx)
    check(ultra_ball in a.discard, "with no Pokémon in discard, Dangle Tail must no-op")
    check(ultra_ball not in a.hand, "a non-Pokémon must never be pulled to hand by Dangle Tail")
    check(a.hand == [], "hand must remain empty on a no-op")

    # --- 2c. NEGATIVE: fully empty discard pile -> no crash, no-op. ---
    st, a, b = fresh_state(db)
    slowpoke = InPlayPokemon(card=slowpoke_card)
    a.active = slowpoke
    a.discard = []
    ctx = ctx_for(st, a, b, source=slowpoke)
    fx._dangle_tail(ctx)                    # must not raise
    check(a.hand == [], "an empty discard pile must leave the hand untouched")

    # --- 2d. POLICY: with 2 qualifying Pokémon in discard, Dangle Tail picks the
    # higher _search_value candidate — Dwebble (Basic that evolves_to Crustle,
    # value 5) over Conkeldurr (Stage 2, value 4). ---
    st, a, b = fresh_state(db)
    slowpoke = InPlayPokemon(card=slowpoke_card)
    a.active = slowpoke
    dwebble_disc = db.get("Dwebble")
    conkeldurr_disc = db.get("Conkeldurr")
    check(dwebble_disc.is_basic and dwebble_disc.evolves_to,
          "setup: Dwebble must be a Basic with evolves_to (value 5)")
    check("Stage 2" in conkeldurr_disc.subtypes,
          "setup: Conkeldurr must be Stage 2 (value 4)")
    a.discard = [conkeldurr_disc, dwebble_disc]
    ctx = ctx_for(st, a, b, source=slowpoke)
    fx._dangle_tail(ctx)
    check(dwebble_disc in a.hand and dwebble_disc not in a.discard,
          "Dangle Tail should recover the higher-value candidate (Dwebble, evolution fodder)")
    check(conkeldurr_disc in a.discard and conkeldurr_disc not in a.hand,
          "the lower-value candidate (Conkeldurr) must remain in the discard pile")

    # --- 2e. INTEGRATION via game._resolve_attack: full attack-index path fires
    # the same effect and does 0 damage (no combat component to Dangle Tail). ---
    st, a, b = fresh_state(db)
    st.active_index = 0
    slowpoke = InPlayPokemon(card=slowpoke_card)
    a.active = slowpoke
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    crustle_disc2 = db.get("Crustle")
    a.discard = [crustle_disc2]
    dt_i = next(i for i, atk in enumerate(slowpoke.card.attacks) if atk.name == "Dangle Tail")
    game._resolve_attack(st, dt_i)
    check(crustle_disc2 in a.hand,
          "end-to-end via game._resolve_attack, Dangle Tail should still recover the Pokémon")
    check(b.active.damage == 0,
          f"Dangle Tail must deal 0 combat damage, got {b.active.damage}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Slowking (Seek Inspiration attack-copy incl. weakness/tie-break/miss "
          "cases, Super Psy Bolt) and Slowpoke (Dangle Tail incl. policy pick) all hold.")


if __name__ == "__main__":
    main()
