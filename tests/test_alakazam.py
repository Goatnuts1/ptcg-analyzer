#!/usr/bin/env python3
"""
test_alakazam.py — assert Alakazam (MEG/56) does EXACTLY what the card says.

Covers:
  - Ability "Psychic Draw" (on-evolve-from-hand draw-3 trigger)
  - Attack "Powerful Hand" (hand-size-scaling damage-counter placement)

Card text (verified against limitlesstcg.com this session; quoted inline per
behavior below):
  Ability "Psychic Draw": "Once during your turn, when you play this Pokémon
    from your hand to evolve 1 of your Pokémon, you may use this Ability.
    Draw 3 cards."
  Attack "Powerful Hand" [P] "": "Place 2 damage counters on your opponent's
    Active Pokémon for each card in your hand."

Run from project root:  python3 tests/test_alakazam.py
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
    st.turn_number = 5            # past turn-1 attack/evolve restriction
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
    # PSYCHIC DRAW — POSITIVE: normal evolve from hand triggers draw 3.
    # Ability text: "when you play this Pokémon from your hand to evolve 1 of
    # your Pokémon, you may use this Ability. Draw 3 cards."
    # =================================================================== #
    st, a, b = fresh_state(db)
    kadabra = InPlayPokemon(card=db.get("Kadabra"))
    a.active = kadabra
    alakazam_card = db.get("Alakazam")
    a.hand = [alakazam_card]
    # deck needs >=3 cards to draw fully; use filler basic energy
    filler = db.get("Basic Psychic Energy")
    a.deck = [filler, filler, filler, filler, filler]

    hand_before = len(a.hand)          # 1 (the Alakazam card about to be played)
    deck_before = len(a.deck)
    game.apply_action(st, Action(kind="evolve", hand_index=0, target_index=-1))

    check(a.active.card.name == "Alakazam",
          f"evolve should replace mon.card with Alakazam, got {a.active.card.name}")
    # hand: -1 (Alakazam popped to evolve) +3 (Psychic Draw) = hand_before + 2
    check(len(a.hand) == hand_before + 2,
          f"Psychic Draw should draw 3 net of the popped evolve card: "
          f"expected hand={hand_before + 2}, got {len(a.hand)}")
    check(len(a.deck) == deck_before - 3,
          f"Psychic Draw should pull exactly 3 from the deck, "
          f"expected deck={deck_before - 3}, got {len(a.deck)}")

    # =================================================================== #
    # PSYCHIC DRAW — NEGATIVE: playing Alakazam as a normal Basic-style play
    # (play_basic action kind, NOT the evolve action kind) does NOT draw.
    # The Ability only fires "when you play this Pokémon from your hand to
    # EVOLVE 1 of your Pokémon" — not merely upon entering play.
    # =================================================================== #
    st, a, b = fresh_state(db)
    a.hand = [db.get("Alakazam")]
    a.deck = [filler, filler, filler, filler, filler]
    hand_before = len(a.hand)
    deck_before = len(a.deck)
    game.apply_action(st, Action(kind="play_basic", hand_index=0))

    check(len(a.bench) == 1 and a.bench[0].card.name == "Alakazam",
          "play_basic should still bench the Alakazam card")
    check(len(a.hand) == hand_before - 1,
          f"play_basic should only pop the played card, no extra draw: "
          f"expected hand={hand_before - 1}, got {len(a.hand)}")
    check(len(a.deck) == deck_before,
          f"Psychic Draw must NOT fire on a normal Basic-style play: "
          f"expected deck unchanged at {deck_before}, got {len(a.deck)}")

    # =================================================================== #
    # PSYCHIC DRAW — NEGATIVE: retreating an already-in-play Alakazam does
    # NOT draw (only the evolve-from-hand moment triggers it).
    # =================================================================== #
    st, a, b = fresh_state(db)
    alakazam_active = InPlayPokemon(card=db.get("Alakazam"))
    a.active = alakazam_active
    bench_mon = InPlayPokemon(card=db.get("Abra"))
    a.bench = [bench_mon]
    a.hand = []
    a.deck = [filler, filler, filler, filler, filler]
    deck_before = len(a.deck)

    game.apply_action(st, Action(kind="retreat", target_index=0))

    check(a.active is bench_mon and a.bench[0] is alakazam_active,
          "retreat should swap active <-> bench as normal")
    check(len(a.hand) == 0,
          f"Psychic Draw must NOT fire on retreat: expected empty hand, "
          f"got {len(a.hand)}")
    check(len(a.deck) == deck_before,
          f"Psychic Draw must NOT fire on retreat: expected deck unchanged "
          f"at {deck_before}, got {len(a.deck)}")

    # =================================================================== #
    # PSYCHIC DRAW — deck-out edge case: fewer than 3 cards in deck draws
    # only what's available (draw() caps at what's left; no crash).
    # =================================================================== #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Kadabra"))
    a.hand = [db.get("Alakazam")]
    a.deck = [filler]                  # only 1 card available, not 3
    game.apply_action(st, Action(kind="evolve", hand_index=0, target_index=-1))

    check(len(a.deck) == 0,
          f"Psychic Draw should drain the deck when fewer than 3 remain, "
          f"got {len(a.deck)} left")
    check(len(a.hand) == 1,
          f"Psychic Draw should only draw the 1 available card (0 popped for "
          f"evolve + 1 drawn), got hand={len(a.hand)}")

    # =================================================================== #
    # POWERFUL HAND — attack text: [Psychic] "": "Place 2 damage counters on
    # your opponent's Active Pokémon for each card in your hand."
    # POSITIVE: hand size 5 -> 10 counters (100 damage) placed via
    # place_counters (a counter effect, NOT apply_attack_damage — so no
    # Weakness/Resistance multiplier applies).
    # =================================================================== #
    st, a, b = fresh_state(db)
    attacker = InPlayPokemon(card=db.get("Alakazam"))
    attacker.energy = [db.get("Basic Psychic Energy")]
    a.active = attacker
    defender = InPlayPokemon(card=db.get("Dragapult ex"))   # high HP, survives
    b.active = defender
    a.hand = [filler, filler, filler, filler, filler]        # hand size 5

    atk_index = next(i for i, atk in enumerate(attacker.card.attacks)
                     if atk.name == "Powerful Hand")
    game._resolve_attack(st, atk_index)

    check(defender.damage == 100,
          f"Powerful Hand with hand size 5 should place 2*5=10 counters "
          f"(=100 damage), got {defender.damage}")
    check(len(a.hand) == 5,
          f"Powerful Hand must not consume hand cards (Energy pays cost, "
          f"not hand cards), got hand={len(a.hand)}")

    # =================================================================== #
    # POWERFUL HAND — NEGATIVE: hand size 0 -> 0 counters placed.
    # =================================================================== #
    st, a, b = fresh_state(db)
    attacker = InPlayPokemon(card=db.get("Alakazam"))
    attacker.energy = [db.get("Basic Psychic Energy")]
    a.active = attacker
    defender = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender
    a.hand = []                                              # hand size 0

    atk_index = next(i for i, atk in enumerate(attacker.card.attacks)
                     if atk.name == "Powerful Hand")
    game._resolve_attack(st, atk_index)

    check(defender.damage == 0,
          f"Powerful Hand with an empty hand should place 0 counters, "
          f"got damage={defender.damage}")

    # =================================================================== #
    # POWERFUL HAND — hand size scaling sanity: 1 card -> 2 counters (=20).
    # =================================================================== #
    st, a, b = fresh_state(db)
    attacker = InPlayPokemon(card=db.get("Alakazam"))
    attacker.energy = [db.get("Basic Psychic Energy")]
    a.active = attacker
    defender = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender
    a.hand = [filler]                                        # hand size 1

    atk_index = next(i for i, atk in enumerate(attacker.card.attacks)
                     if atk.name == "Powerful Hand")
    game._resolve_attack(st, atk_index)

    check(defender.damage == 20,
          f"Powerful Hand with hand size 1 should place 2 counters (=20 "
          f"damage), got {defender.damage}")

    # =================================================================== #
    # POWERFUL HAND — no Weakness multiplier: place_counters bypasses W/R
    # entirely (it is not apply_attack_damage). Use a Darkness-weak-to-Psychic
    # target (Alakazam itself IS ×2 weak to Darkness, but Powerful Hand's
    # SOURCE is Psychic, so use a Psychic-weak defender to prove no ×2 is
    # silently applied on the effect path).
    # =================================================================== #
    st, a, b = fresh_state(db)
    attacker = InPlayPokemon(card=db.get("Alakazam"))
    attacker.energy = [db.get("Basic Psychic Energy")]
    a.active = attacker
    kadabra_defender = InPlayPokemon(card=db.get("Kadabra"))  # ×2 weak to Darkness,
    b.active = kadabra_defender                               # irrelevant here — Psychic
                                                                # source, no weakness match
    a.hand = [filler, filler]                                  # hand size 2 -> 4 counters = 40

    atk_index = next(i for i, atk in enumerate(attacker.card.attacks)
                     if atk.name == "Powerful Hand")
    game._resolve_attack(st, atk_index)

    check(kadabra_defender.damage == 40,
          f"Powerful Hand damage must be exactly 2*handsize*10 with NO "
          f"Weakness/Resistance multiplier (counters, not attack damage): "
          f"expected 40, got {kadabra_defender.damage}")

    # ----------------------------------------------------------------- #
    if fails:
        print(f"FAILED {len(fails)} check(s):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    else:
        print("test_alakazam.py: all checks passed")


if __name__ == "__main__":
    main()
