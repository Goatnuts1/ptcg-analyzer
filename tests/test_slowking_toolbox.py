#!/usr/bin/env python3
"""
test_slowking_toolbox.py — Latias ex (Skyliner), Kyurem (Trifrost / Plasma Bane),
Metagross (Meteor Mash / Luster Blast), Zeraora (Shocking Knuckle / Strong Volt).
Card text quoted from data/standard_pool.json (cross-checked against
limitlesstcg.com this session, per the implementer's recon notes).

Covers:
  - Latias ex (sv8-76, Basic Psychic ex, 210 HP) Ability "Skyliner": "Your
    Basic Pokémon in play have no Retreat Cost."
  - Kyurem (sv6pt5-47, Basic Dragon, 130 HP) Attack "Trifrost"
    [Water][Water][Metal][Metal][Colorless]: "Discard all Energy from this
    Pokémon. This attack does 110 damage to 3 of your opponent's Pokémon.
    (Don't apply Weakness and Resistance for Benched Pokémon.)" Ability
    "Plasma Bane": "If your opponent has any cards in their discard pile that
    have 'Colress' in the name, this Pokémon can use the Trifrost attack for
    [Colorless]." — a DOCUMENTED v0 gap (not modeled; asserted absent below).
  - Metagross (sv5-115, Stage 2 Metal, 180 HP) Attack "Meteor Mash" [Metal] 60:
    "During your next turn, this Pokémon's Meteor Mash attack does 60 more
    damage (before applying Weakness and Resistance)." — NOW IMPLEMENTED (the
    self-buff carryover was a v0 gap; see tests/test_meteor_mash.py for the full
    turn-boundary coverage). Checked here only for what this file is about: two
    uses in the SAME turn are still 60 each, because the buff is armed for the
    owner's NEXT turn. Attack "Luster Blast"
    [Metal][Colorless][Colorless][Colorless] 200: "Discard 2 Energy from this
    Pokémon."
  - Zeraora (sv5-57, Basic Lightning, 120 HP) Attack "Shocking Knuckle"
    [Colorless] 20: "Flip a coin. If heads, your opponent's Active Pokémon is
    now Paralyzed." — Paralysis is not modeled in this engine (same disclosed
    gap as Frogadier's Numbing Water); the flip fires faithfully via ctx.rng
    but is a logged no-op. Attack "Strong Volt"
    [Lightning][Lightning][Colorless] 120: "Discard an Energy from this
    Pokémon."

Run from project root:  python3 tests/test_slowking_toolbox.py
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


class _FixedCoin:
    """Stand-in for ctx.rng forcing flip()'s randint(0,1) call to a fixed
    result, same pattern as tests/test_greninja_line.py's _FixedCoin."""
    def __init__(self, value):
        self._value = value

    def randint(self, lo, hi):
        return self._value


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # =================================================================== #
    # LATIAS EX (sv8-76, Basic Psychic ex, 210 HP)
    # Ability "Skyliner": "Your Basic Pokémon in play have no Retreat Cost."
    # =================================================================== #

    latias_card = db.get("Latias ex")
    check("Skyliner" in [ab.name for ab in latias_card.abilities],
          "setup: Latias ex must carry the Skyliner Ability")
    check(tuple(latias_card.subtypes) == ("Basic", "ex"),
          f"setup: Latias ex should be Basic ex, got {latias_card.subtypes}")

    # --- 1a. POSITIVE: skyliner_free_retreat() directly — a Basic Pokémon on
    # the SAME side as an un-suppressed Latias ex has free retreat. ---
    st, a, b = fresh_state(db)
    latias = InPlayPokemon(card=latias_card)
    dwebble = InPlayPokemon(card=db.get("Dwebble"))         # Basic, printed retreat 2
    a.active = dwebble
    a.bench = [latias]
    check(dwebble.card.retreat_cost == 2, "setup: Dwebble should print retreat cost 2")
    check(fx.skyliner_free_retreat(st, a, dwebble),
          "Skyliner: a Basic Pokémon on Latias ex's side should have free retreat")

    # --- 1b. Integration: game.retreat_cost() with (state, owner) reports 0,
    # not the printed 2, once Latias ex is on the same board; without board
    # context (no state/owner passed), the printed cost is unaffected — same
    # convention as Agile/Air Balloon needing owner/state to apply. ---
    check(game.retreat_cost(dwebble, st, a) == 0,
          f"game.retreat_cost should be 0 under Skyliner, got {game.retreat_cost(dwebble, st, a)}")
    check(game.retreat_cost(dwebble) == 2,
          "without board context, retreat_cost must fall back to the printed cost")

    # --- 1c. NEGATIVE: a NON-Basic Pokémon (Crustle, Stage 1) on the SAME side
    # still pays its full printed retreat cost — Skyliner only covers Basics. ---
    st, a, b = fresh_state(db)
    latias2 = InPlayPokemon(card=latias_card)
    crustle = InPlayPokemon(card=db.get("Crustle"))          # Stage 1, retreat 3
    a.active = crustle
    a.bench = [latias2]
    check(crustle.card.retreat_cost == 3, "setup: Crustle should print retreat cost 3")
    check(not fx.skyliner_free_retreat(st, a, crustle),
          "Skyliner must NOT give a non-Basic Pokémon free retreat")
    check(game.retreat_cost(crustle, st, a) == 3,
          f"non-Basic retreat cost must stay at the printed 3, got {game.retreat_cost(crustle, st, a)}")

    # --- 1d. NEGATIVE: without ANY Latias ex in play, a Basic pays full cost. ---
    st, a, b = fresh_state(db)
    lone_dwebble = InPlayPokemon(card=db.get("Dwebble"))
    a.active = lone_dwebble
    check(not fx.skyliner_free_retreat(st, a, lone_dwebble),
          "no Latias ex in play -> no free retreat")
    check(game.retreat_cost(lone_dwebble, st, a) == 2,
          "no Latias ex in play -> printed retreat cost unaffected")

    # --- 1e. NEGATIVE: Skyliner is a per-SIDE effect — the OPPONENT's Latias ex
    # does not grant free retreat to this player's Basics. ---
    st, a, b = fresh_state(db)
    opp_latias = InPlayPokemon(card=latias_card)
    b.active = opp_latias
    my_dwebble = InPlayPokemon(card=db.get("Dwebble"))
    a.active = my_dwebble
    check(not fx.skyliner_free_retreat(st, a, my_dwebble),
          "the OPPONENT's Latias ex must not grant this player's Basics free retreat")
    check(game.retreat_cost(my_dwebble, st, a) == 2,
          "opponent's Skyliner must not reduce this player's retreat cost")

    # --- 1f. NEGATIVE: ability suppression turns Skyliner off (mirrors
    # test_starmie.py's monkeypatched-suppression pattern for Mysterious Rock
    # Inn) — a suppressed Latias ex no longer grants free retreat. ---
    st, a, b = fresh_state(db)
    latias3 = InPlayPokemon(card=latias_card)
    dwebble3 = InPlayPokemon(card=db.get("Dwebble"))
    a.active = dwebble3
    a.bench = [latias3]
    orig_suppressed = fx.ability_suppressed
    try:
        fx.ability_suppressed = lambda state, mon: True
        check(not fx.skyliner_free_retreat(st, a, dwebble3),
              "a suppressed Latias ex must not grant free retreat")
    finally:
        fx.ability_suppressed = orig_suppressed

    # =================================================================== #
    # KYUREM (sv6pt5-47, Basic Dragon, 130 HP, no printed Weakness/Resistance)
    # Attack "Trifrost" [W][W][M][M][C] (pool text): "Discard all Energy from
    # this Pokémon. This attack does 110 damage to 3 of your opponent's
    # Pokémon. (Don't apply Weakness and Resistance for Benched Pokémon.)"
    # =================================================================== #

    kyurem_card = db.get("Kyurem")
    trifrost_atk = next(a for a in kyurem_card.attacks if a.name == "Trifrost")
    check(trifrost_atk.cost == ("Water", "Water", "Metal", "Metal", "Colorless"),
          f"setup: Trifrost cost should be WWMMC, got {trifrost_atk.cost}")
    check(("Kyurem", "Trifrost") in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Trifrost must own its damage (110 to 3 CHOSEN Pokémon, not the Active)")

    # --- 2a. POSITIVE: discards ALL attached Energy, then 110 to the 3
    # opponent Pokémon CLOSEST to a KO, leaving a 4th (highest remaining_hp)
    # untouched — v0 target policy. ---
    st, a, b = fresh_state(db)
    kyurem = InPlayPokemon(card=kyurem_card)
    kyurem.energy = [db.get("Basic Water Energy"), db.get("Basic Water Energy"),
                     db.get("Basic Metal Energy"), db.get("Basic Metal Energy"),
                     db.get("Basic Fire Energy")]
    a.active = kyurem
    st.active_index = 0
    dragapult = InPlayPokemon(card=db.get("Dragapult ex"))   # 320 HP, no Weakness -> untouched
    dwebble4 = InPlayPokemon(card=db.get("Dwebble"))          # 70 HP -> lowest, hit
    slowpoke = InPlayPokemon(card=db.get("Slowpoke"))         # 80 HP -> hit
    crustle4 = InPlayPokemon(card=db.get("Crustle"))          # 150 HP -> hit
    b.active = dragapult
    b.bench = [dwebble4, slowpoke, crustle4]
    tf_i = next(i for i, atk in enumerate(kyurem.card.attacks) if atk.name == "Trifrost")
    game._resolve_attack(st, tf_i)
    check(kyurem.energy == [], f"Trifrost must discard ALL attached Energy, got {kyurem.energy}")
    check(len(a.discard) == 5, f"the 5 discarded Energy must land in the attacker's own discard, got {len(a.discard)}")
    check(dwebble4.damage == 110, f"Trifrost: lowest remaining_hp target should take 110, got {dwebble4.damage}")
    check(slowpoke.damage == 110, f"Trifrost: 2nd-lowest remaining_hp target should take 110, got {slowpoke.damage}")
    check(crustle4.damage == 110, f"Trifrost: 3rd-lowest remaining_hp target should take 110, got {crustle4.damage}")
    check(dragapult.damage == 0, f"Trifrost: the 4th (highest remaining_hp, untargeted) Pokémon must be untouched, got {dragapult.damage}")

    # --- 2b. NEGATIVE: no Energy attached -> the discard step is a no-op (no
    # crash), damage still lands. ---
    st, a, b = fresh_state(db)
    kyurem2 = InPlayPokemon(card=kyurem_card)
    a.active = kyurem2
    st.active_index = 0
    opp_active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = opp_active
    tf_i2 = next(i for i, atk in enumerate(kyurem2.card.attacks) if atk.name == "Trifrost")
    game._resolve_attack(st, tf_i2)
    check(kyurem2.energy == [], "no Energy attached -> discard-all is a harmless no-op")
    check(opp_active.damage == 110, f"with no Energy attached, damage must still land (110), got {opp_active.damage}")

    # --- 2c. NEGATIVE: fewer than 3 opponent Pokémon in play -> hits all
    # available, no crash. ---
    st, a, b = fresh_state(db)
    kyurem3 = InPlayPokemon(card=kyurem_card)
    a.active = kyurem3
    st.active_index = 0
    only_active = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = only_active
    b.bench = []
    tf_i3 = next(i for i, atk in enumerate(kyurem3.card.attacks) if atk.name == "Trifrost")
    game._resolve_attack(st, tf_i3)
    check(only_active.damage == 110,
          f"with only 1 opponent Pokémon in play, Trifrost should still hit it for 110, got {only_active.damage}")

    # --- 2d. Ability "Plasma Bane" — DOCUMENTED v0 GAP: the conditional
    # cost-reduction to [Colorless] when the opponent's discard has a
    # 'Colress'-named card is NOT modeled (requires a full typed-cost override
    # the engine's Colorless-only effective_cost can't express). Assert this
    # gap explicitly rather than silently: no registered ability effect, and
    # effective_cost stays at the full printed WWMMC cost even when the
    # opponent's discard satisfies the printed condition. ---
    check(("Kyurem", "Plasma Bane") not in fx.ABILITY_EFFECTS,
          "Plasma Bane must have no registered ability effect (documented v0 gap)")
    st, a, b = fresh_state(db)
    kyurem4 = InPlayPokemon(card=kyurem_card)
    a.active = kyurem4
    b.discard = [db.get("Slowpoke")]  # stand-in "Colress"-named card not in this pool;
    # the point of this check is that effective_cost has NO wiring to inspect
    # opp.discard for Kyurem's Trifrost at all, condition-satisfied or not.
    eff = fx.effective_cost(st, kyurem4, trifrost_atk)
    check(eff == trifrost_atk.cost,
          f"Plasma Bane's cost reduction is not modeled -> effective_cost must equal the "
          f"full printed cost regardless of opponent's discard, got {eff}")

    # =================================================================== #
    # METAGROSS (sv5-115, Stage 2 Metal, 180 HP, Weak Fire ×2, Resist Grass -30)
    # =================================================================== #

    metagross_card = db.get("Metagross")
    meteor_atk = next(a for a in metagross_card.attacks if a.name == "Meteor Mash")
    luster_atk = next(a for a in metagross_card.attacks if a.name == "Luster Blast")
    check(meteor_atk.cost == ("Metal",) and meteor_atk.damage == 60,
          f"setup: Meteor Mash should be [Metal] 60, got cost={meteor_atk.cost} damage={meteor_atk.damage}")
    check(luster_atk.cost == ("Metal", "Colorless", "Colorless", "Colorless") and luster_atk.damage == 200,
          f"setup: Luster Blast should be [Metal][C][C][C] 200, got cost={luster_atk.cost} damage={luster_atk.damage}")

    # --- 3a. Meteor Mash [Metal] 60 (pool text): "During your next turn, this
    # Pokémon's Meteor Mash attack does 60 more damage (before applying
    # Weakness and Resistance)." The self-buff carryover IS now modeled (it owns
    # its damage, since 60-vs-120 is conditional on a flag the engine can't see);
    # the turn-boundary lifecycle is covered in tests/test_meteor_mash.py. What
    # this file pins is that the buff is armed for the NEXT turn, so two uses in
    # the SAME turn are 60 each. ---
    check(fx.get_attack_effect("Metagross", "Meteor Mash") is not None,
          "Meteor Mash's self-buff carryover is implemented -> it must have an effect")
    check(("Metagross", "Meteor Mash") in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Meteor Mash's conditional base means its effect applies all its own damage")
    st, a, b = fresh_state(db)
    metagross = InPlayPokemon(card=metagross_card)
    a.active = metagross
    st.active_index = 0
    defender = InPlayPokemon(card=db.get("Dragapult ex"))   # 320 HP, no Weakness
    b.active = defender
    mm_i = next(i for i, atk in enumerate(metagross.card.attacks) if atk.name == "Meteor Mash")
    game._resolve_attack(st, mm_i)
    check(defender.damage == 60, f"Meteor Mash should deal a plain 60, got {defender.damage}")
    check(metagross.pending_boosted_attacks == {"Meteor Mash": 60},
          f"the +60 must be armed for the OWNER's next turn, got "
          f"{metagross.pending_boosted_attacks}")
    # A SECOND use within the SAME turn is still a plain 60: the buff only becomes
    # live when start_turn promotes it on the owner's next turn.
    game._resolve_attack(st, mm_i)
    check(defender.damage == 120, f"two same-turn Meteor Mashes total 120 (60 each — the "
                                  f"buff is not live until next turn), got {defender.damage}")

    # --- 3b. Luster Blast [Metal][C][C][C] 200 (pool text): "Discard 2 Energy
    # from this Pokémon." ---
    st, a, b = fresh_state(db)
    metagross2 = InPlayPokemon(card=metagross_card)
    metagross2.energy = [db.get("Basic Metal Energy"), db.get("Basic Metal Energy"),
                         db.get("Basic Metal Energy"), db.get("Basic Metal Energy")]
    a.active = metagross2
    st.active_index = 0
    defender2 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender2
    lb_i = next(i for i, atk in enumerate(metagross2.card.attacks) if atk.name == "Luster Blast")
    game._resolve_attack(st, lb_i)
    check(defender2.damage == 200, f"Luster Blast should deal exactly 200, got {defender2.damage}")
    check(len(metagross2.energy) == 2, f"Luster Blast must discard exactly 2 Energy, got {len(metagross2.energy)} remaining")
    check(len(a.discard) == 2, f"the 2 discarded Energy must land in the attacker's own discard, got {len(a.discard)}")

    # --- 3c. NEGATIVE: fewer than 2 Energy attached -> discards only what's
    # there, no crash. ---
    st, a, b = fresh_state(db)
    metagross3 = InPlayPokemon(card=metagross_card)
    metagross3.energy = [db.get("Basic Metal Energy")]
    a.active = metagross3
    st.active_index = 0
    defender3 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender3
    lb_i2 = next(i for i, atk in enumerate(metagross3.card.attacks) if atk.name == "Luster Blast")
    game._resolve_attack(st, lb_i2)
    check(metagross3.energy == [], "Luster Blast with only 1 Energy attached must discard that 1, no crash")
    check(defender3.damage == 200, f"Luster Blast damage must still land with insufficient Energy to discard, got {defender3.damage}")

    # =================================================================== #
    # ZERAORA (sv5-57, Basic Lightning, 120 HP, Weak Fighting ×2)
    # =================================================================== #

    zeraora_card = db.get("Zeraora")
    knuckle_atk = next(a for a in zeraora_card.attacks if a.name == "Shocking Knuckle")
    volt_atk = next(a for a in zeraora_card.attacks if a.name == "Strong Volt")
    check(knuckle_atk.cost == ("Colorless",) and knuckle_atk.damage == 20,
          f"setup: Shocking Knuckle should be [C] 20, got cost={knuckle_atk.cost} damage={knuckle_atk.damage}")
    check(volt_atk.cost == ("Lightning", "Lightning", "Colorless") and volt_atk.damage == 120,
          f"setup: Strong Volt should be [L][L][C] 120, got cost={volt_atk.cost} damage={volt_atk.damage}")

    # --- 4a. Shocking Knuckle [C] 20 (pool text): "Flip a coin. If heads,
    # your opponent's Active Pokémon is now Paralyzed." HEADS branch: damage
    # lands regardless of the flip; Paralysis is a logged no-op (not modeled,
    # same disclosed gap as Frogadier's Numbing Water). ---
    st, a, b = fresh_state(db)
    zeraora = InPlayPokemon(card=zeraora_card)
    a.active = zeraora
    st.active_index = 0
    defender4 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender4
    st.rng = _FixedCoin(1)   # force heads
    sk_i = next(i for i, atk in enumerate(zeraora.card.attacks) if atk.name == "Shocking Knuckle")
    game._resolve_attack(st, sk_i)
    check(defender4.damage == 20, f"Shocking Knuckle should deal 20 regardless of the coin flip, got {defender4.damage}")
    check(any("Paralyzed" in line for line in st.log),
          "heads should log the (unmodeled) Paralysis branch")
    check(not hasattr(defender4, "paralyzed") or not getattr(defender4, "paralyzed", False),
          "Paralysis must not actually be applied — it is not a modeled Special Condition in this engine")

    # --- 4b. TAILS branch: damage still lands, no Paralysis-branch log line. ---
    st, a, b = fresh_state(db)
    zeraora2 = InPlayPokemon(card=zeraora_card)
    a.active = zeraora2
    st.active_index = 0
    defender5 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender5
    st.rng = _FixedCoin(0)   # force tails
    game._resolve_attack(st, sk_i)
    check(defender5.damage == 20, f"Shocking Knuckle should deal 20 on tails too, got {defender5.damage}")
    check(any("tails" in line for line in st.log), "tails should log the tails branch")
    check(not any("Paralyzed" in line for line in st.log), "tails must NOT log the Paralysis branch")

    # --- 4c. Strong Volt [L][L][C] 120 (pool text): "Discard an Energy from
    # this Pokémon." ---
    st, a, b = fresh_state(db)
    zeraora3 = InPlayPokemon(card=zeraora_card)
    zeraora3.energy = [db.get("Basic Lightning Energy"), db.get("Basic Lightning Energy"),
                       db.get("Basic Fire Energy")]
    a.active = zeraora3
    st.active_index = 0
    defender6 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender6
    sv_i = next(i for i, atk in enumerate(zeraora3.card.attacks) if atk.name == "Strong Volt")
    game._resolve_attack(st, sv_i)
    check(defender6.damage == 120, f"Strong Volt should deal exactly 120, got {defender6.damage}")
    check(len(zeraora3.energy) == 2, f"Strong Volt must discard exactly 1 Energy, got {len(zeraora3.energy)} remaining (expected 2)")
    check(len(a.discard) == 1, f"the discarded Energy must land in the attacker's own discard, got {len(a.discard)}")

    # --- 4d. NEGATIVE: no Energy attached -> discard is a no-op, no crash,
    # damage still lands. ---
    st, a, b = fresh_state(db)
    zeraora4 = InPlayPokemon(card=zeraora_card)
    a.active = zeraora4
    st.active_index = 0
    defender7 = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = defender7
    game._resolve_attack(st, sv_i)
    check(zeraora4.energy == [], "no Energy attached -> Strong Volt's discard step is a harmless no-op")
    check(defender7.damage == 120, f"Strong Volt damage must still land with no Energy to discard, got {defender7.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_slowking_toolbox.py: all checks passed (Latias ex Skyliner, "
          "Kyurem Trifrost/Plasma Bane, Metagross Meteor Mash/Luster Blast, "
          "Zeraora Shocking Knuckle/Strong Volt).")


if __name__ == "__main__":
    main()
