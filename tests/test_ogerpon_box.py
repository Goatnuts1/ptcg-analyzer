#!/usr/bin/env python3
"""
test_ogerpon_box.py — Wellspring Mask Ogerpon ex (Tera bench-immunity chokepoint,
"Sob" can't-retreat rider, "Torrential Pump" shuffle/bench-spread), Pecharunt
non-ex ("Poison Chain"), and Chi-Yu ("Allure" / "Ground Melter"). Card text
quoted from data/standard_pool.json (cross-checked against limitlesstcg.com per
implementer notes).

Covers:
  - Wellspring Mask Ogerpon ex (sv6-64, Basic Water/Tera/ex, 210 HP): the
    Tera bench-immunity rule ("As long as this Pokémon is on your Bench,
    prevent all damage done to this Pokémon by attacks (both yours and your
    opponent's)."), which is derived FOR FREE from the existing subtype-keyed
    chokepoint in apply_attack_damage — no new ability code exists for it, so
    this file asserts the behavior, not a specific function.
  - "Sob" [Colorless]: "20 damage. During your opponent's next turn, the
    Defending Pokémon can't retreat." — same one-turn pending_cant_retreat
    rider mechanism as Dusknoir's Shadow Bind.
  - "Torrential Pump" [Water+Colorless+Colorless]: "100 damage. You may
    shuffle 3 Energy attached to this Pokémon into your deck. If you do, this
    attack also does 120 damage to 1 of your opponent's Benched Pokémon.
    (Don't apply Weakness and Resistance for Benched Pokémon.)" — v0 always
    takes the shuffle when there's a benched target (per this engine's
    "auto-take the beneficial branch" convention), never when there isn't.
  - Pecharunt non-ex (svp-129, Basic Darkness, 80 HP) — confirmed a distinct
    pool entry from "Pecharunt ex" (sv6pt5-39, Basic/ex, 190 HP).
    "Poison Chain" [Darkness+Colorless]: "10 damage. Your opponent's Active
    Pokémon is now Poisoned. During your opponent's next turn, that Pokémon
    can't retreat." — Poison itself is NOT modeled in this engine (disclosed
    v0 gap, same class as Frogadier's Numbing Water); the can't-retreat rider
    IS modeled and is the only behavior asserted here.
  - Chi-Yu (sv6-39, Basic Fire, 110 HP). "Allure" [Colorless]: "Draw 2 cards."
    (no damage). "Ground Melter" [Fire+Colorless]: "60+ damage. If a Stadium
    is in play, this attack does 60 more damage. Then, discard that Stadium."

Run from project root:  python3 tests/test_ogerpon_box.py
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
    # WELLSPRING MASK OGERPON EX (sv6-64, Basic Water/Tera/ex, 210 HP,
    # Weakness Lightning x2, Retreat 1)
    # =================================================================== #

    ogerpon_card = db.get("Wellspring Mask Ogerpon ex")
    check(ogerpon_card.hp == 210, f"expected 210 HP, got {ogerpon_card.hp}")
    check(tuple(ogerpon_card.types) == ("Water",),
          f"expected Water type, got {ogerpon_card.types}")
    check(set(ogerpon_card.subtypes) >= {"Basic", "Tera", "ex"},
          f"expected subtypes to include Basic/Tera/ex, got {ogerpon_card.subtypes}")
    check(any(w == ("Lightning", "×2") for w in ogerpon_card.weaknesses),
          f"expected Weak to Lightning x2, got {ogerpon_card.weaknesses}")
    check(ogerpon_card.retreat_cost == 1,
          f"expected Retreat Cost 1, got {ogerpon_card.retreat_cost}")

    # --- 1a. TERA BENCH-IMMUNITY (rules text): "As long as this Pokémon is on
    # your Bench, prevent all damage done to this Pokémon by attacks (both
    # yours and your opponent's)." A benched Wellspring Ogerpon ex takes 0
    # from an attack, via the existing subtype-keyed chokepoint (no new
    # ability code — this is asserting the FREE behavior). ---
    st, a, b = fresh_state(db)
    bench_ogerpon = InPlayPokemon(card=ogerpon_card)
    a.active = InPlayPokemon(card=db.get("Dwebble"))
    a.bench = [bench_ogerpon]
    dealt = fx.apply_attack_damage(ctx_for(st, b, a), bench_ogerpon, 100, owner=a)
    check(dealt == 0, f"benched Wellspring Ogerpon ex must take 0 damage from an "
                       f"attack, got dealt={dealt}")
    check(bench_ogerpon.damage == 0,
          f"benched Wellspring Ogerpon ex's damage counter must stay at 0, got "
          f"{bench_ogerpon.damage}")

    # --- 1b. NEGATIVE / contrast: the SAME card, when it's the ACTIVE (not on
    # the Bench), takes damage normally — the immunity is bench-only. ---
    st, a, b = fresh_state(db)
    active_ogerpon = InPlayPokemon(card=ogerpon_card)
    a.active = active_ogerpon
    dealt2 = fx.apply_attack_damage(ctx_for(st, b, a), active_ogerpon, 100, owner=a)
    check(dealt2 == 100,
          f"an ACTIVE Wellspring Ogerpon ex must take damage normally (immunity is "
          f"bench-only), got dealt={dealt2}")
    check(active_ogerpon.damage == 100,
          f"active Wellspring Ogerpon ex's damage counter should be 100, got "
          f"{active_ogerpon.damage}")

    # --- 1c. NEGATIVE: a non-Tera Pokémon on the bench gets NO such immunity
    # (proving 1a isn't just "benched Pokémon never take damage"). ---
    st, a, b = fresh_state(db)
    bench_dwebble = InPlayPokemon(card=db.get("Dwebble"))     # plain Basic, no Tera
    a.active = InPlayPokemon(card=db.get("Crustle"))
    a.bench = [bench_dwebble]
    check("Tera" not in bench_dwebble.card.subtypes, "setup: Dwebble must not be Tera")
    dealt3 = fx.apply_attack_damage(ctx_for(st, b, a), bench_dwebble, 50, owner=a)
    check(dealt3 == 50,
          f"a benched NON-Tera Pokémon must take damage normally, got dealt={dealt3}")

    # =================================================================== #
    # Attack "Sob" [Colorless] — pool text: "20 damage. During your opponent's
    # next turn, the Defending Pokémon can't retreat."
    # =================================================================== #

    # --- 2a. POSITIVE: 20 engine-applied damage, and the effect sets the
    # opponent's pending_cant_retreat flag immediately after resolution. ---
    st, a, b = fresh_state(db)
    ogerpon = InPlayPokemon(card=ogerpon_card)
    a.active = ogerpon
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))    # 320 HP
    st.active_index = 0
    sob_i = next(i for i, atk in enumerate(ogerpon.card.attacks) if atk.name == "Sob")
    check(b.pending_cant_retreat is False, "setup: pending_cant_retreat should start False")
    game._resolve_attack(st, sob_i)
    check(b.active is not None and b.active.damage == 20,
          f"Sob should deal exactly 20 damage, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(b.pending_cant_retreat is True,
          "Sob must set the opponent's pending_cant_retreat flag")
    check(b.cant_retreat is False,
          "pending_cant_retreat must NOT immediately be live cant_retreat — it's "
          "promoted at the start of the opponent's NEXT turn")

    # --- 2b. Promotion: at the start of the opponent's (B's) next turn,
    # pending_cant_retreat becomes the live cant_retreat flag, and retreat is
    # actually gated off in legal-action generation. ---
    st.active_index = 1                  # simulate the turn handing to B
    game.start_turn(st)
    check(b.cant_retreat is True,
          "start_turn must promote pending_cant_retreat to cant_retreat")
    check(b.pending_cant_retreat is False,
          "start_turn must clear pending_cant_retreat once promoted")
    b.bench = [InPlayPokemon(card=db.get("Dwebble"))]
    b.active.energy = [db.get("Basic Fire Energy")] * 5     # plenty to afford retreat
    actions = game.legal_actions(st)
    check(not any(act.kind == "retreat" for act in actions),
          "legal_actions must NOT offer 'retreat' while cant_retreat is True")

    # --- 2c. One-turn expiration: on B's turn AFTER that, cant_retreat clears
    # and retreat becomes legal again. ---
    st.active_index = 0                  # hand back to A (a filler turn)
    game.start_turn(st)
    st.active_index = 1                  # back to B — the rider should be gone
    game.start_turn(st)
    check(b.cant_retreat is False,
          "cant_retreat must expire after exactly one of the opponent's turns")
    actions2 = game.legal_actions(st)
    check(any(act.kind == "retreat" for act in actions2),
          "legal_actions must offer 'retreat' again once cant_retreat has expired")

    # --- 2d. NEGATIVE: a different attack (Torrential Pump) does NOT set
    # pending_cant_retreat — the rider is Sob-specific. ---
    st, a, b = fresh_state(db)
    ogerpon2 = InPlayPokemon(card=ogerpon_card)
    ogerpon2.energy = [db.get("Basic Water Energy"), db.get("Basic Fire Energy"),
                       db.get("Basic Fire Energy")]
    a.active = ogerpon2
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    tp_i = next(i for i, atk in enumerate(ogerpon2.card.attacks)
               if atk.name == "Torrential Pump")
    game._resolve_attack(st, tp_i)
    check(b.pending_cant_retreat is False,
          "Torrential Pump must NOT set pending_cant_retreat (that's Sob's rider)")

    # =================================================================== #
    # Attack "Torrential Pump" [Water+Colorless+Colorless] — pool text: "100
    # damage. You may shuffle 3 Energy attached to this Pokémon into your
    # deck. If you do, this attack also does 120 damage to 1 of your
    # opponent's Benched Pokémon. (Don't apply Weakness and Resistance for
    # Benched Pokémon.)"
    # =================================================================== #

    # --- 3a. POSITIVE: 100 to the Active (engine-applied); with a benched
    # target present and >=3 Energy attached, v0 auto-takes the shuffle: 3
    # Energy leave the attacker into the deck, and 120 lands on the (single)
    # benched Pokémon. ---
    st, a, b = fresh_state(db)
    ogerpon3 = InPlayPokemon(card=ogerpon_card)
    e1, e2, e3 = (db.get("Basic Water Energy"), db.get("Basic Fire Energy"),
                 db.get("Basic Fire Energy"))
    ogerpon3.energy = [e1, e2, e3]
    a.active = ogerpon3
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))     # 320 HP
    bench_mon = InPlayPokemon(card=db.get("Dwebble"))
    b.bench = [bench_mon]
    st.active_index = 0
    tp_i2 = next(i for i, atk in enumerate(ogerpon3.card.attacks)
                if atk.name == "Torrential Pump")
    deck_len_before = len(a.deck)
    game._resolve_attack(st, tp_i2)
    check(b.active is not None and b.active.damage == 100,
          f"Torrential Pump should deal 100 to the Active, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(ogerpon3.energy_count() == 0,
          f"the shuffle should remove all 3 attached Energy, got "
          f"{ogerpon3.energy_count()} remaining")
    check(len(a.deck) == deck_len_before + 3,
          f"the 3 shuffled Energy should land back in the attacker's deck, "
          f"expected {deck_len_before + 3}, got {len(a.deck)}")
    check(bench_mon.damage == 120,
          f"Torrential Pump's shuffle-triggered bonus should deal 120 to the "
          f"benched Pokémon, got {bench_mon.damage}")

    # --- 3b. Bench damage does NOT apply Weakness: Ponyta (Weak Water x2) on
    # the bench still only takes the flat 120, not 240 (attacker is Water). ---
    st, a, b = fresh_state(db)
    ogerpon4 = InPlayPokemon(card=ogerpon_card)
    ogerpon4.energy = [db.get("Basic Water Energy"), db.get("Basic Fire Energy"),
                       db.get("Basic Fire Energy")]
    a.active = ogerpon4
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    ponyta = InPlayPokemon(card=db.get("Ponyta"))              # Fire, Weak Water x2
    b.bench = [ponyta]
    st.active_index = 0
    tp_i3 = next(i for i, atk in enumerate(ogerpon4.card.attacks)
                if atk.name == "Torrential Pump")
    game._resolve_attack(st, tp_i3)
    check(ponyta.damage == 120,
          f"Torrential Pump's bench hit must NOT apply Weakness (flat 120 even "
          f"though Ponyta is Weak to Water x2), got {ponyta.damage}")

    # --- 3c. NEGATIVE: no Benched Pokémon -> only the 100 main hit; v0 keeps
    # the Energy attached (never strips the attacker "for nothing"). ---
    st, a, b = fresh_state(db)
    ogerpon5 = InPlayPokemon(card=ogerpon_card)
    ogerpon5.energy = [db.get("Basic Water Energy"), db.get("Basic Fire Energy"),
                       db.get("Basic Fire Energy")]
    a.active = ogerpon5
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.bench = []
    st.active_index = 0
    tp_i4 = next(i for i, atk in enumerate(ogerpon5.card.attacks)
                if atk.name == "Torrential Pump")
    game._resolve_attack(st, tp_i4)
    check(b.active is not None and b.active.damage == 100,
          f"Torrential Pump with an empty bench should still deal 100 to the "
          f"Active, got {b.active.damage if b.active else 'KO'}")
    check(ogerpon5.energy_count() == 3,
          f"with no benched target, the shuffle must NOT happen (Energy stays "
          f"attached), got {ogerpon5.energy_count()} remaining")

    # --- 3d. NEGATIVE: fewer than 3 Energy attached (isolated effect call,
    # bypassing the cost-gated game._resolve_attack path) -> no shuffle even
    # though a benched target exists. ---
    st, a, b = fresh_state(db)
    ogerpon6 = InPlayPokemon(card=ogerpon_card)
    ogerpon6.energy = [db.get("Basic Water Energy"), db.get("Basic Fire Energy")]  # only 2
    a.active = ogerpon6
    bench_mon2 = InPlayPokemon(card=db.get("Dwebble"))
    b.bench = [bench_mon2]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    fx._torrential_pump(ctx_for(st, a, b, source=ogerpon6))
    check(ogerpon6.energy_count() == 2,
          f"with only 2 Energy attached, the shuffle must not fire, got "
          f"{ogerpon6.energy_count()} remaining")
    check(bench_mon2.damage == 0,
          f"with only 2 Energy attached, no bench damage should be dealt, got "
          f"{bench_mon2.damage}")

    # =================================================================== #
    # PECHARUNT (non-ex) — svp-129, Basic Darkness, 80 HP. Confirmed distinct
    # from "Pecharunt ex" (sv6pt5-39, Basic/ex, 190 HP).
    # =================================================================== #

    pecharunt_card = db.get("Pecharunt")
    pecharunt_ex_card = db.get("Pecharunt ex")
    check(pecharunt_card.hp == 80, f"expected 80 HP, got {pecharunt_card.hp}")
    check(tuple(pecharunt_card.types) == ("Darkness",),
          f"expected Darkness type, got {pecharunt_card.types}")
    check("ex" not in pecharunt_card.subtypes,
          f"non-ex Pecharunt must NOT carry the 'ex' subtype, got "
          f"{pecharunt_card.subtypes}")
    check(pecharunt_card.hp != pecharunt_ex_card.hp
          and "ex" in pecharunt_ex_card.subtypes,
          "Pecharunt and Pecharunt ex must be genuinely distinct pool entries "
          "(different HP, ex only on the ex version)")
    check(len(pecharunt_card.attacks) == 1
          and pecharunt_card.attacks[0].name == "Poison Chain",
          f"non-ex Pecharunt should have exactly one attack, Poison Chain, got "
          f"{[a.name for a in pecharunt_card.attacks]}")

    # --- 4a. POSITIVE: "Poison Chain" — "10 damage. Your opponent's Active
    # Pokémon is now Poisoned. During your opponent's next turn, that Pokémon
    # can't retreat." Poison itself is NOT modeled (disclosed gap); only the
    # can't-retreat rider and the 10 damage are asserted. ---
    st, a, b = fresh_state(db)
    pecharunt = InPlayPokemon(card=pecharunt_card)
    a.active = pecharunt
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    st.active_index = 0
    pc_i = next(i for i, atk in enumerate(pecharunt.card.attacks)
               if atk.name == "Poison Chain")
    check(b.pending_cant_retreat is False, "setup: pending_cant_retreat should start False")
    game._resolve_attack(st, pc_i)
    check(b.active is not None and b.active.damage == 10,
          f"Poison Chain should deal exactly 10 damage, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(b.pending_cant_retreat is True,
          "Poison Chain must set the opponent's pending_cant_retreat flag")

    # --- 4b. NEGATIVE: without the attack firing, pending_cant_retreat stays
    # False (sanity contrast — the flag isn't just always True). ---
    st2, a2, b2 = fresh_state(db)
    check(b2.pending_cant_retreat is False,
          "a fresh PlayerState must start with pending_cant_retreat False")

    # =================================================================== #
    # CHI-YU (sv6-39, Basic Fire, 110 HP, Weakness Water x2, Retreat 1)
    # =================================================================== #

    chiyu_card = db.get("Chi-Yu")
    check(chiyu_card.hp == 110, f"expected 110 HP, got {chiyu_card.hp}")
    check(tuple(chiyu_card.types) == ("Fire",),
          f"expected Fire type, got {chiyu_card.types}")
    check(any(w == ("Water", "×2") for w in chiyu_card.weaknesses),
          f"expected Weak to Water x2, got {chiyu_card.weaknesses}")

    # --- 5a. POSITIVE: "Allure" [Colorless] — "Draw 2 cards." (no damage) ---
    st, a, b = fresh_state(db)
    chiyu = InPlayPokemon(card=chiyu_card)
    a.active = chiyu
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.deck = [db.get("Dwebble") for _ in range(10)]
    hand_before = len(a.hand)
    st.active_index = 0
    allure_i = next(i for i, atk in enumerate(chiyu.card.attacks) if atk.name == "Allure")
    game._resolve_attack(st, allure_i)
    check(len(a.hand) == hand_before + 2,
          f"Allure should draw exactly 2 cards, hand went from {hand_before} to "
          f"{len(a.hand)}")
    check(b.active is not None and b.active.damage == 0,
          f"Allure must deal 0 damage, got {b.active.damage if b.active else 'KO'}")

    # --- 5b. POSITIVE: "Ground Melter" [Fire+Colorless] with NO Stadium in
    # play — flat 60, no crash, nothing discarded. ---
    st, a, b = fresh_state(db)
    chiyu2 = InPlayPokemon(card=chiyu_card)
    a.active = chiyu2
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))     # 320 HP, no Weakness
    st.stadium = None
    st.active_index = 0
    gm_i = next(i for i, atk in enumerate(chiyu2.card.attacks)
               if atk.name == "Ground Melter")
    game._resolve_attack(st, gm_i)
    check(b.active is not None and b.active.damage == 60,
          f"Ground Melter with no Stadium in play should deal exactly 60, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(st.stadium is None, "no Stadium was in play, so none should be discarded")

    # --- 5c. POSITIVE: "Ground Melter" WITH a Stadium in play — +60 more
    # (total 120), and the Stadium is discarded afterward. ---
    st, a, b = fresh_state(db)
    chiyu3 = InPlayPokemon(card=chiyu_card)
    a.active = chiyu3
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    stadium_card = db.get("Nighttime Mine")
    st.stadium = stadium_card
    st.stadium_owner = 0
    st.active_index = 0
    gm_i2 = next(i for i, atk in enumerate(chiyu3.card.attacks)
                if atk.name == "Ground Melter")
    game._resolve_attack(st, gm_i2)
    check(b.active is not None and b.active.damage == 120,
          f"Ground Melter with a Stadium in play should deal 60+60=120, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(st.stadium is None,
          "Ground Melter must discard the Stadium after landing the boosted hit")
    check(stadium_card in a.discard,
          "the discarded Stadium should land in the attack-user's discard pile "
          "(the Stadium's owner, per implementation)")

    # --- 5d. Weakness applies to the WHOLE Ground Melter total (own once, not
    # per-component): Pineco (Grass, Weak Fire x2) with a Stadium in play
    # takes (60+60)*2 = 240, not 60*2+60=180 or some other partial double. ---
    st, a, b = fresh_state(db)
    chiyu4 = InPlayPokemon(card=chiyu_card)
    a.active = chiyu4
    pineco = InPlayPokemon(card=db.get("Pineco"))              # Grass, Weak Fire x2
    b.active = pineco
    st.stadium = db.get("Nighttime Mine")
    st.stadium_owner = 0
    st.active_index = 0
    gm_i3 = next(i for i, atk in enumerate(chiyu4.card.attacks)
                if atk.name == "Ground Melter")
    game._resolve_attack(st, gm_i3)
    check(pineco.damage == 240,
          f"Ground Melter's full (60+60) total must be weakness-doubled once "
          f"against Fire-weak Pineco, expected 240, got {pineco.damage}")

    # --- 5e. NEGATIVE: Ground Melter must not double-apply its own base (it
    # owns its damage via ATTACK_EFFECT_OWNS_DAMAGE / damage_suffix '+' path,
    # so the engine's automatic base-damage application must be 0). Re-assert
    # the no-Stadium flat-60 case against a fresh, non-Weak defender to catch
    # any accidental double-hit (which would show up as 120 here). ---
    st, a, b = fresh_state(db)
    chiyu5 = InPlayPokemon(card=chiyu_card)
    a.active = chiyu5
    fresh_dragapult = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = fresh_dragapult
    st.stadium = None
    st.active_index = 0
    gm_i4 = next(i for i, atk in enumerate(chiyu5.card.attacks)
                if atk.name == "Ground Melter")
    game._resolve_attack(st, gm_i4)
    check(fresh_dragapult.damage == 60,
          f"Ground Melter must own its damage exactly once (60, no Stadium), not "
          f"double-apply a separate printed base on top of the effect, got "
          f"{fresh_dragapult.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_ogerpon_box.py: all checks passed (Wellspring Mask Ogerpon ex Tera "
          "bench-immunity + Sob + Torrential Pump, Pecharunt non-ex Poison Chain, "
          "Chi-Yu Allure + Ground Melter)")


if __name__ == "__main__":
    main()
