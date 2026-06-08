#!/usr/bin/env python3
"""
test_more_decks.py — the feature/more-decks archetypes (Fighting / Dark / Metal /
Water). Each new effect is asserted against its printed card text.

Covers: Mega Lucario ex (Aura Jab), Regirock ex (Regi Charge, Giant Rock),
Iron Boulder ex (Power Stomp), Koraidon ex (Retribution Strike, Kaiser Tackle),
Mega Absol ex (Terminal Period, Claw of Darkness), Mega Mawile ex (Gobble Down,
Huge Bite), Hop's Zacian ex (Insta-Strike), Dondozo ex (Avenging Billow,
Dynamic Dive), Lapras ex (Power Splash).

Run from project root:  python3 tests/test_more_decks.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine.game import setup_game, start_turn, end_turn, legal_actions
from src.engine import effects as fx


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def expected_dmg(attacker, defender, raw):
    if raw <= 0:
        return 0
    if attacker.types and defender.types:
        for w, _ in defender.weaknesses:
            if w == attacker.types[0]:
                return raw * 2
    return raw


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    DREEPY = db.get("Dreepy")
    FIGHT = db.get("Basic Fighting Energy")
    WATER = db.get("Basic Water Energy")
    EX_STAGE2 = db.get("Dragapult ex")     # a Stage 2 (for Giant Rock's condition)

    def defender(b, name="Dreepy"):
        b.active = InPlayPokemon(card=db.get(name))
        return b.active

    # --- Mega Lucario ex: Aura Jab — attach up to 3 Fighting from discard to bench. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Mega Lucario ex"))
    a.active = src
    a.bench = [InPlayPokemon(card=DREEPY), InPlayPokemon(card=DREEPY)]
    a.discard = [FIGHT, FIGHT, FIGHT, FIGHT]
    fx._aura_jab(ctx(st, a, b, source=src))
    moved = sum(len(m.energy) for m in a.bench)
    check(moved == 3 and a.discard.count(FIGHT) == 1,
          f"Aura Jab: attach 3 Fighting from discard to bench (moved {moved})")

    # --- Regirock ex: Regi Charge — attach up to 2 Fighting from discard to self. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Regirock ex"))
    a.active = src
    a.discard = [FIGHT, FIGHT, FIGHT]
    fx._regi_charge(ctx(st, a, b, source=src))
    check(len(src.energy) == 2 and a.discard.count(FIGHT) == 1,
          f"Regi Charge: attach 2 Fighting from discard to self (got {len(src.energy)})")

    # --- Regirock ex: Giant Rock — 140, +140 if opp Active is a Stage 2. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Regirock ex"))
    a.active = src
    d = defender(b)                                # Dreepy (Basic) -> 140
    fx._giant_rock(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 140), f"Giant Rock vs Basic: 140 (got {d.damage})")
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Regirock ex"))
    a.active = src
    b.active = InPlayPokemon(card=EX_STAGE2)       # Stage 2 -> 280
    fx._giant_rock(ctx(st, a, b, source=src))
    check(b.active.damage == expected_dmg(src.card, b.active.card, 280),
          f"Giant Rock vs Stage 2: 280 (got {b.active.damage})")

    # --- Iron Boulder ex: Power Stomp — discard 2 Energy from self (rider). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Iron Boulder ex"), energy=[FIGHT, FIGHT, FIGHT])
    a.active = src
    fx._power_stomp(ctx(st, a, b, source=src))
    check(len(src.energy) == 1 and a.discard.count(FIGHT) == 2,
          f"Power Stomp: discard 2 self Energy (left {len(src.energy)})")

    # --- Koraidon ex: Retribution Strike — 20 + 10 per counter on self. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Koraidon ex"), damage=30)   # 3 counters
    a.active = src
    d = defender(b)
    fx._retribution_strike(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 50), f"Retribution Strike: 20+30 = 50 (got {d.damage})")

    # --- Koraidon ex: Kaiser Tackle — 60 to itself (rider). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Koraidon ex"))
    a.active = src
    fx._kaiser_tackle(ctx(st, a, b, source=src))
    check(src.damage == 60, f"Kaiser Tackle: 60 self-damage (got {src.damage})")

    # --- Mega Absol ex: Terminal Period — KO if opp Active has exactly 6 counters. ---
    st, a, b = fresh(db)
    d = defender(b); d.damage = 60
    fx._terminal_period(ctx(st, a, b))
    check(d.is_knocked_out, "Terminal Period: KO at exactly 6 counters")
    st, a, b = fresh(db)
    d = defender(b); d.damage = 50
    fx._terminal_period(ctx(st, a, b))
    check(not d.is_knocked_out and d.damage == 50, "Terminal Period: no KO at 5 counters")

    # --- Mega Absol ex: Claw of Darkness — discard a card from opp hand (rider). ---
    st, a, b = fresh(db)
    b.hand = [FIGHT, DREEPY]              # Dreepy is higher value -> discarded
    fx._claw_of_darkness(ctx(st, a, b))
    check(len(b.hand) == 1 and len(b.discard) == 1,
          f"Claw of Darkness: discard 1 from opp hand (hand={len(b.hand)})")

    # --- Mega Mawile ex: Gobble Down — 80 per Prize you've taken. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Mega Mawile ex"))
    a.active = src
    a.prizes = [DREEPY] * 4               # 2 taken
    d = defender(b)
    fx._gobble_down(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 160), f"Gobble Down: 80×2 = 160 (got {d.damage})")

    # --- Mega Mawile ex: Huge Bite — 260, but 30 if opp Active already damaged. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Mega Mawile ex"))
    a.active = src
    d = defender(b)                       # undamaged -> 260
    fx._huge_bite(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 260), f"Huge Bite undamaged: 260 (got {d.damage})")
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Mega Mawile ex"))
    a.active = src
    d = defender(b); d.damage = 20        # already damaged -> base 30 (+existing 20)
    fx._huge_bite(ctx(st, a, b, source=src))
    check(d.damage == 20 + expected_dmg(src.card, d.card, 30),
          f"Huge Bite vs damaged: base 30 (got {d.damage})")

    # --- Hop's Zacian ex: Insta-Strike — 30 to a Benched opponent (rider). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Hop's Zacian ex"))
    a.active = src
    b.active = InPlayPokemon(card=DREEPY)
    benched = InPlayPokemon(card=DREEPY)
    b.bench = [benched]
    fx._insta_strike(ctx(st, a, b, source=src))
    check(benched.damage == 30, f"Insta-Strike: 30 to a benched Pokémon (got {benched.damage})")

    # --- Dondozo ex: Avenging Billow — 30 + 10 per counter on self. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Dondozo ex"), damage=50)    # 5 counters
    a.active = src
    d = defender(b)
    fx._avenging_billow(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 80), f"Avenging Billow: 30+50 = 80 (got {d.damage})")

    # --- Dondozo ex: Dynamic Dive — 240 to opp + 50 to self (v0 takes the extra). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Dondozo ex"))
    a.active = src
    d = defender(b)
    fx._dynamic_dive(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 240) and src.damage == 50,
          f"Dynamic Dive: 240 + 50 self (opp={d.damage}, self={src.damage})")

    # --- Lapras ex: Power Splash — 40 per Energy attached to this Pokémon. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Lapras ex"), energy=[WATER, WATER, WATER, WATER])
    a.active = src
    d = defender(b)
    fx._power_splash(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 160), f"Power Splash: 40×4 = 160 (got {d.damage})")

    # --- per-attack cooldown: Mega Brave locks itself next turn, Aura Jab stays usable. ---
    st, a, b = fresh(db)
    luc = InPlayPokemon(card=db.get("Mega Lucario ex"), energy=[FIGHT, FIGHT])  # pays both
    luc.pending_locked_attacks = ["Mega Brave"]    # simulate having used Mega Brave last turn
    a.active = luc
    a.deck = [FIGHT] * 5
    b.active = InPlayPokemon(card=DREEPY)
    start_turn(st)                                  # promotes pending -> active lock for P0
    names = {a.active.card.attacks[x.attack_index].name
             for x in legal_actions(st) if x.kind == "attack"}
    check("Mega Brave" not in names, "Mega Brave should be locked this turn")
    check("Aura Jab" in names, "Aura Jab should still be usable (per-attack lock, not blanket)")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — feature/more-decks (9 cards) all match card text: Mega Lucario, Regirock, "
          "Iron Boulder, Koraidon, Mega Absol, Mega Mawile, Hop's Zacian, Dondozo, Lapras.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
