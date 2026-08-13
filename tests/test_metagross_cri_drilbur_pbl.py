#!/usr/bin/env python3
"""
test_metagross_cri_drilbur_pbl.py — the REAL tournament-list prints substituted in after
the initial mega_excadrill build accidentally used different, non-matching prints
(Temporal Forces Metagross/Drilbur instead of the actual Chaos Rising Metagross / Pitch
Black Drilbur the 2nd/416 "Tournament of Doom" list ran). Covers:
  - Metagross (CRI): M Bounce Back (60 + force the opponent to switch, their choice)
    and Metallic Hammer ("150+", optional discard 3 Metal Energy for +150).
  - Drilbur (PBL, the bare name — NOT "Drilbur (TEF)"): Call for Family (search up to 2
    Basic Pokémon to the Bench).

Run: python3 tests/test_metagross_cri_drilbur_pbl.py
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
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    metagross_cri = db.get("Metagross (CRI)")
    drilbur_pbl = db.get("Drilbur")

    check(metagross_cri.id == "cri-61", f"expected Chaos Rising Metagross (cri-61), got {metagross_cri.id}")
    check(drilbur_pbl.id == "pbl-46", f"expected Pitch Black Drilbur (pbl-46), got {drilbur_pbl.id}")
    check(not any(a.name == "Dig Dig Dig" for a in drilbur_pbl.abilities),
          "the bare 'Drilbur' print must NOT carry Dig Dig Dig (that's 'Drilbur (TEF)')")

    # --- 1. M Bounce Back: 60 (engine-applied elsewhere) + force a switch; the
    # opponent's REPLACEMENT is chosen by _promote's healthiest-bencher policy. ---
    st, a, b = fresh_state(db)
    old_active = InPlayPokemon(card=db.get("Dwebble"))
    healthy = InPlayPokemon(card=db.get("Dwebble"))
    weak = InPlayPokemon(card=db.get("Dwebble"))
    weak.damage = 50   # less remaining HP than `healthy`
    b.active = old_active
    b.bench = [weak, healthy]
    attacker = InPlayPokemon(card=metagross_cri)
    a.active = attacker
    fx._bounce_back(ctx_for(st, a, b, source=attacker))
    check(old_active not in b.bench + [b.active] or old_active in b.bench,
          "the old Active must end up on the Bench")
    check(old_active in b.bench, "the switched-out Pokemon must be on the Bench")
    check(b.active is healthy, f"the opponent must promote the healthiest bencher, got {b.active}")

    # --- 2. NEGATIVE: no opponent Bench -> no switch (nothing to switch to). ---
    st, a, b = fresh_state(db)
    solo_active = InPlayPokemon(card=db.get("Dwebble"))
    b.active = solo_active
    b.bench = []
    attacker2 = InPlayPokemon(card=metagross_cri)
    a.active = attacker2
    fx._bounce_back(ctx_for(st, a, b, source=attacker2))
    check(b.active is solo_active, "with an empty Bench, the Active must not be touched")

    # --- 3. Metallic Hammer: >=3 Metal Energy attached -> discards exactly 3, +150. ---
    st, a, b = fresh_state(db)
    metal = db.get("Basic Metal Energy")
    mg = InPlayPokemon(card=metagross_cri)
    mg.energy = [metal, metal, metal, metal]   # 4 attached (the attack's own cost)
    a.active = mg
    victim = InPlayPokemon(card=db.get("Dwebble"))
    b.active = victim
    fx._metallic_hammer(ctx_for(st, a, b, source=mg))
    check(victim.damage == 300, f"150 base + 150 bonus = 300, got {victim.damage}")
    check(len(mg.energy) == 1, f"exactly 3 of the 4 attached Energy must be discarded, got {len(mg.energy)} left")
    check(len(a.discard) == 3, f"the 3 discarded Energy must land in the discard pile, got {len(a.discard)}")

    # --- 4. NEGATIVE: <3 Metal Energy attached -> base 150 only, nothing discarded. ---
    st, a, b = fresh_state(db)
    mg2 = InPlayPokemon(card=metagross_cri)
    mg2.energy = [metal, metal]
    a.active = mg2
    victim2 = InPlayPokemon(card=db.get("Dwebble"))
    b.active = victim2
    fx._metallic_hammer(ctx_for(st, a, b, source=mg2))
    check(victim2.damage == 150, f"with <3 Energy attached, only the base 150 applies, got {victim2.damage}")
    check(len(mg2.energy) == 2, "with <3 Energy attached, nothing may be discarded")

    # --- 5. Call for Family: benches up to 2 Basic Pokémon from the deck. ---
    st, a, b = fresh_state(db)
    drilbur = InPlayPokemon(card=drilbur_pbl)
    a.bench = [drilbur]
    a.deck = [db.get("Beldum"), db.get("Beldum"), db.get("Metang"), db.get("Basic Metal Energy")]
    fx._call_for_family(ctx_for(st, a, b, source=drilbur))
    check(len(a.bench) == 3, f"exactly 2 Basics must join the Bench (1 already there + 2), got {len(a.bench)}")
    check(sum(1 for m in a.bench if m.card.name == "Beldum") == 2,
          "search_deck's value policy may pick either eligible Basic; here only Beldum is Basic and non-Metang")

    # --- 6. NEGATIVE: Bench already full -> nothing searched, no crash. ---
    st, a, b = fresh_state(db)
    drilbur2 = InPlayPokemon(card=drilbur_pbl)
    a.bench = [InPlayPokemon(card=db.get("Beldum")) for _ in range(5)]  # MAX_BENCH == 5
    a.deck = [db.get("Beldum"), db.get("Beldum")]
    before = len(a.deck)
    fx._call_for_family(ctx_for(st, a, b, source=drilbur2))
    check(len(a.deck) == before, "with a full Bench, Call for Family must be a no-op")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_metagross_cri_drilbur_pbl.py: all checks passed — the real "
          "tournament-list prints (Metagross CRI-61, Drilbur PBL-46) behave correctly")


if __name__ == "__main__":
    main()
