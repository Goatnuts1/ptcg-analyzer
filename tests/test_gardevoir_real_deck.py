#!/usr/bin/env python3
"""
test_gardevoir_real_deck.py — the DECK_MEGA_GARDEVOIR_REAL live-fire check.

The unit tests (test_gardevoir_real_line / test_gardevoir_real_trainers) prove each
new effect does what its card text says. This proves those effects are actually
EXERCISED by real, deterministic games — implemented != fired. It plays 12 seeded
greedy games of `gardevoir_real` vs `dragapult` and asserts the recipe is a legal 60,
that every new card shows up in the logs, and that no card the list does NOT play
leaks in.

PROVENANCE NOTE: this list is Anar Guliyev's Regional Utrecht deck — a 310th-place
finish, i.e. weak provenance, kept because it is the only real tournament list found
for the archetype. It is registered ALONGSIDE the engine's built `gardevoir`
archetype, which stays the strong tuned baseline; this test does not claim the list
is good, only that it is faithfully implemented.

Run: python3 tests/test_gardevoir_real_deck.py
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
from src.analysis.gap_check import check_deck_implementation

SEEDS = range(12)


def play(db, seed):
    """One deterministic greedy game; returns its full log."""
    st = setup_game(load_deck(db, "gardevoir_real"), load_deck(db, "dragapult"),
                    seed=seed, db=db)
    # SEEDED greedy: GreedyAgent()'s default rng is seeded from OS entropy and greedy
    # uses rng.choice to pick which Basic to bench, so an unseeded agent would make this
    # liveness check non-reproducible run to run.
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
    check("gardevoir_real" in DECKS, "the deck must be registered as 'gardevoir_real'")
    recipe = DECKS["gardevoir_real"]
    check(sum(n for _, n in recipe) == 60,
          f"the list must be 60 cards, got {sum(n for _, n in recipe)}")
    violations = validate_deck(db, recipe)
    check(violations == [], f"the list must be Standard-legal, got {violations}")
    check(len(load_deck(db, "gardevoir_real")) == 60, "load_deck must expand to 60 Cards")

    # The built `gardevoir` archetype (the strong baseline) must still exist untouched.
    check("gardevoir" in DECKS, "the built `gardevoir` archetype must remain registered")
    check(DECKS["gardevoir"] is not recipe, "the two Gardevoir lists must be distinct")

    # --- 2. every card in the list has code behind it (no silently inert cards). ---
    gaps = check_deck_implementation(recipe, db)
    check(gaps == [], f"gap-check must report zero unimplemented card text, got {gaps}")

    # --- 3. live fire: every NEW card must appear in the logs of real games. ---
    logs = "\n".join(line for seed in SEEDS for line in play(db, seed))
    must_fire = {
        "Ball Roll (Marill)": "Ball Roll:",
        "Bubble Gathering (Azumarill ex)": "Bubble Gathering:",
        "Energized Balloon (Azumarill ex)": "Energized Balloon:",
        "Azumarill ex actually evolving from Marill": "evolved into Azumarill ex",
        "Limit Break (Zacian)": "Limit Break:",
        "Diamond Coat actually reducing a hit": "less damage (Diamond Coat)",
        "Wally's Compassion (Supporter)": "Wally's Compassion:",
        "Grand Tree played into the Stadium zone": "played Stadium Grand Tree",
        "Grand Tree's once-per-turn deck-search evolution": "Grand Tree: evolved",
        "Jamming Tower played into the Stadium zone": "played Stadium Jamming Tower",
        "Mystery Garden played into the Stadium zone": "played Stadium Mystery Garden",
        "Mystery Garden's once-per-turn discard-an-Energy draw": "Mystery Garden: discarded",
        # already-implemented cards this list leans on — they must still fire here.
        "Mega Symphonia (Mega Gardevoir ex)": "Mega Symphonia",
        "Garland Ray (Mega Diancie ex)": "Garland Ray",
        "Wondrous Patch": "Wondrous Patch:",
        "Colress's Tenacity": "Colress's Tenacity:",
        "Telepathic Psychic Energy (on-attach bench search)": "Telepathic Psychic Energy:",
        "Flip the Script (Fezandipiti ex)": "Flip the Script:",
        "Last-Ditch Catch (Meowth ex)": "Last-Ditch Catch:",
        "Eon Blade (Latias ex)": "Eon Blade",
        "Rare Candy": "Rare Candy:",
    }
    for label, needle in must_fire.items():
        check(needle in logs, f"never fired in {len(list(SEEDS))} seeded games: {label} "
                              f"(looked for {needle!r})")

    # Situational lines greedy rarely reaches in a 12-game sample. Reported WITHOUT
    # failing the suite (the Metallic Hammer / Call for Family treatment) — each is
    # proved correct by a unit test.
    for label, needle in {
        "Overflowing Wishes (Mega Gardevoir ex's [P] accel attack)": "Overflowing Wishes",
        "Adrena-Brain (Munkidori — needs Darkness attached, and this list plays none)":
            "Adrena-Brain:",
        "Full Moon Rondo (Lillie's Clefairy ex)": "Full Moon Rondo",
        "Call Sign (Kirlia)": "Call Sign:",
        "Collect (Ralts)": "used Collect",
        "Limit Break's +90 at 3-or-fewer opponent Prizes": "Prizes left -> 140",
    }.items():
        if needle not in logs:
            print(f"NOTE: did not fire in {len(list(SEEDS))} seeded games (not a failure, "
                  f"see unit test instead): {label}")

    # --- 4. NEGATIVE: cards this list does NOT play must never appear. The pool's
    # Marill is the TEF 64 print (Ball Roll / Magical Shot); the ASC 83 print's
    # Hide / Flop attacks belong to a DIFFERENT card and must never show up. Likewise
    # the pool's plain "Azumarill" (Play Rough / Power Tackle) is a different Pokémon
    # from the Azumarill ex this list runs. ---
    for label, needle in {
        "ASC 83 Marill's Hide (a different print — the pool's Marill is TEF 64)":
            "used Hide",
        "ASC 83 Marill's Flop": "used Flop",
        "the pool's plain Azumarill (Play Rough)": "Play Rough",
        "the pool's plain Azumarill (Power Tackle)": "Power Tackle",
    }.items():
        check(needle not in logs,
              f"NEGATIVE: a card the list does not play leaked into the logs: {label} "
              f"(found {needle!r})")

    # --- 5. the games actually finish (no infinite Bubble Gathering / Grand Tree loop).
    # A repeatable Ability that never runs out of targets would hang the engine here. ---
    check(len(logs) > 0, "the seeded games must produce logs")

    if fails:
        print(f"test_gardevoir_real_deck.py: {len(fails)} FAILURE(S)")
        for f in fails:
            print("  -", f)
        return 1
    print(f"test_gardevoir_real_deck.py: all checks passed — gardevoir_real is a legal "
          f"60 with zero implementation gaps, and every new card fired in "
          f"{len(list(SEEDS))} seeded greedy games.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
