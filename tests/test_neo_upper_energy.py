#!/usr/bin/env python3
"""
test_neo_upper_energy.py — Neo Upper Energy (sv5 162, Special / ACE SPEC):

  "As long as this card is attached to a Pokémon, it provides Colorless Energy.
   If this card is attached to a Stage 2 Pokémon, this card provides every type of
   Energy but provides only 2 Energy at a time."

Two separate clauses, and BOTH have to be modeled or the card is dead weight:
  1. "every type of Energy" -> a wildcard, so it can pay a TYPED symbol.
  2. "2 Energy at a time"   -> two UNITS from one card, so it can pay a two-symbol
     cost on its own (Cynthia's Garchomp ex's [F][F] Draconic Buster — the exact
     reason the cynthia_garchomp list plays it as its ACE SPEC).
Both clauses are gated on a STAGE 2 holder: on a Basic or a Stage 1 it is a plain
single Colorless.

Modeled as "Any" wildcard tokens in InPlayPokemon.provided_types(), consumed by
game.can_pay_cost — the same mechanism as Prism Energy's 1-unit version.

Run: python3 tests/test_neo_upper_energy.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import InPlayPokemon
from src.engine.game import can_pay_cost
from src.engine import effects as fx


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    nue = db.get("Neo Upper Energy")
    fighting = db.get("Basic Fighting Energy")

    # It is recorded as an implemented PASSIVE Special Energy (no on-attach rider).
    check("Neo Upper Energy" in fx.SPECIAL_ENERGY_PASSIVE,
          "Neo Upper Energy must be recorded in SPECIAL_ENERGY_PASSIVE")
    check("Neo Upper Energy" not in fx.SPECIAL_ENERGY_ON_ATTACH,
          "Neo Upper Energy has no on-attach trigger")

    # Sanity: the pool text really is the two-clause Stage 2 version, and the card
    # carries no types of its own (so a naive reading gives plain Colorless).
    text = " ".join(nue.rules)
    check("provides every type of Energy" in text and "2 Energy at a time" in text,
          "sanity: pool text must contain both Neo Upper clauses")
    check(not nue.types, "sanity: Neo Upper Energy has no printed Energy type")

    # --- 1. STAGE 2 holder: every type + 2 Energy at a time. -------------------
    chomp = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))   # Stage 2
    chomp.energy = [nue]
    check(chomp.provided_types() == ["Any", "Any"],
          f"a Stage 2 holder must get 2 wildcard units, got {chomp.provided_types()}")
    draconic = [a for a in chomp.card.attacks if a.name == "Draconic Buster"][0]
    check(draconic.cost == ("Fighting", "Fighting"),
          "sanity: Draconic Buster costs [F][F]")
    check(can_pay_cost(chomp, draconic.cost),
          "one Neo Upper Energy alone must pay Draconic Buster's [F][F]")
    corkscrew = [a for a in chomp.card.attacks if a.name == "Corkscrew Dive"][0]
    check(can_pay_cost(chomp, corkscrew.cost),
          "it must also pay Corkscrew Dive's single [F] (a spare unit is fine)")
    # "every type" is not Fighting-specific.
    check(can_pay_cost(chomp, ("Water", "Psychic")),
          "'every type of Energy' must cover any two typed symbols, not just [F]")
    # but only TWO units — never three.
    check(not can_pay_cost(chomp, ("Fighting", "Fighting", "Fighting")),
          "2 Energy at a time means exactly 2 — a 3-symbol cost must NOT be payable")
    check(not can_pay_cost(chomp, ("Fighting", "Colorless", "Colorless")),
          "2 units can't cover a 3-symbol cost even when the extras are Colorless")

    # It composes with real energy rather than replacing it.
    chomp2 = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    chomp2.energy = [nue, fighting]
    check(can_pay_cost(chomp2, ("Fighting", "Fighting", "Fighting")),
          "Neo Upper (2 units) + a Basic Fighting (1) must pay a 3-symbol [F] cost")

    # --- 2. NEGATIVE: not a Stage 2 -> plain single Colorless. ------------------
    gible = InPlayPokemon(card=db.get("Cynthia's Gible"))         # Basic
    gible.energy = [nue]
    check(gible.provided_types() == ["Colorless"],
          f"on a Basic it provides one Colorless, got {gible.provided_types()}")
    rock_hurl = [a for a in gible.card.attacks if a.name == "Rock Hurl"][0]
    check(not can_pay_cost(gible, rock_hurl.cost),
          "on a Basic it must NOT pay a typed [F] cost (Colorless can't pay [F])")
    check(can_pay_cost(gible, ("Colorless",)),
          "on a Basic it still pays a single [C]")

    gabite = InPlayPokemon(card=db.get("Cynthia's Gabite"))       # Stage 1
    gabite.energy = [nue]
    check(gabite.provided_types() == ["Colorless"],
          f"on a Stage 1 it provides one Colorless, got {gabite.provided_types()}")
    check(not can_pay_cost(gabite, ("Fighting",)),
          "on a Stage 1 it must NOT pay [F] — only 'Stage 2' is named on the card")

    # --- 3. Prism Energy's 1-unit wildcard must NOT have been widened by this. --
    prism = db.get("Prism Energy")
    basic = InPlayPokemon(card=db.get("Cynthia's Gible"))
    basic.energy = [prism]
    check(basic.provided_types() == ["Any"],
          f"Prism Energy on a Basic stays ONE wildcard unit, got {basic.provided_types()}")
    check(can_pay_cost(basic, ("Fighting",)) and not can_pay_cost(basic, ("Fighting", "Fighting")),
          "Prism Energy provides only 1 Energy at a time — it must not pay a 2-symbol cost")

    # --- 4. Plain energies are still counted identically (units == cards). -----
    plain = InPlayPokemon(card=db.get("Cynthia's Garchomp ex"))
    plain.energy = [fighting, fighting]
    check(can_pay_cost(plain, ("Fighting", "Fighting"))
          and not can_pay_cost(plain, ("Fighting", "Fighting", "Fighting")),
          "two Basic Fighting Energy pay exactly two symbols, no more")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_neo_upper_energy.py: all checks passed — 2 wildcard units on a Stage 2 "
          "(pays Draconic Buster's [F][F] alone), plain Colorless on a Basic/Stage 1, "
          "Prism Energy's 1-unit wildcard unchanged")


if __name__ == "__main__":
    main()
