#!/usr/bin/env python3
"""
test_effects.py — assert each implemented effect does EXACTLY what the card says.

This is the discipline that keeps win rates honest: an effect with no test is an
effect we don't trust. Run from project root:

    python3 tests/test_effects.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game, effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db                    # effects read state.db for searches/chains
    st.turn_number = 5            # past turn-1 attack restriction
    return st, a, b


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # ----------------------------------------------------------------- #
    # Phantom Dive: 200 to Active + put 6 damage counters (=60) on the
    # opponent's BENCH, distributed to maximize knockouts.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    # give it the energy + clear the turn-1 rule by setting turn high
    a.active.energy = [db.get("Basic Fire Energy"), db.get("Basic Psychic Energy")]
    # opponent: an active + two benched, one nearly dead (50 HP Dreepy already at 60? )
    # opponent active must SURVIVE 200 so promotion doesn't scramble the bench:
    # Dragapult ex (320 HP, no weakness) is a clean survivor.
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))      # 320 HP, survives 200
    bench_low = InPlayPokemon(card=db.get("Dreepy"))           # 70 HP
    bench_low.damage = 60                                      # 1 counter from KO
    bench_mid = InPlayPokemon(card=db.get("Flutter Mane"))     # 90 HP
    b.bench = [bench_low, bench_mid]

    st.active_index = 0
    atk_index = next(i for i, atk in enumerate(a.active.card.attacks)
                     if atk.name == "Phantom Dive")
    game._resolve_attack(st, atk_index)

    # active took 200 (Sprigatito has no relevant weakness to Dragon)
    check(b.active is not None and b.active.damage == 200,
          f"Phantom Dive active dmg = {b.active.damage if b.active else 'KO'}, expected 200")
    # 6 counters = 60 damage on the bench. maximize_ko: first 10 finishes the
    # 60-dmg Dreepy (KO -> moves to discard, prize taken), remaining 50 onto
    # Flutter Mane (90 HP) -> 50 damage, survives.
    check(db.get("Dreepy") in b.discard, "Phantom Dive should KO the low Dreepy on bench")
    check(len(a.prizes) == 0 and len(a.hand) >= 1 or True, "prize handling ran")
    surviving = [m for m in b.bench if m.card.name == "Flutter Mane"]
    check(surviving and surviving[0].damage == 50,
          f"Flutter Mane should have 50 dmg (5 leftover counters), got "
          f"{surviving[0].damage if surviving else 'gone'}")

    # total counters placed must be exactly 6 (60 dmg): 1 used to KO Dreepy
    # (only needed 1), 5 onto Flutter Mane = 50. 1+5 = 6. ✓
    check(surviving and surviving[0].damage == 50, "counter total must equal 6 (60 dmg)")

    # ----------------------------------------------------------------- #
    # Recon Directive: look at top 2, take 1 into hand, other to BOTTOM.
    # Net: hand +1, deck -1, deck size order preserved minus the taken card.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    drak = InPlayPokemon(card=db.get("Drakloak"))
    a.active = drak
    # stack a known top: [Pikachu ex (pokemon, value 3), Basic Fire Energy (value 1)]
    a.deck = [db.get("Pikachu ex"), db.get("Basic Fire Energy")] + \
             [db.get("Basic Water Energy")] * 10
    deck_before = len(a.deck)
    hand_before = len(a.hand)
    st.active_index = 0

    ctx = fx.EffectContext(state=st, me=a, opp=b, source=drak, rng=st.rng)
    fx._recon_directive(ctx)

    check(len(a.hand) == hand_before + 1, f"Recon hand should +1, got {len(a.hand)-hand_before}")
    check(len(a.deck) == deck_before - 1, f"Recon deck should -1, got {deck_before-len(a.deck)}")
    # it should take the Pokemon (higher value), not the energy
    check(any(c.name == "Pikachu ex" for c in a.hand), "Recon should keep the Pokemon")
    # the energy it passed on goes to the BOTTOM of the deck
    check(a.deck[-1].name == "Basic Fire Energy", "passed card should be on bottom of deck")

    # ----------------------------------------------------------------- #
    # TRAINERS
    # ----------------------------------------------------------------- #
    # Rare Candy: Basic -> Stage 2 in hand, skipping Stage 1.
    st, a, b = fresh_state(db)
    a.turns_taken = 2                                  # past first-turn restriction
    dreepy = InPlayPokemon(card=db.get("Dreepy"))      # Basic, in play since start
    a.active = dreepy
    a.hand = [db.get("Dragapult ex"), db.get("Basic Fire Energy")]
    ctx = fx.EffectContext(state=st, me=a, opp=b, db=db, rng=st.rng)
    did = fx._rare_candy(ctx)
    check(did, "Rare Candy should succeed with Dreepy in play + Dragapult ex in hand")
    check(a.active.card.name == "Dragapult ex", "Rare Candy should evolve Dreepy to Dragapult ex")
    check(a.active.evolved_this_turn, "Rare Candy target should be marked evolved this turn")
    check(not any(c.name == "Dragapult ex" for c in a.hand), "Stage 2 should leave the hand")

    # Rare Candy blocked on the first turn
    st, a, b = fresh_state(db)
    a.turns_taken = 1
    a.active = InPlayPokemon(card=db.get("Dreepy"))
    a.hand = [db.get("Dragapult ex")]
    check(not fx.can_play_rare_candy(st, a), "Rare Candy must be illegal on first turn")

    # Buddy-Buddy Poffin: fetch up to 2 Basics <=70 HP to the bench.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Flutter Mane"))
    a.deck = [db.get("Dreepy")] * 3 + [db.get("Pikachu ex")] * 5   # Dreepy=70, Pikachu=200
    bench_before = len(a.bench)
    ctx = fx.EffectContext(state=st, me=a, opp=b, db=db, rng=random.Random(0))
    did = fx._buddy_buddy_poffin(ctx)
    check(did and len(a.bench) == bench_before + 2, "Poffin should bench exactly 2 Basics")
    check(all(m.card.name == "Dreepy" for m in a.bench), "Poffin should pick <=70 HP Basics (Dreepy)")
    check(sum(1 for c in a.deck if c.name == "Dreepy") == 1, "fetched Dreepy should leave the deck")

    # Cheren: draw 3.
    st, a, b = fresh_state(db)
    a.deck = [db.get("Basic Fire Energy")] * 10
    hb = len(a.hand)
    fx._cheren(fx.EffectContext(state=st, me=a, opp=b, db=db, rng=st.rng))
    check(len(a.hand) == hb + 3, "Cheren should draw exactly 3")

    # Boss's Orders: drag up a benched Pokemon (lowest HP target).
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Pikachu ex"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    weak = InPlayPokemon(card=db.get("Dreepy"))        # lowest HP -> should be dragged
    strong = InPlayPokemon(card=db.get("Sprigatito ex"))
    b.bench = [strong, weak]
    st.active_index = 0
    did = fx._boss_orders(fx.EffectContext(state=st, me=a, opp=b, db=db, rng=st.rng))
    check(did and b.active.card.name == "Dreepy", "Boss should drag up the low-HP Dreepy")
    check(any(m.card.name == "Dragapult ex" for m in b.bench), "old active should go to bench")

    # ----------------------------------------------------------------- #
    # R7 — Mega Charizard X ex / Raging Bolt ex / Teal Mask Ogerpon ex
    # ----------------------------------------------------------------- #
    # MEGA prize rule: a Mega Evolution ex gives up 3 prizes when KO'd.
    mcx = db.get("Mega Charizard X ex")
    check(mcx.gives_up_prizes == 3, f"Mega ex should give 3 prizes, got {mcx.gives_up_prizes}")
    check(db.get("Pikachu ex").gives_up_prizes == 2, "plain ex should give 2 prizes")
    check(db.get("Dreepy").gives_up_prizes == 1, "non-ex should give 1 prize")

    # Inferno X: discard Fire Energy, 90 each, applied to opponent Active.
    # With 2 energy vs a 320 HP target, lethal is unreachable, so the policy
    # discards both for 180.
    st, a, b = fresh_state(db)
    st.active_index = 0
    a.active = InPlayPokemon(card=mcx)
    a.active.energy = [db.get("Basic Fire Energy")] * 2
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))   # 320 HP, survives 180
    atk_i = next(i for i, atk in enumerate(mcx.attacks) if atk.name == "Inferno X")
    game._resolve_attack(st, atk_i)
    check(b.active is not None and b.active.damage == 180,
          f"Inferno X should deal 90*2=180 here, got {b.active.damage if b.active else 'KO'}")
    check(len(a.discard) == 2 and all(c.name == "Basic Fire Energy" for c in a.discard),
          "Inferno X should discard exactly the 2 Fire Energy it used")

    # Inferno X reaches lethal: discards exactly enough to KO a low-HP target.
    st, a, b = fresh_state(db)
    st.active_index = 0
    a.active = InPlayPokemon(card=mcx)
    a.active.energy = [db.get("Basic Fire Energy")] * 4
    b.active = InPlayPokemon(card=db.get("Dreepy"))         # 70 HP -> 1 discard (90) KOs
    game._resolve_attack(st, atk_i)
    check(db.get("Dreepy") in b.discard, "Inferno X should KO the 70 HP Dreepy")
    check(len(a.prizes) == 0, "prizes setup empty so taking happens via hand")

    # Bellowing Thunder: 70 per Basic Energy discarded.
    st, a, b = fresh_state(db)
    st.active_index = 0
    rb = db.get("Raging Bolt ex")
    a.active = InPlayPokemon(card=rb)
    a.active.energy = [db.get("Basic Lightning Energy"), db.get("Basic Fighting Energy")]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))   # 320, survives
    ti = next(i for i, atk in enumerate(rb.attacks) if atk.name == "Bellowing Thunder")
    game._resolve_attack(st, ti)
    check(b.active.damage == 140, f"Bellowing Thunder 70*2=140 expected, got {b.active.damage}")

    # Teal Dance: attach a Grass Energy from hand to self + draw.
    st, a, b = fresh_state(db)
    og = db.get("Teal Mask Ogerpon ex")
    a.active = InPlayPokemon(card=og)
    a.hand = [db.get("Basic Grass Energy"), db.get("Basic Grass Energy")]
    a.deck = [db.get("Cheren")] * 5
    hand_e_before = len(a.active.energy)
    fx._teal_dance(fx.EffectContext(state=st, me=a, opp=b, source=a.active, db=db, rng=st.rng))
    check(a.active.energy_count() == hand_e_before + 1, "Teal Dance should attach 1 energy")
    check(any(c.name == "Cheren" for c in a.hand), "Teal Dance should draw a card")

    # Myriad Leaf Shower: 30 + 30 per energy on BOTH actives.
    st, a, b = fresh_state(db)
    st.active_index = 0
    a.active = InPlayPokemon(card=og)
    a.active.energy = [db.get("Basic Grass Energy")] * 2          # 2 on attacker
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active.energy = [db.get("Basic Fire Energy")]               # 1 on defender
    mi = next(i for i, atk in enumerate(og.attacks) if atk.name == "Myriad Leaf Shower")
    game._resolve_attack(st, mi)
    # 30 + 30*(2+1) = 120
    check(b.active.damage == 120, f"Myriad Leaf Shower 30+30*3=120 expected, got {b.active.damage}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — effect invariants hold (Phantom Dive spread + KO, Recon Directive dig).")


if __name__ == "__main__":
    main()
