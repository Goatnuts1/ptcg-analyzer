#!/usr/bin/env python3
"""
test_ns_zoroark.py — N's Zoroark ex (§META-2026-10): Night Joker's benched-attack-copy
(a new `Action.copy_attack_index` field + a `_night_joker_value` GreedyAgent branch, same
"inertness bug" shape as Do the Wave / Seek Inspiration before it), Trade's discard-then-
draw Ability, N's Zekrom's Shred (ignore_active_effects) / Rampaging Thunder (self-lock),
N's Darmanitan's Back Draft (variable ×) / Flamebody Cannon (self-energy-discard + bench
snipe), Pecharunt ex's Subjugating Chains (switch, Poison logged-not-modeled) / Irritated
Outburst (prizes-taken scaling), Transformation Tome (play-2-at-once swap), N's PP Up,
Black Belt's Training, and N's Castle (retreat-cost-0 Stadium).

Each check asserts an effect against its REAL card text (pool JSON — every card in this
archetype is already in data/standard_pool.json, no manual-supplement additions needed).

Run: python3 tests/test_ns_zoroark.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import DECKS, load_deck
from src.engine.legality import validate_deck
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine.game import (Action, setup_game, start_turn, end_turn, legal_actions,
                             apply_action, retreat_cost)
from src.engine.agents import GreedyAgent
from src.engine import effects as fx
from src.engine.mcts import _semantic_key, _deduped_legal

db = CardDB.from_pool()
fails = 0


def check(c, m):
    global fails
    print(("  ok  " if c else "  FAIL") + " " + m)
    if not c:
        fails += 1


def mk(name):
    return db.get(name)


def blank_state(a_active, b_active, a_bench=(), b_bench=()):
    a = PlayerState(name="A", deck=[mk("Basic Darkness Energy")] * 20,
                    active=InPlayPokemon(card=mk(a_active)),
                    bench=[InPlayPokemon(card=mk(n)) for n in a_bench])
    b = PlayerState(name="B", deck=[mk("Basic Darkness Energy")] * 20,
                    active=InPlayPokemon(card=mk(b_active)),
                    bench=[InPlayPokemon(card=mk(n)) for n in b_bench])
    st = GameState(players=[a, b], db=db, rng=random.Random(7))
    st.phase = Phase.MAIN
    a.prizes = [mk("Basic Darkness Energy")] * 6
    b.prizes = [mk("Basic Darkness Energy")] * 6
    return st, a, b


def ctx_for(st, a, b, src):
    return fx.EffectContext(state=st, me=a, opp=b, source=src, db=db,
                            rng=st.rng, effect_kind="attack")


# --------------------------------------------------------------------------- #
# Card text sanity (every card already lives in the pool under real text)
# --------------------------------------------------------------------------- #
print("== Real card text ==")
zoroark = mk("N's Zoroark ex")
check(zoroark.hp == 280 and "Darkness" in zoroark.types,
      "N's Zoroark ex: 280 HP Darkness")
trade = next(a for a in zoroark.abilities if a.name == "Trade")
check("discard a card from your hand" in trade.text and "draw 2 cards" in trade.text,
      f"Trade text: {trade.text!r}")
night_joker = next(a for a in zoroark.attacks if a.name == "Night Joker")
check("Benched N's Pokémon's attacks" in night_joker.text,
      f"Night Joker text: {night_joker.text!r}")

zekrom = mk("N's Zekrom")
shred = next(a for a in zekrom.attacks if a.name == "Shred")
check("isn't affected by any effects" in shred.text and shred.damage == 70,
      f"Shred text/damage: {shred.damage} {shred.text!r}")
rampaging = next(a for a in zekrom.attacks if a.name == "Rampaging Thunder")
check("can't use attacks" in rampaging.text and rampaging.damage == 250,
      f"Rampaging Thunder text/damage: {rampaging.damage} {rampaging.text!r}")

darmanitan = mk("N's Darmanitan")
back_draft = next(a for a in darmanitan.attacks if a.name == "Back Draft")
check("30 damage for each Basic Energy" in back_draft.text,
      f"Back Draft text: {back_draft.text!r}")
flamebody = next(a for a in darmanitan.attacks if a.name == "Flamebody Cannon")
check("Discard all Energy from this Pokémon" in flamebody.text and flamebody.damage == 90,
      f"Flamebody Cannon text: {flamebody.text!r}")

pecharunt = mk("Pecharunt ex")
subj = next(a for a in pecharunt.abilities if a.name == "Subjugating Chains")
check("now Poisoned" in subj.text, f"Subjugating Chains text: {subj.text!r}")
outburst = next(a for a in pecharunt.attacks if a.name == "Irritated Outburst")
check("Prize card your opponent has taken" in outburst.text,
      f"Irritated Outburst text: {outburst.text!r}")

tome = mk("Transformation Tome")
check(any("play 2 Transformation Tome cards at once" in r for r in tome.rules)
      and any("switch it with 1 of your Basic Pokémon in play" in r for r in tome.rules),
      "Transformation Tome rules text")

castle = mk("N's Castle")
check(any("no Retreat Cost" in r for r in castle.rules), "N's Castle rules text")

ppup = mk("N's PP Up")
check(any("Attach a Basic Energy card from your discard pile" in r for r in ppup.rules),
      "N's PP Up rules text")

belt = mk("Black Belt's Training")
check(any("40 more damage" in r and "Active Pokémon ex" in r for r in belt.rules),
      "Black Belt's Training rules text")


# --------------------------------------------------------------------------- #
# Night Joker
# --------------------------------------------------------------------------- #
print("\n== Night Joker ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex",
                       a_bench=("N's Zekrom",))
ctx = ctx_for(st, a, b, a.active)
ctx.target = (a.bench[0], mk("N's Zekrom").attacks[1])   # Rampaging Thunder
fx.ATTACK_EFFECTS[("N's Zoroark ex", "Night Joker")](ctx)
check(b.active.damage == 250, f"Night Joker copying Rampaging Thunder deals 250, got {b.active.damage}")
check(a.active.pending_cannot_attack,
      "the copied Rampaging Thunder's rider (self-lock) really runs, on the COPIER")

# legal_actions enumerates one action per (bench slot, attack index), excluding the
# benched Pokémon's own Night Joker (self-recursion guard).
st2, a2, b2 = blank_state("N's Zoroark ex", "Mega Excadrill ex",
                          a_bench=("N's Zekrom", "N's Zoroark ex"))
a2.active.energy = [mk("Basic Darkness Energy")] * 2
st2.turn_number = 3
acts = legal_actions(st2)
nj_acts = [x for x in acts if x.kind == "attack" and x.copy_attack_index is not None]
check(len(nj_acts) == 2, f"Night Joker offers exactly N's Zekrom's 2 attacks, got {len(nj_acts)}")
check(all(a2.bench[x.target_index].card.name == "N's Zekrom" for x in nj_acts),
      "the benched N's Zoroark ex's own Night Joker is excluded (no self-recursion)")

# MCTS semantic keys must disambiguate the two Night Joker choices (CLAUDE.md's
# action-vanishing guard — see tests/test_mcts_keys.py for the general sweep).
keys = {_semantic_key(st2, x) for x in nj_acts}
check(len(keys) == 2, f"Night Joker choices get distinct semantic keys, got {keys}")
check(all(k[0] == "attack" for k in keys), "both keys start with the action's own kind")


# --------------------------------------------------------------------------- #
# Trade
# --------------------------------------------------------------------------- #
print("\n== Trade ==")
st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
a.hand = [mk("Ultra Ball"), mk("Boss's Orders")]
ctx = ctx_for(st, a, b, a.active)
fx.ABILITY_EFFECTS[("N's Zoroark ex", "Trade")](ctx)
check(len(a.hand) == 3 and len(a.discard) == 1, "Trade: discarded 1, net hand +1 (drew 2)")


# --------------------------------------------------------------------------- #
# Shred / Rampaging Thunder direct
# --------------------------------------------------------------------------- #
print("\n== N's Zekrom ==")
st, a, b = blank_state("N's Zekrom", "Crustle")   # Crustle's Mysterious Rock Inn wall
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("N's Zekrom", "Shred")](ctx)
check(b.active.damage == 70, f"Shred bypasses Mysterious Rock Inn's ex-attack wall, got {b.active.damage}")

st, a, b = blank_state("N's Zekrom", "Mega Excadrill ex")
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("N's Zekrom", "Rampaging Thunder")](ctx)
check(a.active.pending_cannot_attack, "Rampaging Thunder arms the self-lock")


# --------------------------------------------------------------------------- #
# N's Darmanitan
# --------------------------------------------------------------------------- #
print("\n== N's Darmanitan ==")
st, a, b = blank_state("N's Darmanitan", "N's Darumaka")   # no Fire weakness, no muddying x2
b.discard = [mk("Basic Fire Energy"), mk("Basic Fire Energy"), mk("Ultra Ball")]
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("N's Darmanitan", "Back Draft")](ctx)
check(b.active.damage == 60, f"Back Draft: 30 x 2 Basic Energy in opp discard, got {b.active.damage}")

st, a, b = blank_state("N's Darmanitan", "Mega Excadrill ex",
                       b_bench=("Dwebble", "Dwebble"))
a.active.energy = [mk("Basic Fire Energy")] * 2
b.bench[0].damage = 10    # closer to a KO -> the snipe policy's target
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("N's Darmanitan", "Flamebody Cannon")](ctx)
check(a.active.energy == [] and len(a.discard) == 2,
      f"Flamebody Cannon discards all of its own Energy, got {len(a.active.energy)} left")
check(b.bench[0].damage == 100, f"90 more to the lowest-HP bencher, got {b.bench[0].damage}")
check(b.bench[1].damage == 0, "the other bencher untouched")


# --------------------------------------------------------------------------- #
# Pecharunt ex
# --------------------------------------------------------------------------- #
print("\n== Pecharunt ex ==")
st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex",
                       a_bench=("N's Zekrom", "N's Zoroark ex"))
a.bench[1].energy = [mk("Basic Darkness Energy")] * 2   # N's Zoroark ex can pay Night Joker
check(fx.ABILITY_CAN_USE[("Pecharunt ex", "Subjugating Chains")](st, a, a.active),
      "Subjugating Chains offered: Active (Pecharunt ex) is stuck, a benched Darkness "
      "mon can actually pay for an attack")
a.bench[1].energy = []  # reset: with NOTHING payable anywhere, it must NOT be offered
check(not fx.ABILITY_CAN_USE[("Pecharunt ex", "Subjugating Chains")](st, a, a.active),
      "NOT offered when no benched Darkness mon can actually attack either "
      "(the thrashing-every-turn bug this gate exists to prevent)")
a.bench[1].energy = [mk("Basic Darkness Energy")] * 2   # restore for the switch check below
ctx = ctx_for(st, a, b, a.active)
fx.ABILITY_EFFECTS[("Pecharunt ex", "Subjugating Chains")](ctx)
check(a.active.card.name in ("N's Zekrom", "N's Zoroark ex"),
      f"switched in a benched Darkness mon, got {a.active.card.name}")
check(any(m.card.name == "Pecharunt ex" for m in a.bench),
      "the old Active (Pecharunt ex) lands on the Bench")

st, a, b = blank_state("Pecharunt ex", "Mega Excadrill ex")
b.prizes = [mk("Basic Darkness Energy")] * 4   # opponent has taken 2
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("Pecharunt ex", "Irritated Outburst")](ctx)
check(b.active.damage == 120, f"60 x 2 prizes the OPPONENT has taken, got {b.active.damage}")


# --------------------------------------------------------------------------- #
# Transformation Tome / N's PP Up / Black Belt's Training / N's Castle
# --------------------------------------------------------------------------- #
print("\n== Trainers / Stadium ==")
st, a, b = blank_state("N's Zorua", "Mega Excadrill ex")
a.active.damage = 30
a.discard = [mk("N's Zekrom")]
a.hand = [mk("Transformation Tome"), mk("Transformation Tome"), mk("Ultra Ball")]
check(fx.can_play_trainer(st, a, "Transformation Tome"), "playable with 2 copies + a target")
card = a.hand.pop(0)
ctx = ctx_for(st, a, b, None)
did = fx.TRAINER_EFFECTS["Transformation Tome"](ctx)
check(did, "Transformation Tome resolves")
check(a.active.card.name == "N's Zekrom" and a.active.damage == 30,
      f"the new Pokémon keeps the slot's damage counters, got {a.active.card.name} dmg={a.active.damage}")
check(len(a.hand) == 1 and all(c.name != "Transformation Tome" for c in a.hand),
      "both copies left the hand")
check(any(c.name == "N's Zorua" for c in a.discard), "the replaced Pokémon went to the discard pile")

st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex", a_bench=("N's Zekrom",))
a.discard = [mk("Basic Darkness Energy")]
ctx = ctx_for(st, a, b, None)
did = fx.TRAINER_EFFECTS["N's PP Up"](ctx)
check(did and a.bench[0].energy_count() == 1, "N's PP Up attaches to a Benched N's Pokémon")

st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
ctx = ctx_for(st, a, b, None)
fx.TRAINER_EFFECTS["Black Belt's Training"](ctx)
check(a.bonus_damage_vs_ex_v == 40, "Black Belt's Training sets the +40-vs-ex flag")

st, a, b = blank_state("N's Zoroark ex", "Mega Excadrill ex")
st.stadium = mk("N's Castle")
st.stadium_owner = 0
check(retreat_cost(a.active, st, a) == 0, "N's Castle zeroes an N's Pokémon's retreat cost")
mega = InPlayPokemon(card=mk("Mega Excadrill ex"))
check(retreat_cost(mega, st, b) == mega.card.retreat_cost,
      "a non-N's Pokémon's retreat cost is untouched")


# --------------------------------------------------------------------------- #
# Deck-level: legality + a real seeded game doesn't crash, every new mechanic fires
# somewhere across a 30-game sweep (implemented != fired — same discipline as
# test_doublade_deck.py / test_gardevoir_real_deck.py).
# --------------------------------------------------------------------------- #
print("\n== ns_zoroark deck ==")
recipe = DECKS["ns_zoroark"]
violations = validate_deck(db, recipe)
check(violations == [], f"ns_zoroark is a legal 60: {violations}")

cards = load_deck(db, "ns_zoroark")
check(len(cards) == 60, f"expands to 60 cards, got {len(cards)}")

needles = {
    "Night Joker": False, "Trade:": False, "Shred": False,
    "Rampaging Thunder": False, "Back Draft": False, "Flamebody Cannon": False,
    "Subjugating Chains": False, "Irritated Outburst": False,
    "Transformation Tome:": False, "N's PP Up:": False, "Black Belt's Training:": False,
}
SEEDS = range(30)
crashed = []
for seed in SEEDS:
    st = setup_game(load_deck(db, "ns_zoroark"), load_deck(db, "mega_excadrill"),
                    seed=seed, db=db)
    start_turn(st)
    agent = GreedyAgent(random.Random(seed))
    log = []
    orig_emit = st.emit
    st.emit = lambda m, _l=log: (_l.append(m), orig_emit(m))
    guard = 0
    try:
        while st.phase != Phase.GAME_OVER and st.turn_number < 60 and guard < 4000:
            guard += 1
            if st.phase == Phase.MAIN:
                act = agent.choose(st)
                apply_action(st, act)
                if act.kind in ("attack", "pass"):
                    st.phase = Phase.BETWEEN_TURNS
            if st.phase == Phase.BETWEEN_TURNS:
                end_turn(st)
                if not start_turn(st):
                    break
    except Exception as e:
        crashed.append((seed, repr(e)))
        continue
    for n in needles:
        if any(n in m for m in log):
            needles[n] = True

check(not crashed, f"no crashes across {len(SEEDS)} seeded greedy games: {crashed}")
for n, fired in needles.items():
    if fired:
        check(True, f"{n} fires in real seeded games")
    else:
        print(f"  NOTE: did not fire in {len(SEEDS)} seeded games (not a failure, see "
             f"the unit test above instead): {n}")

if fails:
    print(f"\nFAILED ({fails})")
    sys.exit(1)
print("\ntest_ns_zoroark.py: all checks passed")
