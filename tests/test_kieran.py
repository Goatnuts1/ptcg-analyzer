#!/usr/bin/env python3
"""
test_kieran.py — Kieran (Twilight Masquerade 154), Supporter:
"Choose 1:
  • Switch your Active Pokémon with 1 of your Benched Pokémon.
  • During this turn, attacks used by your Pokémon do 30 more damage to your opponent's
    Active Pokémon ex and Active Pokémon V (before applying Weakness and Resistance)."

Asserted clause by clause:
  * the buff applies ONLY to the opponent's ACTIVE, and only to a Pokémon ex / Pokémon V
    (a non-Rule-Box Active and a BENCHED ex are both negative cases);
  * "before applying Weakness and Resistance" — (100+30) ×2 on a Metal-Weak ex = 260,
    not 100×2+30 = 230;
  * "during this turn" — start_turn clears it, so it can never leak into a later turn;
  * the switch mode is taken when the damage mode would do nothing.

Run: python3 tests/test_kieran.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import start_turn


def fresh_state(db):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    a.deck = [db.get("Basic Metal Energy")] * 8
    b.deck = [db.get("Basic Metal Energy")] * 8
    return st, a, b


def trainer_ctx(st, me, opp):
    return fx.EffectContext(state=st, me=me, opp=opp, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    card = db.get("Kieran")

    # --- 0. card data + registry wiring. ---
    check(card.is_supporter, "Kieran is a Supporter")
    text = " ".join(card.rules)
    check("Switch your Active Pokémon" in text and "30 more damage" in text
          and "Active Pokémon ex and Active Pokémon V" in text,
          f"unexpected card text: {card.rules}")
    check("Kieran" in fx.TRAINER_EFFECTS, "Kieran must be registered")

    # --- 0b. the ex/V predicate: Mega ex and ex count, plain Pokémon don't. ---
    check(fx._is_ex_or_v(db.get("Genesect ex")) is True, "a Pokémon ex qualifies")
    check(fx._is_ex_or_v(db.get("Mega Excadrill ex")) is True,
          "a Mega Evolution Pokémon ex carries the 'ex' subtype and qualifies")
    check(fx._is_ex_or_v(db.get("Metagross")) is False,
          "NEGATIVE: a non-Rule-Box Pokémon does not qualify")

    # --- 1. damage mode: the opponent's Active is an ex -> +30 armed, no switch. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.bench = [InPlayPokemon(card=db.get("Beldum"))]
    b.active = InPlayPokemon(card=db.get("Dachsbun ex"))     # Metal Weakness ×2, ex
    did = fx._kieran(trainer_ctx(st, a, b))
    check(did is True, "Kieran must report that it acted")
    check(a.bonus_damage_vs_ex_v == 30,
          f"the +30 must be armed on the player, got {a.bonus_damage_vs_ex_v}")
    check(a.active.card.name == "Mega Excadrill ex",
          "the damage mode must NOT also switch the Active")

    # --- 2. the +30 lands BEFORE Weakness: (100 + 30) ×2 = 260. ---
    check(any(w == "Metal" for w, _ in b.active.card.weaknesses),
          "Dachsbun ex is expected to be Metal-Weak in this pool")
    dealt = fx.apply_attack_damage(fx.EffectContext(state=st, me=a, opp=b, source=a.active,
                                                    db=st.db, rng=st.rng),
                                   b.active, 100, owner=b, source=a.active)
    check(dealt == 260, f"(100+30) doubled by Weakness = 260, got {dealt}")

    # --- 3. NEGATIVE: the buff does not apply to a non-ex/V Active. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.bonus_damage_vs_ex_v = 30
    b.active = InPlayPokemon(card=db.get("Metagross"))       # no Rule Box, no Metal Weakness
    dealt = fx.apply_attack_damage(fx.EffectContext(state=st, me=a, opp=b, source=a.active,
                                                    db=st.db, rng=st.rng),
                                   b.active, 100, owner=b, source=a.active)
    check(dealt == 100, f"a non-ex/V Active takes no bonus, got {dealt}")

    # --- 4. NEGATIVE: the buff does not apply to a BENCHED ex. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.bonus_damage_vs_ex_v = 30
    b.active = InPlayPokemon(card=db.get("Metagross"))
    benched_ex = InPlayPokemon(card=db.get("Genesect ex"))
    b.bench = [benched_ex]
    dealt = fx.apply_attack_damage(fx.EffectContext(state=st, me=a, opp=b, source=a.active,
                                                    db=st.db, rng=st.rng),
                                   benched_ex, 100, owner=b, source=a.active)
    check(dealt == 100, f"a Benched ex takes no bonus (Active only), got {dealt}")

    # --- 5. NEGATIVE: your OWN ex is not buffed by your own Kieran (the bonus is read
    # off the ATTACKER's owner and only applies against the opponent). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Genesect ex"))
    a.bonus_damage_vs_ex_v = 30
    b.active = InPlayPokemon(card=db.get("Crabominable"))
    dealt = fx.apply_attack_damage(fx.EffectContext(state=st, me=b, opp=a, source=b.active,
                                                    db=st.db, rng=st.rng),
                                   a.active, 100, owner=a, source=b.active)
    check(dealt == 100,
          f"the opponent attacking INTO your ex gets no bonus from your Kieran, got {dealt}")

    # --- 6. "during this turn": start_turn clears the bonus. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    b.active = InPlayPokemon(card=db.get("Dachsbun ex"))
    a.bonus_damage_vs_ex_v = 30
    st.active_index = 0
    start_turn(st)
    check(a.bonus_damage_vs_ex_v == 0,
          "the 'during this turn' bonus must not survive into another of your turns")

    # --- 7. switch mode: no ex/V Active to hit -> switch instead. ---
    st, a, b = fresh_state(db)
    small = InPlayPokemon(card=db.get("Beldum"))
    big = InPlayPokemon(card=db.get("Metagross"))
    a.active, a.bench = small, [big]
    b.active = InPlayPokemon(card=db.get("Metagross"))       # not an ex/V
    did = fx._kieran(trainer_ctx(st, a, b))
    check(did is True, "the switch mode must report that it acted")
    check(a.active is big and a.bench[0] is small,
          f"Kieran must switch the Active, got active={a.active.card.name}")
    check(a.bonus_damage_vs_ex_v == 0, "the switch mode must not arm the damage bonus")

    # --- 8. can_play: unplayable only when NEITHER mode can do anything. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Beldum"))          # no bench -> can't switch
    b.active = InPlayPokemon(card=db.get("Metagross"))       # not ex/V -> no buff target
    st.active_index = 0
    check(fx.can_play_trainer(st, a, "Kieran") is False,
          "no bench and no ex/V Active -> Kieran must not be offered")
    b.active = InPlayPokemon(card=db.get("Genesect ex"))
    check(fx.can_play_trainer(st, a, "Kieran") is True,
          "an ex Active makes the damage mode live -> offer it")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_kieran.py: all checks passed — Kieran's +30 hits only the opponent's Active "
          "ex/V, before Weakness, for this turn only; otherwise it switches")


if __name__ == "__main__":
    main()
