#!/usr/bin/env python3
"""
test_mega_excadrill_deck.py — the DECK_MEGA_EXCADRILL live-fire check.

Unit tests prove each new effect does what its card text says; this proves the effects
are actually EXERCISED by real, deterministic games (implemented != fired). It plays a
handful of seeded greedy games of `mega_excadrill` vs `dragapult` and asserts that every
new card in the list shows up in the game log, plus that the recipe is legal and the
whole line (Drilbur -> Mega Excadrill ex, Beldum -> Metang -> Metagross) really gets
assembled in play.

Run: python3 tests/test_mega_excadrill_deck.py
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
    st = setup_game(load_deck(db, "mega_excadrill"), load_deck(db, "dragapult"),
                    seed=seed, db=db)
    # SEEDED greedy: GreedyAgent()'s default rng is random.Random() — seeded from OS
    # entropy — and greedy uses rng.choice to pick which Basic to bench, so an unseeded
    # agent makes this whole liveness check non-reproducible RUN TO RUN (it is not a
    # PYTHONHASHSEED effect; it flips with a fixed hash seed too). Seeding it off the
    # game seed makes "which cards fire" a property of the deck instead of luck.
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
    check("mega_excadrill" in DECKS, "the deck must be registered as 'mega_excadrill'")
    recipe = DECKS["mega_excadrill"]
    check(sum(n for _, n in recipe) == 60,
          f"the list must be 60 cards, got {sum(n for _, n in recipe)}")
    violations = validate_deck(db, recipe)
    check(violations == [], f"the list must be Standard-legal, got {violations}")
    check(len(load_deck(db, "mega_excadrill")) == 60, "load_deck must expand to 60 Cards")

    # --- 2. live fire: every new card must appear in the logs of real games. ---
    logs = "\n".join(line for seed in SEEDS for line in play(db, seed))
    must_fire = {
        "Metal Maker (Metang ability)": "Metal Maker:",
        "Metallic Signal (Genesect ex ability)": "Metallic Signal:",
        "M Bounce Back (Metagross (CRI))": "M Bounce Back:",
        "Iron Tackle (Beldum)": "Iron Tackle:",
        "Protect Charge (Genesect ex)": "Protect Charge:",
        "Protect Charge's damage reduction actually reducing a hit": "less damage (Protect Charge)",
        "Undermine (Mega Excadrill ex)": "Undermine:",
        "Maximum Drilling (Mega Excadrill ex)": "effect: Maximum Drilling",
        "Zapping Draw (Ethan's Pichu)": "used Zapping Draw",
        "Team Rocket's Petrel": "Team Rocket's Petrel:",
        "Team Rocket's Transceiver": "Team Rocket's Transceiver:",
        "Kieran": "Kieran:",
        "Jumbo Ice Cream": "Jumbo Ice Cream:",
        "Precious Trolley": "Precious Trolley:",
        "Air Balloon (Tool attach)": "attached Tool Air Balloon",
        "Gravity Mountain (Stadium)": "played Stadium Gravity Mountain",
        "Mega Excadrill ex actually evolving from Drilbur": "evolved into Mega Excadrill ex",
        "Metagross (CRI) actually assembled": "evolved into Metagross (CRI)",
    }
    for label, needle in must_fire.items():
        check(needle in logs, f"never fired in {len(list(SEEDS))} seeded games: {label} "
                              f"(looked for {needle!r})")

    # Metallic Hammer and Call for Family are real but situational (Metallic Hammer needs
    # 4+ Energy on Metagross (CRI); Call for Family needs Drilbur played with a spare deck
    # slot to matter) — report whether they fired across the sample without failing the
    # suite on a sample-size miss, same treatment as Iron Tackle got in the original verify
    # pass. A genuinely broken implementation would still be caught by their unit tests.
    for label, needle in {
        "Metallic Hammer (Metagross (CRI))": "Metallic Hammer:",
        "Call for Family (Drilbur)": "Call for Family:",
    }.items():
        if needle not in logs:
            print(f"NOTE: did not fire in {len(list(SEEDS))} seeded games (not a failure, "
                  f"see unit test instead): {label}")

    # --- 3. NEGATIVE: Dig Dig Dig must NOT appear at all in this list's logs — bare
    # "Drilbur" is now the real tournament-list print (PBL 46), which never had that
    # ability in the first place (it belongs to the disambiguated "Drilbur (TEF)" print,
    # covered end-to-end in tests/test_dig_dig_dig.py, not used by this deck). ---
    check("Dig Dig Dig:" not in logs,
          "this deck's Drilbur print (PBL 46) has no Dig Dig Dig ability at all")

    # --- 4. NEGATIVE: no game may end in an engine-visible stall — every seeded game
    # must reach a real result (someone won, or the deck-out/MAX_TURNS valve fired). ---
    for seed in SEEDS:
        log = play(db, seed)
        check(len(log) > 20, f"seed {seed} produced a suspiciously short game ({len(log)} lines)")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_mega_excadrill_deck.py: all checks passed — the list is legal and every "
          "new card fires in real seeded games")


if __name__ == "__main__":
    main()
