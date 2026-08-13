#!/usr/bin/env python3
"""
test_gap_check.py — the gap-check heuristic flags exactly what it should:
unregistered attack/ability text, unregistered Trainers, and unhandled Special
Energy — and NOT the cards the engine implements at a passive chokepoint.

Two blind spots this pins down, both of which let a silently-inert card through
(or cried wolf over a working one) in the cynthia_garchomp verification:
  * a passive Stadium / Pokémon Tool is implemented via STADIUM_IMPLEMENTED /
    TOOL_IMPLEMENTED and never appears in TRAINER_EFFECTS — checking only
    TRAINER_EFFECTS false-flagged Team Rocket's Watchtower and Cynthia's Power
    Weight, both of which work;
  * Special Energy was skipped entirely ("needs nothing"), so Neo Upper Energy's
    unimplemented "provides 2 Energy at a time" clause was never reported.

Run: python3 tests/test_gap_check.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card, Attack, Ability, CardDB
from src.analysis.gap_check import check_deck_implementation
from src.engine import effects as fx


def make_card(name, supertype="Pokémon", subtypes=(), abilities=(), attacks=(),
              regulation_mark="H", rules=(), types=("Colorless",)):
    return Card(
        id=f"test-{name}", name=name, supertype=supertype, subtypes=subtypes,
        hp=100 if supertype == "Pokémon" else None, types=types,
        evolves_from=None, evolves_to=(), abilities=abilities, attacks=attacks,
        rules=rules, weaknesses=(), resistances=(), retreat_cost=1,
        regulation_mark=regulation_mark,
    )


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # A real, already-implemented card: Crustle's Mysterious Rock Inn (passive
    # ability) + Superb Scissors (attack with effect text) — both registered.
    # A plain damage attack (no text) never needs an entry.
    crustle = make_card(
        "Crustle",
        abilities=(Ability(name="Mysterious Rock Inn", text="Prevent all damage..."),),
        attacks=(
            Attack(name="Superb Scissors", cost=(), damage=120, damage_suffix="",
                   text="This attack's damage isn't affected by any effects..."),
            Attack(name="Plain Tackle", cost=(), damage=30, damage_suffix="", text=""),
        ),
    )
    # A fabricated card with an unregistered ability AND an unregistered attack
    # with real effect text — both must be flagged.
    fake_mon = make_card(
        "Test Fakemon",
        abilities=(Ability(name="Made Up Power", text="Do something novel."),),
        attacks=(Attack(name="Made Up Strike", cost=(), damage=50, damage_suffix="",
                        text="Something novel happens."),),
    )
    boss = make_card("Boss's Orders", supertype="Trainer", subtypes=("Supporter",))
    fake_trainer = make_card("Test Fake Trainer", supertype="Trainer", subtypes=("Item",))
    basic_energy = make_card("Basic Fire Energy", supertype="Energy", subtypes=("Basic",))

    db = CardDB([crustle, fake_mon, boss, fake_trainer, basic_energy])

    recipe = [
        ("Crustle", 3), ("Test Fakemon", 2), ("Boss's Orders", 3),
        ("Test Fake Trainer", 1), ("Basic Fire Energy", 10),
    ]
    flagged = check_deck_implementation(recipe, db)
    by_card = {}
    for f in flagged:
        by_card.setdefault(f["card"], []).append(f)

    check("Crustle" not in by_card, "a fully-registered card must not be flagged")
    check("Boss's Orders" not in by_card, "a registered Trainer must not be flagged")
    check("Basic Fire Energy" not in by_card, "basic energy must never be flagged")

    fake_flags = by_card.get("Test Fakemon", [])
    check(len(fake_flags) == 2, f"expected 2 flags for Test Fakemon, got {len(fake_flags)}")
    check(any(f["kind"] == "ability" and f["name"] == "Made Up Power" for f in fake_flags),
          "unregistered ability must be flagged")
    check(any(f["kind"] == "attack" and f["name"] == "Made Up Strike" for f in fake_flags),
          "unregistered attack-with-text must be flagged")

    trainer_flags = by_card.get("Test Fake Trainer", [])
    check(len(trainer_flags) == 1 and trainer_flags[0]["kind"] == "trainer",
          "unregistered Trainer must be flagged exactly once")

    # --- passive Stadiums / Tools are implemented at chokepoints, NOT in
    # TRAINER_EFFECTS. Flagging them was a false positive on working cards. ---
    real_db = CardDB.from_pool("data/standard_pool.json")
    passive_trainers = [("Team Rocket's Watchtower", 2),   # STADIUM_IMPLEMENTED
                        ("Cynthia's Power Weight", 3),     # TOOL_IMPLEMENTED
                        ("Battle Cage", 2),                # STADIUM_IMPLEMENTED
                        ("Brave Bangle", 2)]               # TOOL_IMPLEMENTED
    flags = check_deck_implementation(passive_trainers, real_db)
    check(flags == [], f"passive Stadiums/Tools must not be flagged, got "
                       f"{[f['card'] for f in flags]}")

    # A genuinely unimplemented Stadium must still be flagged (the fix must not
    # have turned the Trainer check into a rubber stamp). Granite Cave is the
    # current fixture. (This used to be Area Zero Underdepths, then Academy at
    # Night — each now implemented, which would have turned this guard into a
    # false pass.)
    check("Granite Cave" not in fx.STADIUM_IMPLEMENTED,
          "setup: Granite Cave must still be an unimplemented Stadium for this "
          "guard to mean anything")
    flags = check_deck_implementation([("Granite Cave", 1)], real_db)
    check(len(flags) == 1 and flags[0]["kind"] == "trainer",
          "an unimplemented Stadium must still be flagged")

    # --- Special Energy. A plain "provides <Type> Energy" card needs no handler
    # (provided_types reads the pool's `types`); anything with a real rider or a
    # conditional provision clause must be flagged unless it's registered. ---
    flags = check_deck_implementation([("Rocky Fighting Energy", 3),   # registered
                                       ("Neo Upper Energy", 1),        # registered
                                       ("Prism Energy", 4),            # registered
                                       ("Basic Fighting Energy", 4)],  # basic
                                      real_db)
    check(flags == [], f"implemented/basic Energy must not be flagged, got "
                       f"{[f['card'] for f in flags]}")
    flags = check_deck_implementation([("Boomerang Energy", 2)], real_db)
    check(len(flags) == 1 and flags[0]["kind"] == "energy",
          "an unimplemented Special Energy with a rider must be flagged")

    plain_energy = make_card(
        "Test Plain Energy", supertype="Energy", subtypes=("Special",),
        types=("Water",),
        rules=("As long as this card is attached to a Pokémon, it provides Water Energy.",),
    )
    conditional_energy = make_card(
        "Test Conditional Energy", supertype="Energy", subtypes=("Special",), types=(),
        rules=("As long as this card is attached to a Pokémon, it provides Colorless "
               "Energy.  If this card is attached to a Stage 2 Pokémon, this card "
               "provides every type of Energy but provides only 2 Energy at a time.",),
    )
    edb = CardDB([plain_energy, conditional_energy])
    check(check_deck_implementation([("Test Plain Energy", 4)], edb) == [],
          "a plain provides-one-type Special Energy needs no handler and must not be flagged")
    flags = check_deck_implementation([("Test Conditional Energy", 1)], edb)
    check(len(flags) == 1 and flags[0]["kind"] == "energy",
          "a conditional-provision Special Energy with no handler MUST be flagged "
          "(this is the Neo Upper Energy blind spot)")

    # A card appearing twice in the recipe (shouldn't happen but be defensive)
    # must not be double-flagged.
    dup_recipe = [("Test Fakemon", 2)]
    flagged_once = check_deck_implementation(dup_recipe, db)
    flagged_twice_input = check_deck_implementation(dup_recipe + dup_recipe, db)
    check(len(flagged_once) == len(flagged_twice_input),
          "a repeated recipe entry for the same card must not duplicate flags")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print(f"test_gap_check.py: all checks passed ({len(flagged)} gaps found in fixture deck, as expected)")


if __name__ == "__main__":
    main()
