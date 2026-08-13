#!/usr/bin/env python3
"""
test_clefairy.py — assert Lillie's Clefairy ex (JTG/56 pool text below) does
EXACTLY what the card says, plus its two v0-landmark siblings from the same
implementation pass: Chien-Pao (SSP/56) and Alakazam (MEG/56), whose triggers
(on-bench / on-evolve) and hooks Lillie's Clefairy ex's Fairy Zone recon leaned on.

Card text (verified this session, quoted at each assertion site):

  CARD 1 — Lillie's Clefairy ex (JTG/56, Basic Psychic ex, 190 HP):
    Ability "Fairy Zone": "The Weakness of each of your opponent's Dragon
      Pokémon in play is now Psychic. (Apply Weakness as x2.)" — passive,
      continuous, board-wide (Active + Bench), non-self.
    Attack "Full Moon Rondo" [P][C] 20+: "This attack does 20 more damage for
      each Benched Pokémon (both yours and your opponent's)."

  CARD 2 — Chien-Pao (SSP/56, Basic Water, 120 HP):
    Ability "Snow Sink": "When you play this Pokémon from your hand to your
      Bench, you may discard a Stadium in play." — on-bench-from-hand trigger.
    Attack "Icicle Loop" [W][W][C] 120: "Put an Energy attached to this
      Pokémon into your hand."

  CARD 3 — Alakazam (MEG/56, Stage 2 Psychic, 140 HP):
    Ability "Psychic Draw": "When you play this Pokémon from your hand to
      evolve 1 of your Pokémon, you may draw 3 cards." — on-evolve trigger.
    Attack "Powerful Hand" [P]: "Place 2 damage counters on your opponent's
      Active Pokémon for each card in your hand."

Run from project root:  python3 tests/test_clefairy.py
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
    st.phase = Phase.MAIN
    a.turns_taken = b.turns_taken = 5
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
    # LILLIE'S CLEFAIRY EX — Fairy Zone
    # "The Weakness of each of your opponent's Dragon Pokémon in play is now
    #  Psychic. (Apply Weakness as x2.)"
    # =================================================================== #

    # --- 1a. POSITIVE: with Clefairy ex on A's BENCH (not Active — proves
    # board-wide, not Active-only scoping), B's Dreepy (Dragon, no printed
    # Weakness at all) takes x2 from a Psychic-type attacker. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Kadabra"))            # Psychic attacker
    a.bench = [InPlayPokemon(card=db.get("Lillie's Clefairy ex"))]
    dreepy = InPlayPokemon(card=db.get("Dreepy"))                # Dragon, no printed Weak
    b.active = dreepy
    ctx = ctx_for(st, me=a, opp=b, source=a.active)
    dealt = fx.apply_attack_damage(ctx, dreepy, 50, owner=b, source=a.active)
    check(dealt == 100 and dreepy.damage == 100,
          f"Fairy Zone should rewrite Dreepy's Weakness to Psychic and double a "
          f"Psychic attacker's damage (50->100), got dealt={dealt}")

    # --- 1b. NEGATIVE control: WITHOUT any Clefairy ex in play, the same
    # Psychic attack on the same Dreepy does NOT double (Dreepy has no printed
    # Weakness at all). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Kadabra"))
    dreepy = InPlayPokemon(card=db.get("Dreepy"))
    b.active = dreepy
    ctx = ctx_for(st, me=a, opp=b, source=a.active)
    dealt = fx.apply_attack_damage(ctx, dreepy, 50, owner=b, source=a.active)
    check(dealt == 50 and dreepy.damage == 50,
          f"without Fairy Zone, Dreepy (no printed Weakness) should take exactly "
          f"50, got dealt={dealt}")

    # --- 1c. NEGATIVE: Fairy Zone does nothing to a non-Dragon opponent
    # Pokémon, even with Clefairy ex in play — a Psychic attack on Pikachu ex
    # (Lightning, weak to Fighting only) must NOT double. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Kadabra"))
    a.bench = [InPlayPokemon(card=db.get("Lillie's Clefairy ex"))]
    pika = InPlayPokemon(card=db.get("Pikachu ex"))              # Lightning, not Dragon
    b.active = pika
    ctx = ctx_for(st, me=a, opp=b, source=a.active)
    dealt = fx.apply_attack_damage(ctx, pika, 50, owner=b, source=a.active)
    check(dealt == 50 and pika.damage == 50,
          f"Fairy Zone must NOT touch a non-Dragon opponent Pokémon, got dealt={dealt}")

    # --- 1d. NEGATIVE: Fairy Zone only rewrites Weakness, and only helps a
    # PSYCHIC-type attacker — a non-Psychic attacker vs. the same Dragon
    # defender under Fairy Zone deals no bonus (its own type isn't Psychic, so
    # the rewritten Weakness doesn't match it). ---
    st, a, b = fresh_state(db)
    non_psychic = InPlayPokemon(card=db.get("Pikachu ex"))       # Lightning attacker
    a.active = non_psychic
    a.bench = [InPlayPokemon(card=db.get("Lillie's Clefairy ex"))]
    dreepy = InPlayPokemon(card=db.get("Dreepy"))
    b.active = dreepy
    ctx = ctx_for(st, me=a, opp=b, source=non_psychic)
    dealt = fx.apply_attack_damage(ctx, dreepy, 50, owner=b, source=non_psychic)
    check(dealt == 50 and dreepy.damage == 50,
          f"Fairy Zone's rewritten Weakness only benefits a Psychic attacker; a "
          f"Lightning attacker should deal exactly 50, got dealt={dealt}")

    # --- 1e. Ability suppression on the Clefairy ex HOLDER disables Fairy
    # Zone (the holder is a third party to this attack, unlike the wall
    # abilities which check the defender). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Kadabra"))
    a.bench = [InPlayPokemon(card=db.get("Lillie's Clefairy ex"))]
    dreepy = InPlayPokemon(card=db.get("Dreepy"))
    b.active = dreepy
    ctx = ctx_for(st, me=a, opp=b, source=a.active)
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        dealt = fx.apply_attack_damage(ctx, dreepy, 50, owner=b, source=a.active)
        check(dealt == 50 and dreepy.damage == 50,
              f"suppressing the Clefairy ex holder should disable Fairy Zone, "
              f"got dealt={dealt}")
    finally:
        fx.ability_suppressed = orig_suppressed

    # =================================================================== #
    # LILLIE'S CLEFAIRY EX — Full Moon Rondo
    # "This attack does 20 more damage for each Benched Pokémon (both yours
    #  and your opponent's)." (20 base + 20/bench, both sides)
    # =================================================================== #

    # --- 1f. Zero benched on both sides -> exactly the 20 base, nothing more.
    # (Defender is Pikachu ex — NOT Dragon — so Clefairy ex's OWN Fairy Zone
    # can't confound this with a Weakness double against its own attack.) ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))    # 200 HP, Lightning, not Dragon
    st.active_index = 0
    fmr_i = next(i for i, atk in enumerate(a.active.card.attacks)
                 if atk.name == "Full Moon Rondo")
    game._resolve_attack(st, fmr_i)
    check(b.active is not None and b.active.damage == 20,
          f"Full Moon Rondo with 0 benched on both sides should deal exactly the "
          f"20 base, got {b.active.damage if b.active else 'KO'}")

    # --- 1g. Scaling: 2 benched for the attacker + 3 for the defender ->
    # 20 + 20*5 = 120. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    a.bench = [InPlayPokemon(card=db.get("Dreepy")), InPlayPokemon(card=db.get("Dreepy"))]
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))      # 200 HP, not Dragon
    b.bench = [InPlayPokemon(card=db.get("Dreepy")) for _ in range(3)]
    st.active_index = 0
    game._resolve_attack(st, fmr_i)
    check(b.active is not None and b.active.damage == 120,
          f"Full Moon Rondo with 2+3=5 benched should deal 20+20*5=120, got "
          f"{b.active.damage if b.active else 'KO'}")

    # --- 1h. Scaling counts ONLY the attacker's/defender's OWN benches (not
    # some other stray count) -> asymmetric bench sizes (1 vs 0) give
    # 20 + 20*1 = 40, not 20 (proves both sides are actually summed). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Lillie's Clefairy ex"))
    a.bench = [InPlayPokemon(card=db.get("Dreepy"))]
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))      # 200 HP, not Dragon
    st.active_index = 0
    game._resolve_attack(st, fmr_i)
    check(b.active is not None and b.active.damage == 40,
          f"Full Moon Rondo with 1 (attacker) + 0 (defender) benched should deal "
          f"20+20*1=40, got {b.active.damage if b.active else 'KO'}")

    # =================================================================== #
    # CHIEN-PAO — Snow Sink
    # "When you play this Pokémon from your hand to your Bench, you may
    #  discard a Stadium in play."
    # =================================================================== #

    # --- 2a. POSITIVE: benching Chien-Pao from hand while a Stadium is in
    # play discards it and clears state.stadium/stadium_owner. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.hand = [db.get("Chien-Pao")]
    stadium_card = db.get("Team Rocket's Watchtower")
    st.stadium = stadium_card
    st.stadium_owner = 1                          # owned by B, still discardable
    st.active_index = 0
    game.apply_action(st, game.Action("play_basic", hand_index=0))
    check(st.stadium is None and st.stadium_owner is None,
          "Snow Sink should clear the Stadium in play")
    check(stadium_card in b.discard,
          "the discarded Stadium should go to its OWNER's discard pile")

    # --- 2b. NEGATIVE: with no Stadium in play, benching Chien-Pao does
    # nothing extra (no crash, no stray discard). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.hand = [db.get("Chien-Pao")]
    st.stadium = None
    st.stadium_owner = None
    st.active_index = 0
    game.apply_action(st, game.Action("play_basic", hand_index=0))
    check(st.stadium is None and len(a.discard) == 0 and len(b.discard) == 0,
          "Snow Sink with no Stadium in play should be a no-op (no stray discard)")
    check(any(m.card.name == "Chien-Pao" for m in a.bench),
          "Chien-Pao should still be benched normally")

    # =================================================================== #
    # CHIEN-PAO — Icicle Loop
    # "Put an Energy attached to this Pokémon into your hand." (120 fixed base)
    # =================================================================== #

    st, a, b = fresh_state(db)
    chienpao = InPlayPokemon(card=db.get("Chien-Pao"))
    WATER = db.get("Basic Water Energy")
    chienpao.energy = [WATER, WATER, db.get("Basic Fire Energy")]
    a.active = chienpao
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))       # 320 HP, no printed Weak
    st.active_index = 0
    energy_before = len(chienpao.energy)
    hand_before = len(a.hand)
    il_i = next(i for i, atk in enumerate(chienpao.card.attacks)
                if atk.name == "Icicle Loop")
    game._resolve_attack(st, il_i)
    check(b.active is not None and b.active.damage == 120,
          f"Icicle Loop should deal exactly 120, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(len(chienpao.energy) == energy_before - 1,
          f"Icicle Loop should remove exactly 1 attached Energy, "
          f"left={len(chienpao.energy)}")
    check(len(a.hand) == hand_before + 1,
          f"Icicle Loop should add exactly 1 Energy to hand, hand={len(a.hand)}")

    # =================================================================== #
    # ALAKAZAM — Psychic Draw
    # "When you play this Pokémon from your hand to evolve 1 of your
    #  Pokémon, you may draw 3 cards."
    # =================================================================== #

    # --- 3a. POSITIVE: a normal evolve-from-hand (Kadabra -> Alakazam) draws
    # exactly 3. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Kadabra"))
    a.hand = [db.get("Alakazam")]
    a.deck = [db.get("Basic Fire Energy")] * 10
    hand_before = len(a.hand)     # counts the Alakazam itself, popped during evolve
    st.active_index = 0
    game.apply_action(st, game.Action("evolve", hand_index=0, target_index=-1))
    check(a.active.card.name == "Alakazam", "Kadabra should evolve into Alakazam")
    # the Alakazam card itself left the hand (-1), then Psychic Draw adds +3
    check(len(a.hand) == hand_before - 1 + 3,
          f"Psychic Draw should net hand -1(played)+3(drawn), got "
          f"{len(a.hand) - hand_before}")

    # --- 3b. Also fires via Rare Candy (Basic straight to Alakazam) — Rare
    # Candy is also "playing the Pokémon from hand to evolve." ---
    st, a, b = fresh_state(db)
    abra = InPlayPokemon(card=db.get("Abra"))
    abra.played_this_turn = False
    a.active = abra
    a.hand = [db.get("Rare Candy"), db.get("Alakazam")]
    a.deck = [db.get("Basic Fire Energy")] * 10
    st.active_index = 0
    rc_index = next(i for i, c in enumerate(a.hand) if c.name == "Rare Candy")
    game.apply_action(st, game.Action("play_trainer", hand_index=rc_index))
    check(a.active.card.name == "Alakazam",
          "Rare Candy should skip Kadabra straight to Alakazam")
    check(len(a.hand) == 0 + 3,
          f"Psychic Draw should also fire via Rare Candy (hand should hold "
          f"exactly the 3 drawn cards), got {len(a.hand)}")

    # --- 3c. NEGATIVE: a normal Basic play (bench a Basic from hand) does
    # NOT draw 3 — Psychic Draw is scoped to the evolve action only. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.hand = [db.get("Dreepy")]
    a.deck = [db.get("Basic Fire Energy")] * 10
    st.active_index = 0
    game.apply_action(st, game.Action("play_basic", hand_index=0))
    check(len(a.hand) == 0,
          f"benching a plain Basic must NOT trigger a draw-3, hand={len(a.hand)}")

    # --- 3d. NEGATIVE: retreating does NOT draw 3 either. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Alakazam"))     # already in play, no evolve
    bench_mon = InPlayPokemon(card=db.get("Dreepy"))
    a.bench = [bench_mon]
    a.hand = [db.get("Basic Fire Energy")] * 2
    a.deck = [db.get("Basic Fire Energy")] * 10
    st.active_index = 0
    hand_before = len(a.hand)
    game.apply_action(st, game.Action("retreat", target_index=0))
    check(a.active is bench_mon, "retreat should swap the Active as normal")
    check(len(a.hand) == hand_before,
          f"retreating must NOT trigger a draw-3, hand changed by "
          f"{len(a.hand) - hand_before}")

    # =================================================================== #
    # ALAKAZAM — Powerful Hand
    # "Place 2 damage counters on your opponent's Active Pokémon for each
    #  card in your hand."
    # =================================================================== #

    # --- 3e. Hand size 0 -> 0 counters, 0 damage. ---
    st, a, b = fresh_state(db)
    alakazam = InPlayPokemon(card=db.get("Alakazam"))
    a.active = alakazam
    a.hand = []
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    ph_i = next(i for i, atk in enumerate(alakazam.card.attacks)
                if atk.name == "Powerful Hand")
    game._resolve_attack(st, ph_i)
    check(b.active is not None and b.active.damage == 0,
          f"Powerful Hand with an empty hand should place 0 counters (0 dmg), "
          f"got {b.active.damage if b.active else 'KO'}")

    # --- 3f. Hand size 5 -> 2*5=10 counters = 100 damage. ---
    st, a, b = fresh_state(db)
    alakazam = InPlayPokemon(card=db.get("Alakazam"))
    a.active = alakazam
    a.hand = [db.get("Basic Fire Energy")] * 5
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))     # 320 HP, survives 100
    st.active_index = 0
    game._resolve_attack(st, ph_i)
    check(b.active is not None and b.active.damage == 100,
          f"Powerful Hand with a 5-card hand should place 2*5=10 counters "
          f"(100 dmg), got {b.active.damage if b.active else 'KO'}")

    # --- 3g. Powerful Hand places COUNTERS (via place_counters), not attack
    # damage — Weakness must NOT apply even against a Dragon defender under a
    # Fairy Zone that would double a Psychic attacker's ATTACK damage. ---
    st, a, b = fresh_state(db)
    alakazam = InPlayPokemon(card=db.get("Alakazam"))
    a.active = alakazam
    a.hand = [db.get("Basic Fire Energy")] * 3          # 2*3=6 counters -> 60 if unaffected
    a.bench = [InPlayPokemon(card=db.get("Lillie's Clefairy ex"))]  # would rewrite Weakness
    dreepy = InPlayPokemon(card=db.get("Dreepy"))        # Dragon, no printed Weakness
    b.active = dreepy
    st.active_index = 0
    game._resolve_attack(st, ph_i)
    check(dreepy.damage == 60,
          f"Powerful Hand's counters must NOT be doubled by Fairy Zone/Weakness "
          f"(expected 60, unaffected), got {dreepy.damage}")

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
