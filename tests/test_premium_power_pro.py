#!/usr/bin/env python3
"""
test_premium_power_pro.py — Premium Power Pro (me1 124, Item): "During this turn,
attacks used by your {F} Pokémon do 30 more damage to your opponent's Active Pokémon
(before applying Weakness and Resistance)."

Same shape as Kieran's damage mode: a same-turn player-scoped flag set by the card and
read in the apply_attack_damage chokepoint, cleared by start_turn (no pending_* hop — it
never survives to another turn). The negative cases pin down each clause: "your {F}
Pokémon" (a non-Fighting attacker of ours gets nothing), "your opponent's ACTIVE"
(a Benched target gets nothing), "During this turn" (gone next turn).

Run: python3 tests/test_premium_power_pro.py
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
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng,
                            effect_kind="trainer")


def hit(st, me, opp, attacker, target, amount):
    ctx = fx.EffectContext(state=st, me=me, opp=opp, source=attacker, db=st.db, rng=st.rng)
    return fx.apply_attack_damage(ctx, target, amount, owner=opp, source=attacker)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    check("Premium Power Pro" in fx.TRAINER_EFFECTS,
          "Premium Power Pro must be a registered Trainer effect")
    check(db.get("Premium Power Pro").is_item,
          "Premium Power Pro is an Item (any number per turn), not a Supporter")

    # --- 1. Playing it buffs a Fighting attacker's hit on the opponent's Active by 30.
    # Dragapult ex has no Weakness/Resistance, so the math is clean. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    check(fx._premium_power_pro(ctx_for(st, a, b)) is True,
          "the Item must report that it did something")
    check(a.bonus_damage_fighting_vs_active == 30,
          f"the flag must be 30, got {a.bonus_damage_fighting_vs_active}")
    check(hit(st, a, b, chomp, b.active, 100) == 130,
          "a Fighting attacker must do +30 to the opponent's Active")

    # --- 2. Two copies in one turn are two separate effects -> +60. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    fx._premium_power_pro(ctx_for(st, a, b))
    fx._premium_power_pro(ctx_for(st, a, b))
    check(a.bonus_damage_fighting_vs_active == 60,
          f"two copies must stack to +60, got {a.bonus_damage_fighting_vs_active}")
    check(hit(st, a, b, chomp, b.active, 100) == 160,
          "two copies must land +60 on the hit")

    # --- 3. NEGATIVE: "your {F} Pokémon" — our own NON-Fighting attacker gets nothing.
    # Cynthia's Roselia is Grass (and there is no Roserade in play, so Cheer On to Glory
    # can't muddy the number). ---
    st, a, b = fresh_state(db)
    roselia = InPlayPokemon(card=db.get("Cynthia's Roselia"))
    a.active = roselia
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    fx._premium_power_pro(ctx_for(st, a, b))
    check(hit(st, a, b, roselia, b.active, 100) == 100,
          "a Grass attacker must get no boost from a {F}-only effect")

    # --- 4. NEGATIVE: "your opponent's ACTIVE Pokémon" — a Benched target gets nothing. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    victim = InPlayPokemon(card=db.get("Kyurem"))
    b.bench = [victim]
    fx._premium_power_pro(ctx_for(st, a, b))
    check(hit(st, a, b, chomp, victim, 100) == 100,
          "a Benched target must never get the +30")

    # --- 5. NEGATIVE: it's OUR buff — the opponent's Fighting attacker doesn't get it. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    opp_chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    b.active = opp_chomp
    fx._premium_power_pro(ctx_for(st, a, b))          # A plays it
    check(hit(st, b, a, opp_chomp, a.active, 100) == 100,
          "the opponent's Fighting attacker must not benefit from OUR Premium Power Pro")

    # --- 6. "before applying Weakness and Resistance": inside the doubling.
    # Snorlax ex is Fighting ×2 -> (100+30)×2 = 260, not 100×2+30. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))
    fx._premium_power_pro(ctx_for(st, a, b))
    check(hit(st, a, b, chomp, b.active, 100) == 260,
          "the +30 must be added BEFORE Weakness doubles ((100+30)×2 = 260)")

    # --- 7. "During this turn": the flag is cleared at the start of our next turn, and
    # does NOT leak across the opponent's turn either. ---
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.deck = [db.get("Basic Fighting Energy")] * 5
    b.deck = [db.get("Basic Fighting Energy")] * 5
    st.active_index = 0
    fx._premium_power_pro(ctx_for(st, a, b))
    st.active_index = 1
    start_turn(st)                     # opponent's turn — our flag is not theirs to clear
    check(a.bonus_damage_fighting_vs_active == 30,
          "the opponent's start_turn must not clear OUR flag (it clears their own)")
    st.active_index = 0
    start_turn(st)                     # our next turn — now it's gone
    check(a.bonus_damage_fighting_vs_active == 0,
          "start_turn must clear the buff on our next turn ('during this turn' only)")
    check(hit(st, a, b, chomp, b.active, 100) == 100,
          "after expiry the hit must be back to base")

    # --- 8. can_play gate: only offered when a Fighting Active of ours can actually cash
    # the buff in and the opponent has an Active to hit. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    check(fx.can_play_trainer(st, a, "Premium Power Pro") is True,
          "with a Fighting Active and an opposing Active it must be playable")
    a.active = InPlayPokemon(card=db.get("Cynthia's Roselia"))     # Grass
    check(fx.can_play_trainer(st, a, "Premium Power Pro") is False,
          "with a non-Fighting Active it must not be offered")
    a.active = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    b.active = None
    check(fx.can_play_trainer(st, a, "Premium Power Pro") is False,
          "with no opposing Active there is nothing to boost damage against")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_premium_power_pro.py: all checks passed — +30 only for your Fighting "
          "attackers into the opponent's Active, stacking per copy, pre-Weakness, and "
          "expiring with the turn")


if __name__ == "__main__":
    main()
