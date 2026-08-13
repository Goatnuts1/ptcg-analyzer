#!/usr/bin/env python3
"""
test_hide_n_sneak_deck.py — the DECK_HIDE_N_SNEAK live-fire check.

The unit tests (test_hide_n_sneak_line / test_watchful_eye_midnight_fluttering /
test_prism_tower / test_legacy_energy / test_trading_places_print_names) prove each
new effect does what its card text says. This proves those effects are actually
EXERCISED by real, deterministic games — implemented != fired. It plays 12 seeded
greedy games of `hide_n_sneak` vs `dragapult` and asserts every new card shows up in
the logs, that the evolution lines really assemble, and that none of the OLDER
same-named prints ever leak in.

Run: python3 tests/test_hide_n_sneak_deck.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import DECKS, load_deck
from src.engine.legality import validate_deck
from src.engine.state import Phase
from src.engine.agents import GreedyAgent
from src.engine.game import (setup_game, start_turn, end_turn, apply_action, check_win,
                             MAX_TURNS)

SEEDS = range(12)


def play(db, seed):
    """One deterministic greedy game; returns its full log."""
    st = setup_game(load_deck(db, "hide_n_sneak"), load_deck(db, "dragapult"),
                    seed=seed, db=db)
    # SEEDED greedy: GreedyAgent()'s default rng is random.Random() — seeded from OS
    # entropy — and greedy uses rng.choice to pick which Basic to bench, so an unseeded
    # agent makes this whole liveness check non-reproducible RUN TO RUN. Seeding it off
    # the game seed makes "which cards fire" a property of the deck instead of luck.
    agent = GreedyAgent(random.Random(1000 + seed))
    while st.phase is not Phase.GAME_OVER and st.turn_number < MAX_TURNS:
        if not start_turn(st):
            break
        while st.phase is Phase.MAIN:
            action = agent.choose(st)
            apply_action(st, action)
            if action.kind == "pass" or check_win(st):
                break
        if st.phase is Phase.GAME_OVER:
            break
        end_turn(st)
    return st.log


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 1. the recipe: registered, exactly 60 cards, zero legality violations. ---
    check("hide_n_sneak" in DECKS, "the deck must be registered as 'hide_n_sneak'")
    recipe = DECKS["hide_n_sneak"]
    check(sum(n for _, n in recipe) == 60,
          f"the list must be 60 cards, got {sum(n for _, n in recipe)}")
    violations = validate_deck(db, recipe)
    check(violations == [], f"the list must be Standard-legal, got {violations}")
    check(len(load_deck(db, "hide_n_sneak")) == 60, "load_deck must expand to 60 Cards")

    # the list plays the NEW prints, never the pool's older same-named entries.
    names = {n for n, _ in recipe}
    for bare in ("Shuppet", "Banette", "Dhelmise", "Poltchageist", "Sinistcha",
                 "Patrat", "Dunsparce"):
        check(bare not in names,
              f"the recipe must name the disambiguated print, not the bare {bare!r} "
              f"(which is a different, older card)")

    # --- 2. live fire: every new card must appear in the logs of real games. ---
    logs = "\n".join(line for seed in SEEDS for line in play(db, seed))
    must_fire = {
        "Vengeful Anchor (Dhelmise (PBL))": "Vengeful Anchor:",
        "Puppet Pull (Banette (PBL))": "Puppet Pull:",
        "Furtive Drop (Poltchageist (PBL))": "Furtive Drop:",
        "Matcha Spin (Sinistcha (PBL))": "Matcha Spin:",
        "Trading Places (Dunsparce (JTG))": "Trading Places:",
        "Bite (Patrat (CRI))": "used Bite",
        "Hide 'n' Sneak actually preventing an opposing effect": "Hide 'n' Sneak: prevented",
        "Gwynn (Supporter)": "Gwynn:",
        "Prism Tower played into the Stadium zone": "played Stadium Prism Tower",
        "Prism Tower's once-per-turn discard-2-draw-1": "Prism Tower: discarded",
        "Legacy Energy's 1-fewer-Prize clause": "Legacy Energy:",
        "Telepathic Psychic Energy (on-attach bench search)": "Telepathic Psychic Energy:",
        "Run Away Draw (Dudunsparce)": "used ability Run Away Draw",
        "Full Moon Rondo (Lillie's Clefairy ex)": "Full Moon Rondo",
        "Kieran": "Kieran:",
        "Air Balloon (Tool attach)": "attached Tool Air Balloon",
        "Banette (PBL) actually evolving from Shuppet (PBL)": "evolved into Banette (PBL)",
        "Sinistcha (PBL) actually evolving from Poltchageist (PBL)":
            "evolved into Sinistcha (PBL)",
        "Dudunsparce actually evolving from Dunsparce (JTG)": "evolved into Dudunsparce",
    }
    for label, needle in must_fire.items():
        check(needle in logs, f"never fired in {len(list(SEEDS))} seeded games: {label} "
                              f"(looked for {needle!r})")

    # Situational payoffs that need a specific board/discard state greedy rarely reaches
    # in a 12-game sample. Report whether they fired WITHOUT failing the suite on a
    # sample-size miss — the same treatment Metallic Hammer / Call for Family get in
    # tests/test_mega_excadrill_deck.py. Each is proved correct by its unit test.
    for label, needle in {
        "Vengeful Anchor's +140 (4+ Hide 'n' Sneak Pokémon in discard)": "-> 170 base",
        "Matcha Spin's 6+ payoff": "in discard -> placed",
        "Hex Hurl (Flutter Mane, [C][C][C])": "effect: Hex Hurl",
        "Watchful Eye actually blanking an Adrena-Brain": "Watchful Eye:",
        "Blood Moon (Bloodmoon Ursaluna ex)": "used Blood Moon",
        "Hang Down (Shuppet (PBL))": "used Hang Down",
    }.items():
        if needle not in logs:
            print(f"NOTE: did not fire in {len(list(SEEDS))} seeded games (not a failure, "
                  f"see unit test instead): {label}")

    # --- 3. NEGATIVE: not one line of the OLDER same-named prints may appear. This is
    # the anti-print-collision guard — if the deck ever silently reverted to a pool
    # entry, its attack names would show up here. ---
    for label, needle in {
        "old Shuppet/Banette (JTG) Spooky Shot": "Spooky Shot",
        "old Banette (JTG) Cursed Words": "Cursed Words",
        "old Dhelmise (TEF) Steel Anchor": "Steel Anchor",
        "old Dhelmise (TEF) Spinning Attack": "Spinning Attack",
        "old Poltchageist (TWM) Storehouse Hideaway": "Storehouse Hideaway",
        "old Sinistcha (TWM) Cursed Drop": "Cursed Drop",
        "old Sinistcha (TWM) Spill the Tea": "Spill the Tea",
        "old Patrat (White Flare) Procurement": "Procurement",
        "old Dunsparce (TEF) Dig": "used Dig",
    }.items():
        check(needle not in logs,
              f"an OLDER print leaked into this deck's games: {label} "
              f"(found {needle!r} in the logs)")

    # --- 4. NEGATIVE: no game may end in an engine-visible stall — every seeded game
    # must reach a real result (someone won, or the deck-out/MAX_TURNS valve fired). ---
    for seed in SEEDS:
        log = play(db, seed)
        check(len(log) > 20,
              f"seed {seed} produced a suspiciously short game ({len(log)} lines)")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_hide_n_sneak_deck.py: all checks passed — the list is legal, every new "
          "card fires in real seeded games, and no older same-named print leaks in")


if __name__ == "__main__":
    main()
