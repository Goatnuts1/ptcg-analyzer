#!/usr/bin/env python3
"""
test_chienpao.py — assert Lillie's Clefairy ex, Chien-Pao, and Alakazam do EXACTLY
what their card text says (data/standard_pool.json quoted inline, verified against
limitlesstcg.com this session).

Covers:
  - Lillie's Clefairy ex: "Fairy Zone" (passive Weakness-rewrite on opponent's Dragon
    Pokémon) + "Full Moon Rondo" (bench-count scaling attack)
  - Chien-Pao: "Snow Sink" (discard-Stadium-on-bench trigger) + "Icicle Loop"
    (self-energy-return rider)
  - Alakazam: "Psychic Draw" (on-evolve-from-hand draw-3 trigger) + "Powerful Hand"
    (hand-size-scaling damage-counter placement)

Also asserts negative cases: Fairy Zone does nothing to a non-Dragon opponent
Pokémon and does not leak to the ability holder's OWN side's Dragon; Full Moon
Rondo's damage is exactly 20 base with zero benched Pokémon on both sides;
Alakazam's draw-3 does NOT fire on a normal Basic play or on retreat, only on an
evolve-from-hand (both plain evolve and Rare Candy); Powerful Hand scales correctly
with hand size 0 vs hand size 5 and uses place_counters (no Weakness), not
weakness-scaled attack damage.

Run from project root:  python3 tests/test_chienpao.py
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
    # LILLIE'S CLEFAIRY EX (JTG/56 -> sv9-56 in pool)
    # Ability "Fairy Zone" (pool text): "The Weakness of each of your opponent's
    # Dragon Pokémon in play is now Psychic. (Apply Weakness as ×2.)" — passive,
    # continuous, board-wide (checked on both Active and Bench for the holder).
    # =================================================================== #

    # --- 1a. POSITIVE: Clefairy ex on the BENCH (not Active) still projects Fairy
    # Zone. Dreepy (Dragon) has NO printed Weakness, so any bonus proves the
    # rewrite, not a coincidence with the printed table. Attacker (Abra) is
    # Psychic-typed. ---
    st, a, b = fresh_state(db)
    clefairy = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    abra_attacker = InPlayPokemon(card=db.get("Abra"))       # Psychic source
    a.active = abra_attacker
    a.bench = [clefairy]                                      # Clefairy ex on BENCH
    dreepy = InPlayPokemon(card=db.get("Dreepy"))             # Dragon, weaknesses=[]
    b.active = dreepy
    ctx = ctx_for(st, me=a, opp=b, source=abra_attacker)
    dealt = fx.apply_attack_damage(ctx, dreepy, 50, owner=b, source=abra_attacker)
    check(dealt == 100 and dreepy.damage == 100,
          f"Fairy Zone (Clefairy ex on BENCH) should rewrite Dreepy's Weakness to "
          f"Psychic (50 -> x2 = 100), got dealt={dealt}")

    # --- 1b. POSITIVE: Clefairy ex as the Active also projects Fairy Zone, and can
    # itself be the Psychic-typed attacking source. ---
    st, a, b = fresh_state(db)
    clefairy = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    a.active = clefairy
    dreepy = InPlayPokemon(card=db.get("Dreepy"))
    b.active = dreepy
    ctx = ctx_for(st, me=a, opp=b, source=clefairy)
    dealt = fx.apply_attack_damage(ctx, dreepy, 20, owner=b, source=clefairy)
    check(dealt == 40 and dreepy.damage == 40,
          f"Fairy Zone (Clefairy ex Active) should rewrite Dreepy's Weakness to "
          f"Psychic (20 -> x2 = 40), got dealt={dealt}")

    # --- 1c. NEGATIVE: Fairy Zone does nothing to a non-Dragon opponent Pokémon.
    # Pikachu ex (Lightning, weak only to Fighting) takes no bonus from a Psychic
    # source even with Clefairy ex in play. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    pikachu = InPlayPokemon(card=db.get("Pikachu ex"))
    b.active = pikachu
    ctx = ctx_for(st, me=a, opp=b, source=a.active)
    dealt = fx.apply_attack_damage(ctx, pikachu, 50, owner=b, source=a.active)
    check(dealt == 50 and pikachu.damage == 50,
          f"Fairy Zone must do NOTHING to a non-Dragon opponent Pokémon (Pikachu ex), "
          f"got dealt={dealt}")

    # --- 1d. NEGATIVE: Fairy Zone does not leak to the ability holder's OWN side's
    # Dragon Pokémon — the text says "your OPPONENT's Dragon Pokémon". Here A holds
    # Clefairy ex, and A's OWN Dreepy is attacked by B; A's own Dragon must not get
    # the Psychic-Weakness rewrite from A's own Ability. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))     # A holds Fairy Zone
    own_dragon = InPlayPokemon(card=db.get("Dreepy"))
    a.bench = [own_dragon]                                             # A's OWN Dragon
    b_attacker = InPlayPokemon(card=db.get("Abra"))                    # Psychic source
    b.active = b_attacker
    ctx = ctx_for(st, me=b, opp=a, source=b_attacker)
    dealt = fx.apply_attack_damage(ctx, own_dragon, 50, owner=a, source=b_attacker)
    check(dealt == 50 and own_dragon.damage == 50,
          f"Fairy Zone must NOT apply to the ability holder's OWN side's Dragon "
          f"(only the opponent's Dragons are affected), got dealt={dealt}")

    # --- 1e. Ability suppression disables Fairy Zone. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    dreepy = InPlayPokemon(card=db.get("Dreepy"))
    b.active = dreepy
    ctx = ctx_for(st, me=a, opp=b, source=a.active)
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        dealt = fx.apply_attack_damage(ctx, dreepy, 50, owner=b, source=a.active)
        check(dealt == 50 and dreepy.damage == 50,
              f"a suppressed Fairy Zone must NOT rewrite Weakness, got dealt={dealt}")
    finally:
        fx.ability_suppressed = orig_suppressed

    # =================================================================== #
    # Attack "Full Moon Rondo" [P][C] 20+ (pool text): "This attack does 20 more
    # damage for each Benched Pokémon (both yours and your opponent's)."
    # =================================================================== #

    # --- 1f. Zero benched Pokémon on BOTH sides -> exactly 20 base damage.
    # Defender is Pikachu ex (non-Dragon, not weak to Psychic) to isolate the pure
    # bench-scaling math from any Fairy Zone / Weakness noise. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    st.active_index = 0
    fmr_i = next(i for i, atk in enumerate(a.active.card.attacks)
                 if atk.name == "Full Moon Rondo")
    game._resolve_attack(st, fmr_i)
    check(b.active is not None and b.active.damage == 20,
          f"Full Moon Rondo with 0 benched Pokémon on both sides should deal exactly "
          f"20 base, got {b.active.damage if b.active else 'KO'}")

    # --- 1g. Scaling: 2 benched for the attacker + 1 benched for the defender = 3
    # total -> 20 + 20*3 = 80. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    a.bench = [InPlayPokemon(card=db.get("Abra")), InPlayPokemon(card=db.get("Abra"))]
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    b.bench = [InPlayPokemon(card=db.get("Dreepy"))]
    st.active_index = 0
    game._resolve_attack(st, fmr_i)
    check(b.active is not None and b.active.damage == 80,
          f"Full Moon Rondo with 3 total benched Pokémon should deal 20+20*3=80, "
          f"got {b.active.damage if b.active else 'KO'}")

    # =================================================================== #
    # CHIEN-PAO (SSP/56 -> svp-152 in pool)
    # Ability "Snow Sink" (pool text): "When you play this Pokémon from your hand
    # onto your Bench during your turn, you may discard a Stadium in play."
    # =================================================================== #

    # --- 2a. POSITIVE: a Stadium in play (owned by the OPPONENT) is discarded to
    # its OWNER's discard pile when Chien-Pao is played from hand to the bench. ---
    st, a, b = fresh_state(db)
    a.hand = [db.get("Chien-Pao")]
    st.stadium = db.get("Paradise Resort")
    st.stadium_owner = 1                       # owned by B, not the player benching
    st.active_index = 0                        # A is current
    game.apply_action(st, game.Action(kind="play_basic", hand_index=0))
    check(st.stadium is None, "Snow Sink should discard the Stadium in play")
    check(db.get("Paradise Resort") in b.discard,
          "the discarded Stadium should go to its OWNER's (B's) discard, not A's")
    check(any(m.card.name == "Chien-Pao" for m in a.bench),
          "Chien-Pao should be benched regardless")

    # --- 2b. NEGATIVE: no Stadium in play -> nothing happens, no crash. ---
    st, a, b = fresh_state(db)
    a.hand = [db.get("Chien-Pao")]
    st.stadium = None
    st.active_index = 0
    game.apply_action(st, game.Action(kind="play_basic", hand_index=0))
    check(st.stadium is None and len(a.bench) == 1,
          "Snow Sink with no Stadium in play must be a no-op, not a crash")

    # --- 2c. Ability suppression disables Snow Sink (Stadium survives). ---
    st, a, b = fresh_state(db)
    a.hand = [db.get("Chien-Pao")]
    st.stadium = db.get("Paradise Resort")
    st.stadium_owner = 0
    st.active_index = 0
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        game.apply_action(st, game.Action(kind="play_basic", hand_index=0))
        check(st.stadium is not None and st.stadium.name == "Paradise Resort",
              "a suppressed Snow Sink must NOT discard the Stadium")
    finally:
        fx.ability_suppressed = orig_suppressed

    # =================================================================== #
    # Attack "Icicle Loop" [W][W][C] 120 (pool text): "Put an Energy attached to
    # this Pokémon into your hand."
    # =================================================================== #

    # --- 2d. POSITIVE: exactly one attached Energy is returned to hand (the
    # effect itself, called directly). ---
    st, a, b = fresh_state(db)
    chien = InPlayPokemon(card=db.get("Chien-Pao"))
    e1 = db.get("Basic Water Energy")
    e2 = db.get("Basic Fire Energy")
    chien.energy = [e1, e2]
    a.active = chien
    hand_before = len(a.hand)
    ctx = fx.EffectContext(state=st, me=a, opp=b, source=chien, db=db, rng=st.rng)
    fx._icicle_loop(ctx)
    check(len(chien.energy) == 1 and chien.energy[0] is e1,
          "Icicle Loop should return exactly ONE attached Energy, leaving 1 behind")
    check(len(a.hand) == hand_before + 1 and a.hand[-1] is e2,
          "the returned Energy should land in hand")

    # --- 2e. POSITIVE, full attack resolution: fixed 120 damage AND the energy
    # return both fire from a single attack use. ---
    st, a, b = fresh_state(db)
    chien = InPlayPokemon(card=db.get("Chien-Pao"))
    chien.energy = [db.get("Basic Water Energy"), db.get("Basic Water Energy"),
                    db.get("Basic Fire Energy")]
    a.active = chien
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))    # 320 HP, no weakness
    st.active_index = 0
    il_i = next(i for i, atk in enumerate(chien.card.attacks)
                if atk.name == "Icicle Loop")
    game._resolve_attack(st, il_i)
    check(b.active is not None and b.active.damage == 120,
          f"Icicle Loop should deal exactly 120, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(len(chien.energy) == 2,
          f"Icicle Loop should return exactly 1 of 3 attached Energy, "
          f"{len(chien.energy)} remain")
    check(len(a.hand) == 1, "the returned Energy should be in hand after the attack")

    # --- 2f. NEGATIVE: no attached Energy -> no crash, no hand change. ---
    st, a, b = fresh_state(db)
    chien = InPlayPokemon(card=db.get("Chien-Pao"))          # no energy attached
    a.active = chien
    hand_before = len(a.hand)
    ctx = fx.EffectContext(state=st, me=a, opp=b, source=chien, db=db, rng=st.rng)
    fx._icicle_loop(ctx)
    check(len(a.hand) == hand_before,
          "Icicle Loop with no attached Energy should be a no-op")

    # =================================================================== #
    # ALAKAZAM (MEG/56)
    # Ability "Psychic Draw" (pool text): "Once during your turn, when you play
    # this Pokémon from your hand to evolve 1 of your Pokémon, you may use this
    # Ability. Draw 3 cards."
    # =================================================================== #

    # --- 3a. POSITIVE: a normal evolve-from-hand (Kadabra -> Alakazam) draws 3. ---
    st, a, b = fresh_state(db)
    a.turns_taken = 2
    kadabra_mon = InPlayPokemon(card=db.get("Kadabra"))
    a.active = kadabra_mon
    a.hand = [db.get("Alakazam")]
    a.deck = [db.get("Basic Fire Energy")] * 10
    game.apply_action(st, game.Action(kind="evolve", hand_index=0, target_index=-1))
    check(a.active.card.name == "Alakazam", "evolve should install Alakazam")
    check(len(a.hand) == 3,
          f"Psychic Draw should draw exactly 3 on a normal evolve, got {len(a.hand)}")

    # --- 3b. POSITIVE: Rare Candy (Abra -> Alakazam, skipping Kadabra) is ALSO
    # "playing this Pokémon from your hand to evolve" -> also draws 3. ---
    st, a, b = fresh_state(db)
    a.turns_taken = 2
    abra_mon = InPlayPokemon(card=db.get("Abra"))       # in play, not played this turn
    a.active = abra_mon
    a.hand = [db.get("Alakazam")]
    a.deck = [db.get("Basic Fire Energy")] * 10
    ctx = fx.EffectContext(state=st, me=a, opp=b, db=db, rng=st.rng)
    did = fx._rare_candy(ctx)
    check(did, "Rare Candy should succeed evolving Abra straight to Alakazam")
    check(a.active.card.name == "Alakazam", "Rare Candy should install Alakazam")
    check(len(a.hand) == 3,
          f"Psychic Draw should also fire via Rare Candy, got hand={len(a.hand)}")

    # --- 3c. NEGATIVE: a normal Basic play does NOT fire Psychic Draw (the
    # on-evolve hook is a separate registry from ON_BENCH_TRIGGERS — Alakazam is
    # not registered there, so playing it to the bench draws nothing). ---
    st, a, b = fresh_state(db)
    a.hand = [db.get("Alakazam")]
    a.deck = [db.get("Basic Fire Energy")] * 10
    st.active_index = 0
    game.apply_action(st, game.Action(kind="play_basic", hand_index=0))
    check(any(m.card.name == "Alakazam" for m in a.bench),
          "Alakazam should have been benched")
    check(len(a.hand) == 0,
          f"Psychic Draw must NOT fire on a normal Basic play, got hand={len(a.hand)}")

    # --- 3d. NEGATIVE: retreat does not fire Psychic Draw (no card is played from
    # hand during a retreat). ---
    st, a, b = fresh_state(db)
    alakazam_mon = InPlayPokemon(card=db.get("Alakazam"))
    a.active = alakazam_mon
    bench_mon = InPlayPokemon(card=db.get("Dreepy"))
    a.bench = [bench_mon]
    a.deck = [db.get("Basic Fire Energy")] * 10
    hand_before = len(a.hand)     # 0
    game.apply_action(st, game.Action(kind="retreat", target_index=0))
    check(a.active.card.name == "Dreepy" and
          any(m.card.name == "Alakazam" for m in a.bench),
          "retreat should swap active/bench normally")
    check(len(a.hand) == hand_before,
          f"Psychic Draw must NOT fire on retreat, got hand={len(a.hand)}")

    # =================================================================== #
    # Attack "Powerful Hand" [P] "" (pool text): "Place 2 damage counters on your
    # opponent's Active Pokémon for each card in your hand."
    # =================================================================== #

    # --- 3e. Hand size 0 -> 0 counters placed. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Alakazam"))
    a.hand = []
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    ph_i = next(i for i, atk in enumerate(a.active.card.attacks)
                if atk.name == "Powerful Hand")
    game._resolve_attack(st, ph_i)
    check(b.active is not None and b.active.damage == 0,
          f"Powerful Hand with an empty hand should place 0 counters (2*0), "
          f"got {b.active.damage if b.active else 'KO'}")

    # --- 3f. Hand size 5 -> 2*5=10 counters = 100 damage. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Alakazam"))
    a.hand = [db.get("Basic Fire Energy")] * 5
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    game._resolve_attack(st, ph_i)
    check(b.active is not None and b.active.damage == 100,
          f"Powerful Hand with 5 cards in hand should place 2*5=10 counters = 100, "
          f"got {b.active.damage if b.active else 'KO'}")

    # --- 3g. Powerful Hand uses place_counters (NOT Weakness-scaled attack
    # damage): Meditite is weak to Psychic x2 (Alakazam's own type), but the
    # counters must NOT be doubled -- 2 cards -> 4 counters = 40, not 80. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Alakazam"))
    a.hand = [db.get("Basic Fire Energy")] * 2
    b.active = InPlayPokemon(card=db.get("Meditite"))     # weak to Psychic x2
    st.active_index = 0
    game._resolve_attack(st, ph_i)
    check(b.active is not None and b.active.damage == 40,
          f"Powerful Hand must place raw counters with NO Weakness (2*2=4 -> 40, "
          f"not 80 despite Meditite's Psychic weakness), got "
          f"{b.active.damage if b.active else 'KO'}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Lillie's Clefairy ex (Fairy Zone + Full Moon Rondo), Chien-Pao "
          "(Snow Sink + Icicle Loop), and Alakazam (Psychic Draw + Powerful Hand) "
          "all hold, including the negative/suppression cases.")


if __name__ == "__main__":
    main()
