#!/usr/bin/env python3
"""
test_cynthia_garchomp_line.py — the Cynthia's Garchomp ex evolution line's own
attacks/ability, each asserted against its exact card text with negative cases.

  Cynthia's Gible (sv10 102)
    Rock Hurl  [F] 20 — "This attack's damage isn't affected by Resistance."
  Cynthia's Gabite (sv10 103)
    Ability Champion's Call — "Once during your turn, you may search your deck for a
    Cynthia's Pokémon, reveal it, and put it into your hand. Then, shuffle your deck."
  Cynthia's Garchomp ex (sv10 104)
    Corkscrew Dive  [F] 100 — "You may draw cards until you have 6 cards in your hand."
    Draconic Buster [F][F] 260 — "Discard all Energy from this Pokémon."
  Cynthia's Spiritomb (sv10 129)
    Raging Curse [C] 10× — "This attack does 10 damage for each damage counter on all of
    your Benched Cynthia's Pokémon. This attack's damage isn't affected by Weakness."

Run: python3 tests/test_cynthia_garchomp_line.py
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

    # ===================================================================== #
    # 1. Rock Hurl — "20. This attack's damage isn't affected by Resistance."
    # ===================================================================== #
    # It must OWN its damage, else the engine would auto-apply the printed 20 through
    # the normal (Resistance-applying) path and the effect would double-hit.
    check(("Cynthia's Gible", "Rock Hurl") in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Rock Hurl must be in ATTACK_EFFECT_OWNS_DAMAGE (engine base 0)")

    # 1a. Into a Fighting-RESISTANT defender (Munkidori: Fighting −30). A plain 20-damage
    # Fighting hit would be reduced to 0; Rock Hurl lands the full 20.
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.active = gible
    b.active = InPlayPokemon(card=db.get("Munkidori"))       # Fighting −30 Resistance
    fx._rock_hurl(ctx_for(st, a, b, source=gible))
    check(b.active.damage == 20,
          f"Rock Hurl must ignore the defender's Fighting Resistance (want 20, got "
          f"{b.active.damage})")

    # 1a'. NEGATIVE control: the same 20 through the ordinary path IS resisted to 0, so
    # the assertion above is really testing the flag and not a no-op.
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.active = gible
    b.active = InPlayPokemon(card=db.get("Munkidori"))
    fx.apply_attack_damage(ctx_for(st, a, b, source=gible), b.active, 20,
                           owner=b, source=gible)
    check(b.active.damage == 0,
          f"control: a plain 20 Fighting hit into Fighting −30 Resistance must be 0, got "
          f"{b.active.damage}")

    # 1b. Weakness is NOT named on the card, so it still applies: Snorlax ex is
    # Fighting ×2 -> 40.
    st, a, b = fresh_state(db)
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    a.active = gible
    b.active = InPlayPokemon(card=db.get("Snorlax ex"))      # Fighting ×2 Weakness
    fx._rock_hurl(ctx_for(st, a, b, source=gible))
    check(b.active.damage == 40,
          f"Rock Hurl must still double for Weakness (want 40, got {b.active.damage})")

    # 1c. The two W/R halves are independently skippable (the plumbing Rock Hurl and
    # Raging Curse each use one half of). Munkidori: Darkness ×2 Weakness, Fighting −30
    # Resistance.
    st, a, b = fresh_state(db)
    munk = InPlayPokemon(card=db.get("Munkidori"))
    b.active = munk
    dark_src = db.get("Cynthia's Spiritomb")      # Darkness Pokémon
    fight_src = db.get("Cynthia's Gible")         # Fighting Pokémon
    wr = fx._apply_weakness_resistance
    check(wr(st, dark_src, munk, 50) == 100, "Darkness source into Darkness ×2 must be 100")
    check(wr(st, dark_src, munk, 50, skip_weakness=True) == 50,
          "skip_weakness must drop the ×2 and nothing else")
    check(wr(st, fight_src, munk, 50) == 20, "Fighting source into Fighting −30 must be 20")
    check(wr(st, fight_src, munk, 50, skip_resistance=True) == 50,
          "skip_resistance must drop the −30 and nothing else")
    check(wr(st, fight_src, munk, 50, skip_weakness=True) == 20,
          "skip_weakness must NOT also skip Resistance")

    # ===================================================================== #
    # 2. Champion's Call — search your deck for A (one) Cynthia's Pokémon -> hand.
    # ===================================================================== #
    st, a, b = fresh_state(db)
    gabite = InPlayPokemon(card=db.get("Cynthia's Gabite"))
    a.active = gabite
    a.deck = [db.get("Cynthia's Garchomp ex"), db.get("Dwebble"),
              db.get("Basic Fighting Energy"), db.get("Cynthia's Power Weight")]
    fx._champions_call(ctx_for(st, a, b, source=gabite))
    check(len(a.hand) == 1 and a.hand[0].name == "Cynthia's Garchomp ex",
          f"Champion's Call must put exactly 1 Cynthia's Pokémon into hand, got "
          f"{[c.name for c in a.hand]}")
    check(len(a.deck) == 3, f"the deck must shrink by exactly 1, got {len(a.deck)}")

    # 2a. NEGATIVE: "Cynthia's Power Weight" is a Cynthia's TRAINER, not a Pokémon — it
    # must never be findable, and with no Cynthia's Pokémon left the guard says no.
    st, a, b = fresh_state(db)
    gabite = InPlayPokemon(card=db.get("Cynthia's Gabite"))
    a.active = gabite
    a.deck = [db.get("Cynthia's Power Weight"), db.get("Dwebble")]
    fx._champions_call(ctx_for(st, a, b, source=gabite))
    check(a.hand == [], f"a Cynthia's Trainer must not satisfy 'a Cynthia's Pokémon', got "
                        f"{[c.name for c in a.hand]}")
    guard = fx.get_ability_can_use("Cynthia's Gabite", "Champion's Call")
    check(guard is not None, "Champion's Call must have an ABILITY_CAN_USE guard")
    check(guard(st, a, gabite) is False,
          "the guard must be False when no Cynthia's Pokémon is left in the deck")
    a.deck.append(db.get("Cynthia's Roselia"))
    check(guard(st, a, gabite) is True,
          "the guard must be True once a Cynthia's Pokémon is in the deck")

    # ===================================================================== #
    # 3. Corkscrew Dive — "You may draw cards until you have 6 cards in your hand."
    # ===================================================================== #
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.hand = [db.get("Basic Fighting Energy")] * 2
    a.deck = [db.get("Basic Fighting Energy")] * 10
    fx._corkscrew_dive(ctx_for(st, a, b, source=chomp))
    check(len(a.hand) == 6, f"Corkscrew Dive must fill the hand to 6, got {len(a.hand)}")
    check(len(a.deck) == 6, f"it must draw exactly 4 here, deck should be 6, got {len(a.deck)}")

    # 3a. NEGATIVE: already at/above 6 cards -> draws NOTHING (never discards down to 6).
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.hand = [db.get("Basic Fighting Energy")] * 8
    a.deck = [db.get("Basic Fighting Energy")] * 5
    fx._corkscrew_dive(ctx_for(st, a, b, source=chomp))
    check(len(a.hand) == 8 and len(a.deck) == 5,
          f"with 8 cards in hand it must draw 0 and discard none, got hand={len(a.hand)} "
          f"deck={len(a.deck)}")

    # 3b. A short deck draws only what's there (no crash, no phantom cards).
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    a.hand = []
    a.deck = [db.get("Basic Fighting Energy")] * 2
    fx._corkscrew_dive(ctx_for(st, a, b, source=chomp))
    check(len(a.hand) == 2 and a.deck == [],
          f"a 2-card deck must yield a 2-card hand, got hand={len(a.hand)}")

    # ===================================================================== #
    # 4. Draconic Buster — "Discard all Energy from this Pokémon."
    # ===================================================================== #
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    chomp.energy = [db.get("Basic Fighting Energy"), db.get("Basic Fighting Energy"),
                    db.get("Rocky Fighting Energy")]     # ALL Energy, incl. Special
    a.active = chomp
    bench_mon = InPlayPokemon(card=db.get("Cynthia's Gible"))
    bench_mon.energy = [db.get("Basic Fighting Energy")]
    a.bench = [bench_mon]
    fx._draconic_buster(ctx_for(st, a, b, source=chomp))
    check(chomp.energy == [], f"all Energy must come off the attacker, got {chomp.energy}")
    check(len(a.discard) == 3, f"all 3 must go to the discard pile, got {len(a.discard)}")
    check(any(c.name == "Rocky Fighting Energy" for c in a.discard),
          "Special Energy is Energy too — the Rocky Fighting Energy must be discarded")
    check(len(bench_mon.energy) == 1,
          "'from this Pokémon' — a Benched Pokémon's Energy must be untouched")

    # 4a. NEGATIVE: no Energy attached -> no crash, nothing discarded.
    st, a, b = fresh_state(db)
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    a.active = chomp
    fx._draconic_buster(ctx_for(st, a, b, source=chomp))
    check(a.discard == [], "with no Energy attached nothing may be discarded")

    # ===================================================================== #
    # 5. Raging Curse — 10 per damage counter on all of your BENCHED Cynthia's
    #    Pokémon; damage isn't affected by Weakness.
    # ===================================================================== #
    st, a, b = fresh_state(db)
    tomb = InPlayPokemon(card=db.get("Cynthia's Spiritomb"))
    tomb.damage = 40                       # the ACTIVE's own counters must NOT count
    a.active = tomb
    hurt_roselia = InPlayPokemon(card=db.get("Cynthia's Roselia"))
    hurt_roselia.damage = 30               # 3 counters
    hurt_gible = InPlayPokemon(card=db.get("Cynthia's Gible"))
    hurt_gible.damage = 20                 # 2 counters
    non_cynthia = InPlayPokemon(card=db.get("Dwebble"))
    non_cynthia.damage = 50                # NOT a Cynthia's Pokémon -> must not count
    a.bench = [hurt_roselia, hurt_gible, non_cynthia]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))     # no Weakness, no Resistance
    fx._raging_curse(ctx_for(st, a, b, source=tomb))
    check(b.active.damage == 50,
          f"Raging Curse must count only Benched Cynthia's counters (3+2 -> 50), got "
          f"{b.active.damage}")

    # 5a. "This attack's damage isn't affected by Weakness": Munkidori is Darkness ×2 and
    # Spiritomb is a Darkness Pokémon — the hit must NOT double.
    st, a, b = fresh_state(db)
    tomb = InPlayPokemon(card=db.get("Cynthia's Spiritomb"))
    a.active = tomb
    hurt = InPlayPokemon(card=db.get("Cynthia's Roselia"))
    hurt.damage = 50                       # 5 counters -> 50 damage
    a.bench = [hurt]
    b.active = InPlayPokemon(card=db.get("Munkidori"))        # Darkness ×2
    fx._raging_curse(ctx_for(st, a, b, source=tomb))
    check(b.active.damage == 50,
          f"Weakness must be ignored (want 50, not 100), got {b.active.damage}")
    # (No printing in the current pool has Darkness Resistance, so the "Resistance still
    # applies" half of this card is covered by the independent-flag matrix in §1c.)

    # 5b. NEGATIVE: an undamaged Bench means 0 counters -> 0 damage (a real 0, because
    # the attack is printed "10×" and the engine applies no base damage).
    st, a, b = fresh_state(db)
    tomb = InPlayPokemon(card=db.get("Cynthia's Spiritomb"))
    a.active = tomb
    a.bench = [InPlayPokemon(card=db.get("Cynthia's Roselia"))]
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    fx._raging_curse(ctx_for(st, a, b, source=tomb))
    check(b.active.damage == 0,
          f"with no counters on the Bench, Raging Curse must do 0, got {b.active.damage}")
    check(db.get("Cynthia's Spiritomb").attacks[0].damage_suffix == "×",
          "Raging Curse must be a '×' variable-damage attack (engine base 0)")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_cynthia_garchomp_line.py: all checks passed — Rock Hurl ignores only "
          "Resistance, Champion's Call finds only Cynthia's Pokémon, Corkscrew Dive fills "
          "to 6, Draconic Buster dumps all Energy, Raging Curse counts only Benched "
          "Cynthia's counters and ignores Weakness")


if __name__ == "__main__":
    main()
