#!/usr/bin/env python3
"""
test_doublade_deck.py — the DECK_DOUBLADE live-fire check.

Unit tests prove each new effect does what its card text says; this proves the effects
are actually EXERCISED by real, deterministic games (implemented != fired). It plays
seeded greedy games of `doublade` vs `dragapult` and asserts the recipe is legal, that
every new card shows up in the game logs, and that both evolution lines really get
assembled in play.

THE HEADLINE CHECK is section 3: Weaponized Swords REVEALS from hand rather than
discarding, so the same cards must keep paying turn after turn. That is unusual enough
for this engine that a synthetic unit test isn't sufficient evidence — so this file
instruments REAL games, snapshotting the acting player's hand immediately before and
after every Weaponized Swords swing and asserting no Honedge / Doublade / Aegislash
ever left it, plus finding a real game in which the attack fires more than once with a
strictly GROWING revealed count.

Run: python3 tests/test_doublade_deck.py
"""

import random
import re
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import DECKS, load_deck
from src.engine.legality import validate_deck
from src.engine.state import Phase
from src.engine.agents import GreedyAgent
from src.engine.game import (setup_game, start_turn, end_turn, apply_action, check_win,
                             MAX_TURNS)

# 30 seeds, not 12. Greedy evolves eagerly, so it plays the Aegislash line OUT of hand
# instead of holding the swords as ammunition — the archetype's actual plan is one this
# policy under-expresses (see CLAUDE.md's "greedy mispilots complex decks"). A wider
# DETERMINISTIC sweep is what it takes to observe repeated Weaponized Swords use in real
# games; the sample is still fully reproducible, just bigger.
SEEDS = range(30)

LINE_NAMES = ("Honedge", "Doublade", "Aegislash")


