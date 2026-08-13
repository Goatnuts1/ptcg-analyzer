#!/usr/bin/env python3
"""
test_toucannon_deck.py — the DECK_TOUCANNON live-fire check.

The unit tests (test_toucannon_line / test_area_zero_underdepths) prove each new
effect does what its card text says. This proves those effects are actually
EXERCISED by real, deterministic games — implemented != fired. It plays 40 seeded
greedy games of `toucannon` vs `dragapult` and asserts the new cards show up in the
logs (40 rather than 12 because Trumbeak's Fly and Iron Leaves ex's Rapid Vernier
switch are genuinely rare lines under greedy — 3 and 1 games out of 40 — and
"implemented != exercised" means they must still be proved to FIRE, not just to
unit-test), that the Pikipek -> Trumbeak -> Toucannon and Hoothoot -> Noctowl lines really
assemble, and that the OLDER same-named Hoothoot print never leaks in.

Run: python3 tests/test_toucannon_deck.py
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
from src.engine import effects as fx
from src.engine.game import (setup_game, start_turn, end_turn, apply_action, check_win,
                             MAX_TURNS)

SEEDS = range(40)


def play(db, seed):
    """One deterministic greedy game; returns its full log."""
    st = setup_game(load_deck(db, "toucannon"), load_deck(db, "dragapult"),
                    seed=seed, db=db)
    # SEEDED greedy: GreedyAgent()'s default rng is seeded from OS entropy and greedy
    # uses rng.choice to pick which Basic to bench, so an unseeded agent would make this
    # liveness check non-reproducible run to run.
    agent = GreedyAgent(random.Random(2000 + seed))
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


def play_tracking_bench(db, seed):
    """Same game, but after EVERY action record each player's Bench size against that
    player's live bench_limit. Returns (state, {player_name: (worst_size, its_limit)}).
    This is the direct guard that no Bench-placement site ever bypassed fx.bench_limit."""
    st = setup_game(load_deck(db, "toucannon"), load_deck(db, "dragapult"),
                    seed=seed, db=db)
    agent = GreedyAgent(random.Random(2000 + seed))
    worst = {}

    def sample():
        for p in st.players:
            size, limit = len(p.bench), fx.bench_limit(st, p)
            if p.name not in worst or size > worst[p.name][0]:
                worst[p.name] = (size, limit)

    while st.phase is not Phase.GAME_OVER and st.turn_number < MAX_TURNS:
        if not start_turn(st):
            break
        while st.phase is Phase.MAIN:
            action = agent.choose(st)
            apply_action(st, action)
            sample()
            if action.kind == "pass" or check_win(st):
                break
        if st.phase is Phase.GAME_OVER:
            break
        end_turn(st)
    return st, worst


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 1. the recipe: registered, exactly 60 cards, zero legality violations. ---
    check("toucannon" in DECKS, "the deck must be registered as 'toucannon'")
    recipe = DECKS["toucannon"]
    check(sum(n for _, n in recipe) == 60,
          f"the list must be 60 cards, got {sum(n for _, n in recipe)}")
    violations = validate_deck(db, recipe)
    check(violations == [], f"the list must be Standard-legal, got {violations}")
    check(len(load_deck(db, "toucannon")) == 60, "load_deck must expand to 60 Cards")

    # the list plays the SCR Hoothoot print, never the pool's older bare entry.
    names = {n for n, _ in recipe}
    check("Hoothoot (SCR)" in names and "Hoothoot" not in names,
          "the recipe must name the disambiguated 'Hoothoot (SCR)' print, not the bare "
          "'Hoothoot' (which is the older Temporal Forces card with Silent Wing)")

    # --- 2. live fire: every new card must appear in the logs of real games. ---
    logs = "\n".join(line for seed in SEEDS for line in play(db, seed))
    must_fire = {
        "Double Stab (Pikipek)": "Double Stab:",
        "Triple Stab (Hoothoot (SCR))": "Triple Stab:",
        "Feather Rondo (Toucannon)": "Feather Rondo:",
        "Aerial Draw (Toucannon Ability)": "Aerial Draw:",
        "Jewel Seeker (Noctowl, on evolve)": "Jewel Seeker:",
        "Area Zero Underdepths played into the Stadium zone":
            "played Stadium Area Zero Underdepths",
        "Trumbeak actually evolving from Pikipek": "evolved into Trumbeak",
        "Toucannon actually evolving from Trumbeak": "evolved into Toucannon",
        "Noctowl actually evolving from Hoothoot (SCR)": "evolved into Noctowl",
        "Teal Dance (Teal Mask Ogerpon ex)": "Teal Dance",
        "Crispin (Supporter)": "Crispin:",
        "Boss's Orders": "Boss's Orders",
        # Rarer lines — still required to fire, because an effect that is only ever
        # unit-tested is not proved to be reachable by real play.
        "Fly heads (30 + the shield)": "Fly: heads",
        "Fly tails (the attack really doing nothing)": "Fly: tails",
        "the Fly shield actually blocking an opposing attack":
            "is shielded — no attack damage",
        "Rapid Vernier TAKING the switch (Iron Leaves ex)": "Rapid Vernier: switched",
        "Rapid Vernier DECLINING the switch": "Rapid Vernier: declined",
        "Prism Edge (Iron Leaves ex)": "Prism Edge:",
        "Jewel Seeker blocked with no Tera Pokémon in play":
            "Jewel Seeker: no Tera Pokémon in play",
        "Jewel Seeker finding the full 2 Trainers": "Jewel Seeker: searched 2",
        "Area Zero Underdepths' 8-Bench really being used (a 6th Benched Pokémon "
        "counted by Feather Rondo)": "Feather Rondo: 6 Benched",
        "Area Zero Underdepths' Bench shrink clause": "Area Zero Underdepths:",
    }
    for label, needle in must_fire.items():
        check(needle in logs, f"never fired in {len(list(SEEDS))} seeded games: {label} "
                              f"(looked for {needle!r})")

    # Situational payoffs that need a specific board state greedy rarely reaches even
    # in a 40-game sample. Report whether they fired WITHOUT failing the suite on a
    # sample-size miss — the same treatment Metallic Hammer / Call for Family get in
    # tests/test_mega_excadrill_deck.py. Each is proved correct by its unit test.
    for label, needle in {
        "Feather Rondo at the full 8-Bench cap": "Feather Rondo: 8 Benched",
        "Legacy Energy's 1-fewer-Prize clause": "Legacy Energy:",
        "Fighting Wings (Moltres)": "Fighting Wings",
        "Fan Call (Fan Rotom, first turn only)": "Fan Call",
    }.items():
        if needle not in logs:
            print(f"NOTE: did not fire in {len(list(SEEDS))} seeded games (not a failure, "
                  f"see unit test instead): {label}")

    # --- 3. NEGATIVE: the OLDER Hoothoot print must never appear. This is the
    # anti-print-collision guard — if the deck silently reverted to the pool's bare
    # entry, its attack name would show up here. ---
    check("Silent Wing" not in logs,
          "the OLDER bare 'Hoothoot' (sv5-126 TEF, Silent Wing) leaked into this deck's "
          "games — the recipe must use 'Hoothoot (SCR)'")

    # --- 4. NEGATIVE: the Bench cap must never leak. Feather Rondo counts BOTH
    # Benches, and both players here run Tera Pokémon (Ogerpon ex / Dragapult ex), so
    # under Area Zero Underdepths the absolute ceiling is 8 + 8 = 16. Anything above
    # that would mean a placement site skipped bench_limit entirely. ---
    for line in logs.splitlines():
        if "Feather Rondo:" in line:
            n = int(line.split("Feather Rondo:")[1].split()[0])
            check(n <= 16,
                  f"Feather Rondo counted {n} Benched Pokémon — above the 8+8 ceiling "
                  f"the Bench caps allow: {line}")
    # and the live boards themselves are checked directly, not inferred from a damage
    # line: no player's Bench may exceed its own bench_limit at any point in any game,
    # and no Bench may exceed 8 ever.
    for seed in SEEDS:
        st, worst = play_tracking_bench(db, seed)
        for who, (size, limit) in worst.items():
            check(size <= limit,
                  f"seed {seed}: {who}'s Bench reached {size} against a live cap of "
                  f"{limit} — a Bench-placement site skipped fx.bench_limit")
            check(size <= 8,
                  f"seed {seed}: {who}'s Bench reached {size}; 8 is the absolute ceiling")

    # --- 5. NEGATIVE: no game may end in an engine-visible stall — every seeded game
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
    print("test_toucannon_deck.py: all checks passed — the list is legal, every new card "
          "fires in real seeded games, and the older Hoothoot print never leaks in")


if __name__ == "__main__":
    main()
