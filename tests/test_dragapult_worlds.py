#!/usr/bin/env python3
"""
test_dragapult_worlds.py — the Worlds-2026 champion Dragapult list
(Andrew Hedrick, San Francisco, 1st place 14-2-0) and its two new engine pieces:

- Risky Ruins (MEG, Stadium): "Whenever any player puts a Basic non-Darkness
  Pokémon onto their Bench during their turn, place 2 damage counters on that
  Pokémon." Lives at the bench-arrival chokepoint `effects.on_benched_new`.
- Rosa's Encouragement (POR 84, Supporter): "You can use this card only if you
  have more Prize cards remaining than your opponent. Attach up to 2 Basic
  Energy cards from your discard pile to 1 of your Stage 2 Pokémon."

Each check asserts against the REAL card text (limitlesstcg / pool JSON).
Run: python3 tests/test_dragapult_worlds.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game, effects as fx
from src.engine.decks import load_deck

db = CardDB.from_pool()
fails = 0
def check(c, m):
    global fails
    print(("  ok  " if c else "  FAIL") + " " + m)
    if not c: fails += 1

def mk(name): return db.get(name)

def blank_state(a_active, b_active):
    a = PlayerState(name="A", deck=[mk("Basic Fire Energy")] * 20,
                    active=InPlayPokemon(card=mk(a_active)))
    b = PlayerState(name="B", deck=[mk("Basic Fire Energy")] * 20,
                    active=InPlayPokemon(card=mk(b_active)))
    st = GameState(players=[a, b], db=db, rng=random.Random(7))
    st.phase = Phase.MAIN
    a.prizes = [mk("Basic Fire Energy")] * 6
    b.prizes = [mk("Basic Fire Energy")] * 6
    return st, a, b

def ctx_for(st, a, b, src):
    return fx.EffectContext(state=st, me=a, opp=b, source=src, db=db,
                            rng=st.rng, effect_kind="trainer")


print("== deck registration ==")
deck = load_deck(db, "dragapult_worlds")
check(len(deck) == 60, "dragapult_worlds is exactly 60 cards")
check(sum(1 for c in deck if c.name == "Dragapult ex") == 3, "3 Dragapult ex")
check(sum(1 for c in deck if c.name == "Crushing Hammer") == 4, "4 Crushing Hammer")
check(sum(1 for c in deck if c.name == "Risky Ruins") == 2, "2 Risky Ruins")
check(sum(1 for c in deck if c.name == "Rosa's Encouragement") == 1, "1 Rosa's Encouragement")

print("\n== Risky Ruins: bench-arrival counters ==")
st, a, b = blank_state("Dragapult ex", "Mega Excadrill ex")
st.stadium = mk("Risky Ruins")
st.stadium_owner = 0
# a Basic non-Darkness Pokémon benched -> 2 damage counters
newmon = InPlayPokemon(card=mk("Dreepy"), played_this_turn=True)
a.bench.append(newmon)
fx.on_benched_new(st, a, newmon)
check(newmon.damage == 20, "Basic non-Darkness benched under Risky Ruins takes 20")
# a Darkness Basic is exempt (the card's own faction clause). NOTE the pool's
# Munkidori print is Psychic-type, so it is NOT exempt — use Gastly (Darkness).
dark = InPlayPokemon(card=mk("Gastly"), played_this_turn=True)
a.bench.append(dark)
fx.on_benched_new(st, a, dark)
check(dark.damage == 0, "Darkness Basic (Gastly) is exempt")
# applies to BOTH players ("any player")
theirs = InPlayPokemon(card=mk("Drilbur"), played_this_turn=True)
b.bench.append(theirs)
fx.on_benched_new(st, b, theirs)
check(theirs.damage == 20, "opponent's Basic benched under Risky Ruins takes 20 too")
# no Stadium -> no counters
st.stadium = None
clean = InPlayPokemon(card=mk("Dreepy"), played_this_turn=True)
a.bench.append(clean)
fx.on_benched_new(st, a, clean)
check(clean.damage == 0, "no counters without the Stadium in play")
# the trigger is wired into the real play_basic action
st.stadium = mk("Risky Ruins")
a.hand.append(mk("Dreepy"))
before = len(a.bench)
game.apply_action(st, game.Action(kind="play_basic", hand_index=len(a.hand) - 1))
check(len(a.bench) == before + 1 and a.bench[-1].damage == 20,
      "play_basic action routes through the chokepoint")

print("\n== Rosa's Encouragement ==")
st, a, b = blank_state("Dragapult ex", "Mega Excadrill ex")
can = fx._TRAINER_CAN_PLAY["Rosa's Encouragement"]
st.active_index = 0
a.discard.extend([mk("Basic Fire Energy"), mk("Basic Psychic Energy"),
                  mk("Basic Darkness Energy")])
# equal prizes -> NOT playable (must have MORE remaining, i.e. be behind)
check(not can(st, a), "not playable at equal prizes (must be behind)")
b.prizes = b.prizes[:4]     # opponent has taken prizes -> we have more remaining
check(can(st, a), "playable when behind on prizes")
ctx = ctx_for(st, a, b, a.active)
ok = fx.TRAINER_EFFECTS["Rosa's Encouragement"](ctx)
check(ok and len(a.active.energy) == 2, "attaches up to 2 Basic Energy from discard")
check(len(a.discard) == 1, "exactly 2 left the discard pile")
# Dragapult ex costs Fire+Psychic: the type-preference policy should have taken
# those two and left the Darkness Energy behind
check(all(c.name != "Basic Darkness Energy" for c in a.active.energy)
      and any(c.name == "Basic Darkness Energy" for c in a.discard),
      "prefers Energy types named in the target's attack costs")
# no Stage 2 in play -> not playable
st2, a2, b2 = blank_state("Dreepy", "Drilbur")
st2.active_index = 0
a2.discard.append(mk("Basic Fire Energy"))
b2.prizes = b2.prizes[:4]
check(not fx._TRAINER_CAN_PLAY["Rosa's Encouragement"](st2, a2),
      "not playable with no Stage 2 in play")

print()
if fails:
    print(f"{fails} FAILURES")
    sys.exit(1)
print("ALL PASS")
