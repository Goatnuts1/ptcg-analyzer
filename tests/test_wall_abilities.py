#!/usr/bin/env python3
"""
test_wall_abilities.py — assert the passive "wall" abilities and their attached
attacks do EXACTLY what the card says (data/standard_pool.json quoted inline).

Covers:
  - Crustle:                    Mysterious Rock Inn + Superb Scissors
  - Milotic ex:                 Sparkling Scales + Hypno Splash (damage only —
                                 the Asleep rider is a documented engine limitation)
  - Cornerstone Mask Ogerpon ex: Cornerstone Stance + Demolish
  - Special Red Card:            ≤3-opponent-prizes gate + bottom-hand/draw-3 effect
  - Bloodmoon Ursaluna ex:        Seasoned Skill (Blood Moon Colorless discount)

Also asserts the negative cases: a wall does NOT block a non-matching attacker,
and ability suppression disables a wall / cost discount.

Run from project root:  python3 tests/test_wall_abilities.py
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
    # CRUSTLE
    # Ability "Mysterious Rock Inn" (pool text):
    #   "Prevent all damage done to this Pokémon by attacks from your
    #    opponent's Pokémon ex."
    # Attack "Superb Scissors" [G][C][C] 120 (pool text):
    #   "This attack's damage isn't affected by any effects on your
    #    opponent's Active Pokémon."
    # =================================================================== #

    # --- 1a. POSITIVE: an opponent's Pokémon ex's attack is fully prevented. ---
    st, a, b = fresh_state(db)
    crustle = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle
    ex_attacker = InPlayPokemon(card=db.get("Milotic ex"))     # ex, Water (no
    a.active = ex_attacker                                     # Fire-weakness noise)
    ctx = ctx_for(st, me=a, opp=b, source=ex_attacker)
    dealt = fx.apply_attack_damage(ctx, crustle, 120, owner=b, source=ex_attacker)
    check(dealt == 0 and crustle.damage == 0,
          f"Mysterious Rock Inn should prevent ALL dmg from an opponent's ex, "
          f"dealt={dealt}")

    # --- 1b. NEGATIVE: a non-ex opponent attacker is NOT walled. ---
    st, a, b = fresh_state(db)
    crustle = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle
    non_ex = InPlayPokemon(card=db.get("Dreepy"))              # Basic, not ex,
    a.active = non_ex                                           # Dragon (not Fire)
    ctx = ctx_for(st, me=a, opp=b, source=non_ex)
    dealt = fx.apply_attack_damage(ctx, crustle, 50, owner=b, source=non_ex)
    check(dealt == 50 and crustle.damage == 50,
          f"Mysterious Rock Inn must NOT block a non-ex attacker, dealt={dealt}")

    # --- 1c. Ability suppression disables the wall. Crustle is Grass-typed, so
    # the only suppression mechanic the engine implements (Team Rocket's
    # Watchtower, which only silences Colorless Pokémon) can never actually
    # suppress it — so we exercise the shared `ability_suppressed` gate that
    # `_wall_is_active` consults directly, proving the wiring honors
    # suppression (see Bloodmoon Ursaluna ex §5d below for a real-stadium version,
    # since that Pokémon IS Colorless-typed). ---
    st, a, b = fresh_state(db)
    crustle = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle
    ex_attacker = InPlayPokemon(card=db.get("Milotic ex"))
    a.active = ex_attacker
    ctx = ctx_for(st, me=a, opp=b, source=ex_attacker)
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        dealt = fx.apply_attack_damage(ctx, crustle, 120, owner=b, source=ex_attacker)
        check(dealt == 120 and crustle.damage == 120,
              f"a suppressed Mysterious Rock Inn must NOT block, dealt={dealt}")
    finally:
        fx.ability_suppressed = orig_suppressed

    # --- 1d. Superb Scissors bypasses a shield (Dig-style "effect on the
    # opponent's Active") for the full 120. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Crustle"))
    defender = InPlayPokemon(card=db.get("Pikachu ex"))    # 200 HP, not weak to Grass
    defender.shielded = True
    b.active = defender
    st.active_index = 0
    atk_i = next(i for i, atk in enumerate(a.active.card.attacks)
                 if atk.name == "Superb Scissors")
    game._resolve_attack(st, atk_i)
    check(b.active is not None and b.active.damage == 120,
          f"Superb Scissors should bypass a shield for 120, "
          f"got {b.active.damage if b.active else 'KO'}")

    # --- 1e. Superb Scissors bypasses an Ability-wall too (Cornerstone Stance
    # would normally block Crustle, since Crustle HAS an Ability), and Weakness
    # still applies (only "effects", not W/R, are ignored) -> KO's the 210 HP
    # Ogerpon via 120x2=240. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Crustle"))
    b.active = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))  # weak to Grass
    st.active_index = 0
    game._resolve_attack(st, atk_i)
    check(b.active is None and db.get("Cornerstone Mask Ogerpon ex") in b.discard,
          "Superb Scissors should bypass Cornerstone Stance's wall AND still take "
          "Weakness (120x2=240 KOs the 210 HP Ogerpon)")

    # --- 1f. Superb Scissors: exact 120 with no Weakness/wall involved (proves
    # the engine doesn't double-apply base damage + the registered effect). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Crustle"))
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))        # not weak to Grass
    st.active_index = 0
    game._resolve_attack(st, atk_i)
    check(b.active is not None and b.active.damage == 120,
          f"Superb Scissors should deal exactly 120 (no double-apply), "
          f"got {b.active.damage if b.active else 'KO'}")

    # =================================================================== #
    # MILOTIC EX
    # Ability "Sparkling Scales" (pool text):
    #   "Prevent all damage from and effects of attacks from your opponent's
    #    Tera Pokémon done to this Pokémon."
    # Attack "Hypno Splash" [W][C][C] 160 (pool text): "Your opponent's Active
    # Pokémon is now Asleep." — left unregistered per the implementer's notes
    # (no Sleep condition/checkup exists yet), so NOT tested here.
    # =================================================================== #

    # --- 2a. POSITIVE: a Tera source's attack damage is fully prevented. ---
    st, a, b = fresh_state(db)
    milotic = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic
    tera_attacker = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))  # Tera
    a.active = tera_attacker                                                   # Fighting
    ctx = ctx_for(st, me=a, opp=b, source=tera_attacker)
    dealt = fx.apply_attack_damage(ctx, milotic, 140, owner=b, source=tera_attacker)
    check(dealt == 0 and milotic.damage == 0,
          f"Sparkling Scales should prevent ALL dmg from a Tera source, dealt={dealt}")

    # --- 2b. NEGATIVE: an ex source that is NOT Tera is not walled (proves the
    # condition keys on Tera, not on ex). ---
    st, a, b = fresh_state(db)
    milotic = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic
    non_tera_ex = InPlayPokemon(card=db.get("Sprigatito ex"))   # ex, Grass, not Tera
    a.active = non_tera_ex
    ctx = ctx_for(st, me=a, opp=b, source=non_tera_ex)
    dealt = fx.apply_attack_damage(ctx, milotic, 60, owner=b, source=non_tera_ex)
    check(dealt == 60 and milotic.damage == 60,
          f"Sparkling Scales must NOT block a non-Tera ex, dealt={dealt}")

    # --- 2c. Sparkling Scales also blocks the EFFECTS (damage counters) of a
    # Tera source's attack, via place_counters. ---
    st, a, b = fresh_state(db)
    milotic = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic
    tera_attacker = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    a.active = tera_attacker
    ctx = ctx_for(st, me=a, opp=b, source=tera_attacker)
    placed = fx.place_counters(ctx, milotic, 3, owner=b)
    check(placed == 0 and milotic.damage == 0,
          f"Sparkling Scales should block effect-counters from a Tera source, "
          f"placed={placed}")

    # --- 2d. NEGATIVE: a non-Tera source's counters land normally. ---
    st, a, b = fresh_state(db)
    milotic = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic
    non_tera = InPlayPokemon(card=db.get("Dreepy"))
    a.active = non_tera
    ctx = ctx_for(st, me=a, opp=b, source=non_tera)
    placed = fx.place_counters(ctx, milotic, 3, owner=b)
    check(placed == 3 and milotic.damage == 30,
          f"non-Tera counters should land normally, placed={placed}")

    # --- 2e. Ability suppression disables Sparkling Scales too. ---
    st, a, b = fresh_state(db)
    milotic = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic
    tera_attacker = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    a.active = tera_attacker
    ctx = ctx_for(st, me=a, opp=b, source=tera_attacker)
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        dealt = fx.apply_attack_damage(ctx, milotic, 140, owner=b, source=tera_attacker)
        check(dealt == 140 and milotic.damage == 140,
              f"a suppressed Sparkling Scales must NOT block, dealt={dealt}")
    finally:
        fx.ability_suppressed = orig_suppressed

    # =================================================================== #
    # CORNERSTONE MASK OGERPON EX
    # Ability "Cornerstone Stance" (pool text):
    #   "Prevent all damage from attacks done to this Pokémon by your
    #    opponent's Pokémon that have an Ability."
    # Attack "Demolish" [F][C][C] 140 (pool text): "This attack's damage isn't
    # affected by Weakness or Resistance, or by any effects on your opponent's
    # Active Pokémon."
    # =================================================================== #

    # --- 3a. POSITIVE: an opponent's Ability-holder's attack is fully prevented. ---
    # (Milotic ex, not Crustle, so its Water typing doesn't also trip Ogerpon's
    # own Grass Weakness and confound the "prevent ALL damage" assertion.)
    st, a, b = fresh_state(db)
    ogerpon = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = ogerpon
    ability_holder = InPlayPokemon(card=db.get("Milotic ex"))   # has Sparkling Scales
    a.active = ability_holder
    ctx = ctx_for(st, me=a, opp=b, source=ability_holder)
    dealt = fx.apply_attack_damage(ctx, ogerpon, 50, owner=b, source=ability_holder)
    check(dealt == 0 and ogerpon.damage == 0,
          f"Cornerstone Stance should prevent ALL dmg from an Ability-holder, "
          f"dealt={dealt}")

    # --- 3b. NEGATIVE: an opponent attacker with NO Ability is not walled. ---
    st, a, b = fresh_state(db)
    ogerpon = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = ogerpon
    no_ability = InPlayPokemon(card=db.get("Pikachu ex"))       # no Abilities, Lightning
    a.active = no_ability
    ctx = ctx_for(st, me=a, opp=b, source=no_ability)
    dealt = fx.apply_attack_damage(ctx, ogerpon, 50, owner=b, source=no_ability)
    check(dealt == 50 and ogerpon.damage == 50,
          f"Cornerstone Stance must NOT block a non-Ability attacker, dealt={dealt}")

    # --- 3c. Ability suppression disables Cornerstone Stance too. ---
    st, a, b = fresh_state(db)
    ogerpon = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = ogerpon
    ability_holder = InPlayPokemon(card=db.get("Milotic ex"))
    a.active = ability_holder
    ctx = ctx_for(st, me=a, opp=b, source=ability_holder)
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        dealt = fx.apply_attack_damage(ctx, ogerpon, 50, owner=b, source=ability_holder)
        check(dealt == 50 and ogerpon.damage == 50,
              f"a suppressed Cornerstone Stance must NOT block, dealt={dealt}")
    finally:
        fx.ability_suppressed = orig_suppressed

    # --- 3d. Demolish: exact 140, no Weakness/wall noise. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))       # 320 HP, no weaknesses
    st.active_index = 0
    dem_i = next(i for i, atk in enumerate(a.active.card.attacks)
                 if atk.name == "Demolish")
    game._resolve_attack(st, dem_i)
    check(b.active is not None and b.active.damage == 140,
          f"Demolish should deal exactly 140, got {b.active.damage if b.active else 'KO'}")

    # --- 3e. Demolish ignores Weakness: a Pikachu ex weak to Fighting x2 would
    # take 280 normally, but must take only 140 and SURVIVE (200 HP). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    st.active_index = 0
    game._resolve_attack(st, dem_i)
    check(b.active is not None and b.active.damage == 140,
          f"Demolish must ignore Weakness (140, not 280), "
          f"got {b.active.damage if b.active else 'KO'}")

    # --- 3f. Demolish bypasses a shield ("effects on the opponent's Active"). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    defender = InPlayPokemon(card=db.get("Dragapult ex"))
    defender.shielded = True
    b.active = defender
    st.active_index = 0
    game._resolve_attack(st, dem_i)
    check(b.active is not None and b.active.damage == 140,
          f"Demolish should bypass a shield, got {b.active.damage if b.active else 'KO'}")

    # --- 3g. Demolish bypasses an Ability-wall too: Ogerpon IS an ex, so
    # Crustle's Mysterious Rock Inn would normally block it. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = InPlayPokemon(card=db.get("Crustle"))            # not weak to Fighting
    st.active_index = 0
    game._resolve_attack(st, dem_i)
    check(b.active is not None and b.active.damage == 140,
          f"Demolish should bypass Mysterious Rock Inn, "
          f"got {b.active.damage if b.active else 'KO'}")

    # =================================================================== #
    # SPECIAL RED CARD (pool text):
    #   "You can use this card only if your opponent has 3 or fewer Prize
    #    cards remaining. Your opponent shuffles their hand and puts it on
    #    the bottom of their deck. If they put any cards on the bottom of
    #    their deck in this way, they draw 3 cards."
    # =================================================================== #

    # --- 4a. POSITIVE gate: legal at exactly 3 Prizes remaining + a nonempty hand. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dreepy"))
    b.prizes = [db.get("Basic Fire Energy")] * 3     # 3 remaining (3 taken)
    b.hand = [db.get("Cheren")]
    st.active_index = 0
    check(fx.can_play_trainer(st, a, "Special Red Card"),
          "Special Red Card should be LEGAL at 3 Prizes remaining")

    # --- 4b. NEGATIVE gate: illegal at 4+ Prizes remaining (opponent has taken
    # fewer than 3). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dreepy"))
    b.prizes = [db.get("Basic Fire Energy")] * 4      # 4 remaining (only 2 taken)
    b.hand = [db.get("Cheren")]
    st.active_index = 0
    check(not fx.can_play_trainer(st, a, "Special Red Card"),
          "Special Red Card must be ILLEGAL at 4+ Prizes remaining")

    # --- 4c. NEGATIVE gate: illegal when the opponent's hand is empty, even at
    # <=3 Prizes remaining. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dreepy"))
    b.prizes = [db.get("Basic Fire Energy")] * 2
    b.hand = []
    st.active_index = 0
    check(not fx.can_play_trainer(st, a, "Special Red Card"),
          "Special Red Card must be ILLEGAL with an empty opponent hand")

    # --- 4d. Effect: hand goes to the BOTTOM of the deck (not drawn back this
    # turn), and the opponent draws exactly 3 fresh cards from the top. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dreepy"))
    old_hand_names = ["Cheren", "Boss's Orders"]
    b.hand = [db.get(n) for n in old_hand_names]
    b.deck = [db.get("Basic Fire Energy")] * 5        # sits ahead of the bottomed hand
    b.prizes = [db.get("Basic Fire Energy")] * 2
    ctx = ctx_for(st, me=a, opp=b, source=a.active)
    did = fx._special_red_card(ctx)
    check(did, "Special Red Card should succeed with a nonempty opponent hand")
    check(len(b.hand) == 3, f"opponent should draw exactly 3, got {len(b.hand)}")
    check(all(c.name == "Basic Fire Energy" for c in b.hand),
          "opponent should draw from the (pre-existing) TOP of the deck, not the "
          "just-bottomed cards")
    check(sum(1 for c in b.deck if c.name in old_hand_names) == 2,
          "the old hand must be sitting at the bottom of the deck")

    # =================================================================== #
    # BLOODMOON URSALUNA EX
    # Ability "Seasoned Skill" (pool text): "Blood Moon used by this Pokémon
    # costs Colorless less for each Prize card your opponent has taken."
    # Attack "Blood Moon" [C][C][C][C][C] 240 (pool text): "During your next
    # turn, this Pokémon can't attack."
    # =================================================================== #

    # --- 5a. Full cost (5 Colorless) when the opponent has taken 0 Prizes. ---
    st, a, b = fresh_state(db)
    ursaluna = InPlayPokemon(card=db.get("Bloodmoon Ursaluna ex"))
    a.active = ursaluna
    b.prizes = [db.get("Basic Fire Energy")] * 6        # 6 remaining = 0 taken
    atk = next(atk for atk in ursaluna.card.attacks if atk.name == "Blood Moon")
    cost = fx.effective_cost(st, ursaluna, atk)
    check(cost == atk.cost and len(cost) == 5,
          f"Blood Moon should cost the full 5 Colorless at 0 Prizes taken, got {cost}")

    # --- 5b. Discounted cost partway through (3 Prizes taken -> 2 Colorless left). ---
    st, a, b = fresh_state(db)
    ursaluna = InPlayPokemon(card=db.get("Bloodmoon Ursaluna ex"))
    a.active = ursaluna
    b.prizes = [db.get("Basic Fire Energy")] * 3         # 3 remaining = 3 taken
    cost = fx.effective_cost(st, ursaluna, atk)
    check(len(cost) == 2,
          f"Blood Moon should cost 2 Colorless at 3 Prizes taken (5-3), got {cost}")

    # --- 5c. Discount clamps at 0 (never goes negative / free-attack bug). ---
    st, a, b = fresh_state(db)
    ursaluna = InPlayPokemon(card=db.get("Bloodmoon Ursaluna ex"))
    a.active = ursaluna
    b.prizes = []                                         # 0 remaining = 6 taken
    cost = fx.effective_cost(st, ursaluna, atk)
    check(len(cost) == 0,
          f"Blood Moon's discount should clamp at 0 Energy, got {cost}")

    # --- 5d. Ability suppression disables the discount. Unlike the 3 wall
    # cards above, Bloodmoon Ursaluna ex IS Colorless-typed, so the real
    # Team Rocket's Watchtower genuinely suppresses Seasoned Skill here. ---
    st, a, b = fresh_state(db)
    ursaluna = InPlayPokemon(card=db.get("Bloodmoon Ursaluna ex"))
    a.active = ursaluna
    b.prizes = [db.get("Basic Fire Energy")] * 3          # would normally discount
    st.stadium = db.get("Team Rocket's Watchtower")
    st.stadium_owner = 0
    cost = fx.effective_cost(st, ursaluna, atk)
    check(cost == atk.cost,
          f"TRW should suppress Seasoned Skill (Ursaluna is Colorless) -> full "
          f"cost, got {cost}")

    # --- 5e. Blood Moon attack: deals exactly 240 (engine base, not owned) and
    # sets pending_cannot_attack for the following turn. ---
    st, a, b = fresh_state(db)
    ursaluna = InPlayPokemon(card=db.get("Bloodmoon Ursaluna ex"))
    a.active = ursaluna
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))   # 320 HP, no weaknesses
    st.active_index = 0
    bm_i = next(i for i, atk in enumerate(ursaluna.card.attacks)
                if atk.name == "Blood Moon")
    game._resolve_attack(st, bm_i)
    check(b.active is not None and b.active.damage == 240,
          f"Blood Moon should deal exactly 240, got {b.active.damage if b.active else 'KO'}")
    check(ursaluna.pending_cannot_attack,
          "Blood Moon should set pending_cannot_attack for the attacker's next turn")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — wall abilities (Crustle / Milotic ex / Cornerstone Mask Ogerpon ex), "
          "Special Red Card's Prize gate, and Bloodmoon Ursaluna ex's Blood Moon "
          "discount all hold, including the negative/suppression cases.")


if __name__ == "__main__":
    main()