def play(db, seed):
    """One deterministic greedy game.

    Returns (log, swings, finished) where `swings` is one record per Weaponized Swords
    attack — (revealed_count_from_log, hand_line_counts_before, hand_line_counts_after) —
    and `finished` says the game reached a real terminal state rather than stalling.

    SEEDED greedy: GreedyAgent()'s default rng is random.Random() — seeded from OS
    entropy — and greedy uses rng.choice to pick which Basic to bench, so an unseeded
    agent makes this whole liveness check non-reproducible RUN TO RUN. Seeding it off
    the game seed makes "which cards fire" a property of the deck instead of luck.
    """
    st = setup_game(load_deck(db, "doublade"), load_deck(db, "dragapult"),
                    seed=seed, db=db)
    agent = GreedyAgent(random.Random(1000 + seed))
    swings = []

    def line_counts(player):
        return Counter(c.name for c in player.hand if c.name in LINE_NAMES)

    while st.phase is not Phase.GAME_OVER and st.turn_number < MAX_TURNS:
        if not start_turn(st):
            break
        while st.phase is Phase.MAIN:
            action = agent.choose(st)
            # Is this swing Weaponized Swords? Decide BEFORE applying — the attack ends
            # the turn and the active can be Knocked Out by retaliation.
            attacker_owner, before = None, None
            if (action.kind == "attack" and st.current.active is not None
                    and st.current.active.card.attacks[action.attack_index].name
                    == "Weaponized Swords"):
                attacker_owner = st.current
                before = line_counts(attacker_owner)
            log_len = len(st.log)
            apply_action(st, action)
            if attacker_owner is not None:
                after = line_counts(attacker_owner)
                revealed = None
                for line in st.log[log_len:]:
                    m = re.search(r"Weaponized Swords: revealed (\d+)", line)
                    if m:
                        revealed = int(m.group(1))
                swings.append((revealed, before, after))
            if action.kind == "pass" or check_win(st):
                break
        if st.phase is Phase.GAME_OVER:
            break
        end_turn(st)
    finished = st.phase is Phase.GAME_OVER or st.turn_number >= MAX_TURNS
    return st.log, swings, finished


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 1. the recipe: registered, exactly 60 cards, zero legality violations. ---
    check("doublade" in DECKS, "the deck must be registered as 'doublade'")
    recipe = DECKS["doublade"]
    check(sum(n for _, n in recipe) == 60,
          f"the list must be 60 cards, got {sum(n for _, n in recipe)}")
    violations = validate_deck(db, recipe)
    check(violations == [], f"the list must be Standard-legal, got {violations}")
    check(len(load_deck(db, "doublade")) == 60, "load_deck must expand to 60 Cards")

    # --- 2. live fire: every new card must appear in the logs of real games. ---
    games = [play(db, seed) for seed in SEEDS]
    logs = "\n".join(line for log, _, _ in games for line in log)
    must_fire = {
        "Weaponized Swords (Doublade)": "Weaponized Swords: revealed",
        "Metal Slash's can't-attack lock": "Metal Slash:",
        "X-Boot (Steven's Metagross ex ability)": "X-Boot: attached",
        "Team Rocket's Factory actually played as the Stadium":
            "played Stadium Team Rocket's Factory",
        "Team Rocket's Factory's conditional draw 2": "Team Rocket's Factory: drew",
        "Honedge -> Doublade": "evolved into Doublade",
        "Doublade -> Aegislash": "evolved into Aegislash",
        "Steven's Beldum -> Steven's Metang": "evolved into Steven's Metang",
        "Steven's Metang -> Steven's Metagross ex": "evolved into Steven's Metagross ex",
        "Rare Candy skipping a Stage 1": "Rare Candy:",
        "Metallic Signal (Genesect ex)": "Metallic Signal:",
        "Protect Charge (Genesect ex)": "Protect Charge:",
        "Flip the Script (Fezandipiti ex)": "Flip the Script",
        "Metal Stomp (Steven's Metagross ex)": "used Metal Stomp",
        "Slash (Aegislash)": "used Slash",
        "Cut (Honedge)": "used Cut",
        "Team Rocket's Petrel": "Team Rocket's Petrel:",
        "Team Rocket's Transceiver": "Team Rocket's Transceiver:",
        "Lillie's Determination": "Lillie's Determination:",
        "Dawn": "Dawn:",
        "Boss's Orders": "Boss's Orders:",
        "Poké Pad": "Poké Pad:",
        "Night Stretcher": "Night Stretcher:",
        "Energy Recycler": "Energy Recycler:",
        "Sacred Ash": "Sacred Ash:",
        "Buddy-Buddy Poffin": "Buddy-Buddy Poffin:",
        "Precious Trolley (ACE SPEC)": "Precious Trolley:",
        "Air Balloon (Tool attach)": "attached Tool Air Balloon",
        "Brave Bangle (Tool attach)": "attached Tool Brave Bangle",
    }
    for label, needle in must_fire.items():
        check(needle in logs, f"never fired in {len(list(SEEDS))} seeded games: {label} "
                              f"(looked for {needle!r})")

    # Fezandipiti ex's Cruel Arrow is real but situational (greedy would have to promote
    # a 1-Prize support Basic into the Active Spot and pay [C][C][C] on it). Report
    # without failing the suite on a sample-size miss — the same treatment Metallic
    # Hammer / Call for Family get in test_mega_excadrill_deck.py.
    for label, needle in {"Cruel Arrow (Fezandipiti ex)": "used Cruel Arrow"}.items():
        if needle not in logs:
            print(f"NOTE: did not fire in {len(list(SEEDS))} seeded games (not a failure, "
                  f"see unit test instead): {label}")

    # --- 3. THE HEADLINE: Weaponized Swords reveals, it does not consume. ---
    all_swings = [s for _, swings, _ in games for s in swings]
    check(len(all_swings) >= 3,
          f"Weaponized Swords must actually be used in these games, got {len(all_swings)} "
          f"swings")

    # 3a. NOT ONE Honedge / Doublade / Aegislash ever left the attacker's hand because
    #     of a swing. (Counts may RISE — a Knock Out puts a Prize card in hand — so the
    #     assertion is "never decreased", checked per card name, on every swing of every
    #     game. This is the real-game form of the reveal-is-not-a-discard property.)
    for i, (revealed, before, after) in enumerate(all_swings):
        for name in LINE_NAMES:
            check(after[name] >= before[name],
                  f"swing {i}: Weaponized Swords REMOVED {before[name] - after[name]} "
                  f"{name} from hand — it reveals, it must never discard "
                  f"(before={dict(before)} after={dict(after)})")
        # 3b. and the number it claims to have revealed must be exactly the number of
        #     those cards that were in hand at the time.
        check(revealed == sum(before.values()),
              f"swing {i}: the log says {revealed} revealed but the hand held "
              f"{sum(before.values())} ({dict(before)})")

    # 3c. a REAL game in which the attack fires MORE THAN ONCE, with a strictly GROWING
    #     revealed count — the direct observable consequence of cards staying in hand
    #     (a discard-based version of this card could only ever shrink).
    repeat_games = [(seed, [s[0] for s in swings])
                    for seed, (_, swings, _) in zip(SEEDS, games) if len(swings) > 1]
    check(repeat_games,
          "no seeded game used Weaponized Swords more than once — the repeat-use property "
          "is unproven")
    growing = [(seed, counts) for seed, counts in repeat_games
               if any(b > a for a, b in zip(counts, counts[1:]))]
    check(growing,
          f"no seeded game showed a GROWING revealed count across uses; sequences seen: "
          f"{repeat_games}")
    if growing:
        print(f"  repeat-use evidence (seed, revealed-count per swing): {growing[0]}")
        print(f"  all repeat-use games: {repeat_games}")

    # --- 4. NEGATIVE: Aegislash must never use Weaponized Swords. It is a distinct card
    #        with two distinct attacks (the recon correction this line was most at risk
    #        of getting wrong), so no log line may ever pair the two. ---
    check("Aegislash used Weaponized Swords" not in logs,
          "Aegislash does not have Weaponized Swords — only Doublade does")
    check([a.name for a in db.get("Aegislash").attacks] == ["Slash", "Metal Slash"],
          "sanity: Aegislash's printed attacks are Slash and Metal Slash")

    # --- 5. NEGATIVE: the Factory's draw may never appear in a game where no Team
    #        Rocket Supporter was ever played. Checked per game, not in aggregate. ---
    for seed, (log, _, _) in zip(SEEDS, games):
        text = "\n".join(log)
        if "Team Rocket's Factory: drew" in text:
            check("Team Rocket's Petrel:" in text,
                  f"seed {seed}: the Factory drew without any Team Rocket Supporter "
                  f"having been played — its condition is not being enforced")

    # --- 6. NEGATIVE: no game may end in an engine-visible stall — every seeded game
    #        must reach a real TERMINAL STATE (someone won, or the deck-out / MAX_TURNS
    #        valve fired). Checked on the state, not on a log-length proxy: a legitimately
    #        fast game is fine (seed 2 loses on turn 3 with its lone Basic Knocked Out and
    #        an empty Bench), a game that just stops resolving is not.
    for seed, (log, _, finished) in zip(SEEDS, games):
        check(finished,
              f"seed {seed} never reached a terminal state ({len(log)} log lines) — the "
              f"game stalled instead of resolving")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print(f"test_doublade_deck.py: all checks passed — the list is legal, every new card "
          f"fires in {len(list(SEEDS))} seeded games, and across {len(all_swings)} real "
          f"Weaponized Swords swings not a single Honedge/Doublade/Aegislash ever left "
          f"the hand")


if __name__ == "__main__":
    main()
