#!/usr/bin/env python3
"""
test_cynthia_garchomp_deck.py — the DECK_CYNTHIA_GARCHOMP live-fire check.

The per-card unit tests prove each new effect does what its card text says; this proves
the effects are actually EXERCISED by real, deterministic games (implemented != fired).
It plays seeded greedy games of `cynthia_garchomp` vs `dragapult` and asserts:

  1. the recipe is registered, is exactly 60 cards and has zero legality violations;
  2. every new card shows up in the logs of real games, and the whole line
     (Cynthia's Gible -> Gabite -> Garchomp ex, Roselia -> Roserade) gets assembled;
  3. the SILENT pieces really bite in-game — Cheer On to Glory's +30 shows up as boosted
     damage numbers, Cynthia's Power Weight's +70 shows up as a live max_hp, and Neo Upper
     Energy's "every type / 2 Energy at a time" shows up as a live Stage 2 holder whose
     lone Neo Upper provides two wildcard units (an attach line alone would pass even if
     the card were inert, so it is asserted from board state);
  4. Rocky Fighting Energy's prevention fires through the REAL attack path (scripted,
     because greedy almost never lands an opposing counter-placing attack effect on a
     Rocky-holding Fighting Pokémon — see the note at §4).

Run: python3 tests/test_cynthia_garchomp_deck.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import DECKS, load_deck
from src.engine.legality import validate_deck
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine.agents import GreedyAgent
from src.engine.game import (Action, setup_game, start_turn, end_turn, apply_action,
                             can_pay_cost, check_win, MAX_TURNS)

# 18 seeds: enough that the 1-of Cynthia's Spiritomb reaches the Active Spot and uses
# Raging Curse (first at seed 12), which is the rarest line in the list.
SEEDS = range(18)


def play(db, seed):
    """One deterministic greedy game; returns (log, power_weight max_hp observations,
    Neo Upper Energy provision observations)."""
    st = setup_game(load_deck(db, "cynthia_garchomp"), load_deck(db, "dragapult"),
                    seed=seed, db=db)
    # SEEDED greedy: GreedyAgent()'s default rng is unseeded, and it uses rng.choice to
    # pick which Basic to bench — so an unseeded agent makes this whole liveness check
    # non-reproducible run to run. Seeding it off the game seed keeps the assertions below
    # deterministic (which cards fire is then a property of the deck, not of luck).
    agent = GreedyAgent(random.Random(1000 + seed))
    hp_samples = set()
    nue_samples = set()
    while st.phase is not Phase.GAME_OVER and st.turn_number < MAX_TURNS:
        if not start_turn(st):
            break
        while st.phase is Phase.MAIN:
            action = agent.choose(st)
            apply_action(st, action)
            for p in st.players:
                for mon in p.all_in_play():
                    if mon.tool is not None and mon.tool.name == "Cynthia's Power Weight":
                        hp_samples.add((mon.card.name, mon.card.hp, mon.max_hp))
                    if any(e.name == "Neo Upper Energy" for e in mon.energy):
                        # what this holder's attachments actually PROVIDE, and whether
                        # the Neo Upper alone covers a two-symbol typed cost
                        solo = InPlayPokemon(card=mon.card)
                        solo.energy = [e for e in mon.energy
                                       if e.name == "Neo Upper Energy"][:1]
                        nue_samples.add((mon.card.name,
                                         "Stage 2" in mon.card.subtypes,
                                         tuple(solo.provided_types()),
                                         can_pay_cost(solo, ("Fighting", "Fighting"))))
            if action.kind == "pass" or check_win(st):
                break
        if st.phase is Phase.GAME_OVER:
            break
        end_turn(st)
    return st.log, hp_samples, nue_samples


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 1. the recipe: registered, exactly 60 cards, zero legality violations. ---
    check("cynthia_garchomp" in DECKS, "the deck must be registered as 'cynthia_garchomp'")
    recipe = DECKS["cynthia_garchomp"]
    check(sum(n for _, n in recipe) == 60,
          f"the list must be 60 cards, got {sum(n for _, n in recipe)}")
    violations = validate_deck(db, recipe)
    check(violations == [], f"the list must be Standard-legal, got {violations}")
    check(len(load_deck(db, "cynthia_garchomp")) == 60, "load_deck must expand to 60 Cards")

    # --- 2. live fire: every new card must appear in the logs of real games. ---
    logs, hp_samples, nue_samples = [], set(), set()
    for seed in SEEDS:
        log, hp, nue = play(db, seed)
        logs.extend(log)
        hp_samples |= hp
        nue_samples |= nue
        check(len(log) > 20, f"seed {seed} produced a suspiciously short game "
                             f"({len(log)} lines)")
    logs = "\n".join(logs)

    must_fire = {
        "Champion's Call (Cynthia's Gabite ability)": "Champion's Call:",
        # Rock Hurl owns its damage (engine base 0), so _resolve_attack prints no
        # "used Rock Hurl for N" line — the effect emits its own dealt-damage line, which
        # is what makes the Resistance-skip observable in a log at all.
        "Rock Hurl (Cynthia's Gible)": "Rock Hurl: ",
        "Corkscrew Dive (Cynthia's Garchomp ex)": "Corkscrew Dive:",
        "Draconic Buster (Cynthia's Garchomp ex)": "Draconic Buster:",
        "Raging Curse (Cynthia's Spiritomb)": "Raging Curse:",
        "Surfer": "Surfer:",
        "Fighting Gong": "Fighting Gong:",
        "Premium Power Pro": "Premium Power Pro:",
        "Cynthia's Power Weight (Tool attach)": "attached Tool Cynthia's Power Weight",
        "Team Rocket's Watchtower (Stadium)": "played Stadium Team Rocket's Watchtower",
        "Rocky Fighting Energy (attach)": "attached Rocky Fighting Energy",
        # Neo Upper Energy: the attach line only proves the CARD was played, not that its
        # rule does anything — an inert Special Energy would pass it. Its provision clause
        # is asserted from live board state at §3c instead.
        "Neo Upper Energy (attach)": "attached Neo Upper Energy",
        "Cynthia's Gabite actually evolving": "evolved into Cynthia's Gabite",
        "Cynthia's Garchomp ex actually evolving": "evolved into Cynthia's Garchomp ex",
        "Cynthia's Roserade actually evolving": "evolved into Cynthia's Roserade",
        # the rest of the list's Trainers (already-implemented staples, but they must
        # still be doing something in THIS deck — an inert 32-card Trainer half would
        # make every win rate meaningless)
        "Lillie's Determination": "Lillie's Determination:",
        "Boss's Orders": "Boss's Orders:",
        "Hilda": "Hilda:",
        "Kieran": "Kieran:",
        "Judge": "Judge:",
        "Buddy-Buddy Poffin": "Buddy-Buddy Poffin",
        "Poké Pad": "Poké Pad:",
        "Night Stretcher": "Night Stretcher:",
    }
    for label, needle in must_fire.items():
        check(needle in logs, f"never fired in {len(list(SEEDS))} seeded games: {label} "
                              f"(looked for {needle!r})")

    # --- 3a. Cheer On to Glory is SILENT (a pre-W/R add inside apply_attack_damage), so
    # prove it bit by finding boosted damage numbers in the logs: Corkscrew Dive's printed
    # 100 landing as 130/160 (one/two Roserade), Dragonslice's 40 as 70, Spike Sting's 20
    # as 50. A number like that cannot appear unless the passive really applied. ---
    boosted = [n for n in ("used Corkscrew Dive for 130", "used Corkscrew Dive for 160",
                           "used Dragonslice for 70", "used Spike Sting for 50")
               if n in logs]
    check(boosted, "Cheer On to Glory's +30 never showed up as a boosted damage number "
                   "(looked for Corkscrew Dive 130/160, Dragonslice 70, Spike Sting 50)")

    # --- 3a'. Rock Hurl's "damage isn't affected by Resistance", proven from live logs.
    # The dragapult list runs four Fighting-RESISTANT (−30) Pokémon (Duskull, Dusclops,
    # Dusknoir, Munkidori). Rock Hurl's printed damage is 20, so if the Resistance half of
    # the chokepoint were ever applied the log would show a 0. Nothing else in this matchup
    # can zero it out (no wall Abilities, no Dig shield), so "never 0" is a real assertion
    # about the clause, not about the sample. ---
    check("Rock Hurl: 0 damage" not in logs,
          "Rock Hurl landed 0 damage in a live game — the Fighting Resistance it is "
          "supposed to ignore was applied")
    check("Rock Hurl: 20 damage" in logs,
          "Rock Hurl never landed its printed 20 in a live game")

    # --- 3b. Cynthia's Power Weight is equally silent (derived max HP), so assert we
    # actually observed a live holder at printed HP + 70 during real games. ---
    check(hp_samples, "no Cynthia's Power Weight holder was ever observed in play")
    bad = [s for s in hp_samples if s[2] != s[1] + 70]
    check(not bad, f"every Cynthia's holder of Power Weight must sit at printed HP + 70 "
                   f"in live play; offenders: {sorted(bad)}")

    # --- 3c. Neo Upper Energy's provision clause is silent too (it never emits — it is
    # consumed by can_pay_cost), and "attached Neo Upper Energy" above would pass even if
    # the card provided nothing. So assert from LIVE board state that a real Stage 2 holder
    # arose and that the lone Neo Upper on it really provided 2 wildcard units (enough for
    # Draconic Buster's [F][F] by itself), and that a non-Stage-2 holder never did. ---
    check(nue_samples, "no Neo Upper Energy holder was ever observed in play")
    stage2 = [s for s in nue_samples if s[1]]
    check(stage2, "Neo Upper Energy was never observed on a Stage 2 holder in real games — "
                  "its 'every type / 2 Energy at a time' clause is untested live")
    bad = [s for s in stage2 if s[2] != ("Any", "Any") or not s[3]]
    check(not bad, f"a Stage 2 Neo Upper holder must provide 2 wildcard units and pay "
                   f"[F][F] from the Neo Upper alone; offenders: {sorted(map(str, bad))}")
    bad = [s for s in nue_samples if not s[1] and (s[2] != ("Colorless",) or s[3])]
    check(not bad, f"a non-Stage-2 Neo Upper holder must provide exactly one Colorless and "
                   f"must NOT pay [F][F]; offenders: {sorted(map(str, bad))}")

    # --- 4. Rocky Fighting Energy's prevention, through the REAL attack path. Greedy
    # loads its Active, and the opponent's only counter-placing attack effect (Phantom
    # Dive) targets the BENCH, so this combination essentially never occurs in a greedy
    # game — it is scripted here rather than grepped for, so the engine path (apply_action
    # -> _resolve_attack -> effect -> place_counters) is genuinely exercised. ---
    def phantom_dive_into_bench(rocky: bool):
        """Script one real Phantom Dive from a Dragapult ex into a lone benched Cynthia's
        Gible, with or without a Rocky Fighting Energy attached. Returns (bencher, log)."""
        a = PlayerState(name="A")
        b = PlayerState(name="B")
        st = GameState(players=(a, b), rng=random.Random(0))
        st.db = db
        st.turn_number = 6
        st.active_index = 1                                # B (Dragapult ex) attacks
        a.active = InPlayPokemon(card=db.get("Cynthia's Roselia"))
        bencher = InPlayPokemon(card=db.get("Cynthia's Gible"))        # Fighting
        if rocky:
            bencher.energy = [db.get("Rocky Fighting Energy")]
        a.bench = [bencher]
        a.prizes = [db.get("Basic Fighting Energy")] * 6
        b.prizes = [db.get("Basic Fighting Energy")] * 6
        pult = InPlayPokemon(card=db.get("Dragapult ex"))
        pult.energy = [db.get("Basic Fire Energy"), db.get("Basic Psychic Energy")]
        b.active = pult
        apply_action(st, Action("attack", attack_index=1))  # Phantom Dive: 6 bench counters
        return bencher, "\n".join(st.log)

    protected, plog = phantom_dive_into_bench(rocky=True)
    check(protected.damage == 0,
          f"Phantom Dive's counters must be fully prevented on the Rocky-protected "
          f"Fighting Pokémon, got {protected.damage} damage")
    check("Rocky Fighting Energy: prevented" in plog,
          "the prevention must be logged when it fires through the real attack path")
    # CONTROL: the identical scripted attack with no Rocky attached really does land the
    # counters (and KOs the 70-HP Gible), so the assertion above tests the Energy and not
    # some unrelated reason the counters went nowhere.
    exposed, _ = phantom_dive_into_bench(rocky=False)
    check(exposed.damage == 60,
          f"control: without Rocky Fighting Energy all 6 counters must land, got "
          f"{exposed.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_cynthia_garchomp_deck.py: all checks passed — the list is legal, every new "
          "card fires in real seeded games, the silent pieces bite (+30 damage, +70 HP, "
          "Neo Upper's 2 wildcard units on a live Stage 2), Rock Hurl keeps its 20 through "
          "Fighting Resistance, and Rocky Fighting Energy's prevention fires through the "
          "real attack path")


if __name__ == "__main__":
    main()
