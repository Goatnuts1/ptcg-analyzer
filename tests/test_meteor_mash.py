#!/usr/bin/env python3
"""
test_meteor_mash.py — Metagross (Temporal Forces 115) Meteor Mash:
"[M] 60 — During your next turn, this Pokémon's Meteor Mash attack does 60 more
damage (before applying Weakness and Resistance)."

MODELING NOTE: the buff must be LIVE during the OWNER's next turn, so it uses the
pending_*/promote-in-start_turn lifecycle of `pending_locked_attacks` (Mega Brave),
NOT the set-and-clear-in-start_turn pattern of `shielded`/`retaliate` — those are
live only during the OPPONENT's one intervening turn, which would clear this buff
at exactly the moment it is supposed to apply. Asserted below on both boundaries.

Meteor Mash owns its damage (60 or 120 is conditional on a flag the engine can't
see, and the printed number is flat), and "before applying Weakness and Resistance"
is verified by hitting a Metal-Weak defender for (60+60)×2.

Run: python3 tests/test_meteor_mash.py
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
    a.deck = [db.get("Basic Metal Energy")] * 10
    b.deck = [db.get("Basic Metal Energy")] * 10
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    metagross_card = db.get("Metagross")

    # --- 0. card data + registry wiring. ---
    atk = next(a for a in metagross_card.attacks if a.name == "Meteor Mash")
    check(atk.cost == ("Metal",) and atk.damage == 60 and atk.damage_suffix == "",
          f"Meteor Mash is [M] for a flat 60, got {atk.cost} {atk.damage}{atk.damage_suffix!r}")
    check("60 more damage" in atk.text and "before applying Weakness and Resistance" in atk.text,
          f"unexpected card text: {atk.text!r}")
    check(("Metagross", "Meteor Mash") in fx.ATTACK_EFFECTS, "Meteor Mash must be registered")
    check(("Metagross", "Meteor Mash") in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Meteor Mash's base is conditional (60 vs 120) — the effect must own its damage")

    # --- 1. first use: 60 now, and the +60 is ARMED for next turn (not live yet). ---
    st, a, b = fresh_state(db)
    gross = InPlayPokemon(card=metagross_card)
    a.active = gross
    target = InPlayPokemon(card=db.get("Genesect ex"))   # Fire Weak, Grass Resist: neither applies
    b.active = target
    fx._meteor_mash(ctx_for(st, a, b, source=gross))
    check(target.damage == 60, f"first Meteor Mash must do exactly 60, got {target.damage}")
    check(gross.pending_boosted_attacks == {"Meteor Mash": 60},
          f"the +60 must be pending for next turn, got {gross.pending_boosted_attacks}")
    check(gross.boosted_attacks == {},
          f"the buff must NOT be live on the turn it was set, got {gross.boosted_attacks}")

    # --- 2. the OPPONENT's turn starting must not promote our buff... ---
    st.active_index = 1
    start_turn(st)
    check(gross.boosted_attacks == {} and gross.pending_boosted_attacks == {"Meteor Mash": 60},
          "the opponent's turn must leave the pending buff untouched")

    # --- 3. ...and the OWNER's next turn promotes it: the second Meteor Mash does 120,
    # and re-arms +60 (it does not stack to +120). ---
    st.active_index = 0
    start_turn(st)
    check(gross.boosted_attacks == {"Meteor Mash": 60},
          f"the buff must be live on the owner's next turn, got {gross.boosted_attacks}")
    check(gross.pending_boosted_attacks == {},
          "promoting must clear the pending slot")
    target.damage = 0
    fx._meteor_mash(ctx_for(st, a, b, source=gross))
    check(target.damage == 120, f"a buffed Meteor Mash must do 120, got {target.damage}")
    check(gross.pending_boosted_attacks == {"Meteor Mash": 60},
          "using it again re-arms exactly +60 for the following turn (no stacking)")

    # --- 4. NEGATIVE: skip a turn without attacking and the buff expires — a third
    # turn later Meteor Mash is back to 60. ---
    st.active_index = 1
    start_turn(st)
    st.active_index = 0
    start_turn(st)                    # promotes the +60 armed in step 3
    st.active_index = 1
    start_turn(st)
    st.active_index = 0
    start_turn(st)                    # nothing was armed last turn -> buff gone
    check(gross.boosted_attacks == {},
          f"an unused buff must not persist a second owner-turn, got {gross.boosted_attacks}")
    target.damage = 0
    fx._meteor_mash(ctx_for(st, a, b, source=gross))
    check(target.damage == 60, f"unbuffed Meteor Mash is 60 again, got {target.damage}")

    # --- 5. NEGATIVE: the buff is keyed to Meteor Mash ONLY — Luster Blast is
    # untouched by it (its registered effect discards 2 Energy, it never reads the
    # boost table). ---
    st, a, b = fresh_state(db)
    gross2 = InPlayPokemon(card=metagross_card)
    gross2.boosted_attacks = {"Meteor Mash": 60}
    gross2.energy = [db.get("Basic Metal Energy")] * 4
    a.active = gross2
    b.active = InPlayPokemon(card=db.get("Genesect ex"))
    fx._luster_blast(ctx_for(st, a, b, source=gross2))
    check(b.active.damage == 0 and gross2.energy_count() == 2,
          "Luster Blast must be unaffected by the Meteor Mash buff (engine applies its "
          f"own 200; the effect only discards 2 Energy) — got {gross2.energy_count()} Energy")

    # --- 6. Weakness applies to the BOOSTED total, once: (60+60) x2 on a Metal-Weak
    # defender = 240. ---
    st, a, b = fresh_state(db)
    gross3 = InPlayPokemon(card=metagross_card)
    gross3.boosted_attacks = {"Meteor Mash": 60}
    a.active = gross3
    weak = InPlayPokemon(card=db.get("Crabominable"))    # Metal Weakness ×2
    check(any(w == "Metal" for w, _ in weak.card.weaknesses),
          "Crabominable is expected to be Metal-Weak in this pool")
    b.active = weak
    fx._meteor_mash(ctx_for(st, a, b, source=gross3))
    check(weak.damage == 240,
          f"(60+60) doubled by Weakness = 240 (buff applies BEFORE W/R), got {weak.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_meteor_mash.py: all checks passed — Meteor Mash hits 60, arms +60 for "
          "the owner's next turn only, and the buff lands before Weakness")


if __name__ == "__main__":
    main()
