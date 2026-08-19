#!/usr/bin/env python3
"""
test_meta_2026_08_lines.py — the three live-metagame archetype additions:
Dragapult Blaziken (Blaziken ex), Festival Lead (Dipplin engine + the
attack-twice mechanic + Gladion's Final Battle), Grimmsnarl Froslass (Punk Up /
Shadow Bullet / Freezing Shroud / Spikemuth Gym / Rabsca walls).

Each check asserts an effect against its REAL card text (pool JSON /
limitlesstcg for the manual-supplement prints). Run: python3 tests/test_meta_2026_08_lines.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import game, effects as fx

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
                            rng=st.rng, effect_kind="attack")


print("== Blaziken ex ==")
st, a, b = blank_state("Blaziken ex", "Dragapult ex")
a.discard.extend([mk("Basic Fire Energy"), mk("Ultra Ball")])
ctx = ctx_for(st, a, b, a.active)
fx.ABILITY_EFFECTS[("Blaziken ex", "Seething Spirit")](ctx)
check(len(a.active.energy) == 1 and a.active.energy[0].name == "Basic Fire Energy"
      and all(c.name != "Basic Fire Energy" for c in a.discard),
      "Seething Spirit attaches a BASIC Energy from the discard (not the Item)")

fx.ATTACK_EFFECTS[("Blaziken ex", "Smolder-sault")](ctx)
check(a.active.pending_cannot_attack, "Smolder-sault sets the next-turn attack lock")
check(any(atk.name == "Smolder-sault" and atk.damage == 200
          for atk in mk("Blaziken ex").attacks), "printed 200 confirmed")

print("\n== Gladion's Final Battle ==")
st, a, b = blank_state("Dipplin", "Dragapult ex")
glad = mk("Gladion's Final Battle")
a.hand = [glad]
check(fx.can_play_trainer(st, a, "Gladion's Final Battle"),
      "playable when it is the LAST card in hand")
a.hand = [glad, mk("Ultra Ball")]
check(not fx.can_play_trainer(st, a, "Gladion's Final Battle"),
      "NOT playable with any other card in hand")
a.hand = []
ctx = ctx_for(st, a, b, a.active)
fx.TRAINER_EFFECTS["Gladion's Final Battle"](ctx)
check(a.bonus_damage_nonrulebox == 80, "sets the +80 turn flag")
# non-Rule-Box attacker vs Active: +80 applies; a Rule-Box attacker gets nothing
dealt = fx.apply_attack_damage(ctx, b.active, 20, owner=b, source=a.active)
check(dealt == 100, f"Dipplin (no Rule Box) 20 -> 100 vs the Active (got {dealt})")
st2, a2, b2 = blank_state("Blaziken ex", "Dragapult ex")
a2.bonus_damage_nonrulebox = 80
ctx2 = ctx_for(st2, a2, b2, a2.active)
dealt = fx.apply_attack_damage(ctx2, b2.active, 20, owner=b2, source=a2.active)
check(dealt == 20, f"Blaziken ex (Rule Box) gets NO bonus (got {dealt})")

print("\n== Festival Lead: attack twice ==")
st, a, b = blank_state("Dipplin", "Dragapult ex")
a.active.energy = [mk("Basic Grass Energy")]
a.bench = [InPlayPokemon(card=mk("Grookey")) for _ in range(3)]
st.stadium, st.stadium_owner = mk("Festival Grounds"), 0
b.active.damage = 0
game._resolve_attack(st, 0)     # Do the Wave: 20×3 bench = 60, twice = 120
check(b.active.damage == 120,
      f"Do the Wave fires TWICE under Festival Grounds: 60+60 (got {b.active.damage})")
st.stadium = None
b.active.damage = 0
game._resolve_attack(st, 0)
check(b.active.damage == 60,
      f"without Festival Grounds it fires once (got {b.active.damage})")

# the second use hits the REPLACEMENT active if the first KO'd
st, a, b = blank_state("Dipplin", "Budew")
a.active.energy = [mk("Basic Grass Energy")]
a.bench = [InPlayPokemon(card=mk("Grookey")) for _ in range(4)]   # 80 per use
b.active.damage = 0
b.bench = [InPlayPokemon(card=mk("Munkidori"))]      # 110 HP: survives the repeat
st.stadium, st.stadium_owner = mk("Festival Grounds"), 0
game._resolve_attack(st, 0)     # 80 KOs 70HP Budew; repeat hits promoted Dreepy
check(b.active.card.name == "Munkidori" and b.active.damage == 80,
      f"first use KOs, second use hits the NEW Active (Munkidori at {b.active.damage})")

print("\n== Festival Grounds: Condition immunity ==")
st, a, b = blank_state("Munkidori", "Dipplin")
b.active.energy = [mk("Basic Grass Energy")]
st.stadium, st.stadium_owner = mk("Festival Grounds"), 1
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("Munkidori", "Mind Bend")](ctx)
check(not b.active.confused,
      "an Energy-attached Pokémon can't be Confused under Festival Grounds")
b.active.energy = []
fx.ATTACK_EFFECTS[("Munkidori", "Mind Bend")](ctx)
check(b.active.confused, "with no Energy attached the immunity does not apply")

print("\n== Punk Up (on-evolve) ==")
st, a, b = blank_state("Marnie's Grimmsnarl ex", "Dragapult ex")
a.bench = [InPlayPokemon(card=mk("Marnie's Impidimp"))]
a.deck = [mk("Basic Darkness Energy")] * 7 + [mk("Ultra Ball")] * 5
ctx = fx.EffectContext(state=st, me=a, opp=b, source=a.active, db=db,
                       rng=st.rng, effect_kind="ability")
fx.ON_EVOLVE_TRIGGERS["Marnie's Grimmsnarl ex"](ctx)
attached = len(a.active.energy) + len(a.bench[0].energy)
check(attached == 5, f"searches and attaches exactly 5 Basic Darkness (got {attached})")
check(len(a.active.energy) >= 3, "the evolving Grimmsnarl is filled first")
check(sum(1 for c in a.deck if c.is_basic_energy and "Darkness" in c.types) == 2,
      "the other 2 stay in the deck")

print("\n== Shadow Bullet bench snipe respects the walls ==")
st, a, b = blank_state("Marnie's Grimmsnarl ex", "Dragapult ex")
b.bench = [InPlayPokemon(card=mk("Dreepy"), damage=40)]
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("Marnie's Grimmsnarl ex", "Shadow Bullet")](ctx)
check(b.bench[0].damage == 70, f"30 to the damaged bencher (got {b.bench[0].damage})")
b.bench = [InPlayPokemon(card=mk("Dreepy"), damage=40)]
b.bench.append(InPlayPokemon(card=mk("Rabsca")))
fx.ATTACK_EFFECTS[("Marnie's Grimmsnarl ex", "Shadow Bullet")](ctx)
check(all(m.damage in (0, 40) for m in b.bench),
      "Spherical Shield (Rabsca) prevents the bench damage entirely")

print("\n== Freezing Shroud at Pokémon Checkup ==")
st, a, b = blank_state("Froslass", "Dragapult ex")     # Dragapult ex has no ability
a.bench = [InPlayPokemon(card=mk("Munkidori"))]        # has an Ability
b.bench = [InPlayPokemon(card=mk("Fezandipiti ex"))]   # has an Ability
fx.pokemon_checkup(st)
check(a.bench[0].damage == 10 and b.bench[0].damage == 10,
      "1 counter on every Ability-holder, both sides")
check(a.active.damage == 0, "except any Froslass")
check(b.active.damage == 0, "a no-Ability Pokémon is untouched")
a.bench.append(InPlayPokemon(card=mk("Froslass")))     # second Froslass -> ×2
a.bench[0].damage = b.bench[0].damage = 0
fx.pokemon_checkup(st)
check(a.bench[0].damage == 20, "two Froslass stack: 2 counters per Checkup")

print("\n== Spikemuth Gym action ==")
st, a, b = blank_state("Marnie's Impidimp", "Dragapult ex")
a.deck = [mk("Marnie's Grimmsnarl ex"), mk("Marnie's Morgrem")] + [mk("Ultra Ball")] * 10
st.stadium, st.stadium_owner = mk("Spikemuth Gym"), 0
st.turn_number = 3
a.turns_taken = 2
acts = [x for x in game.legal_actions(st) if x.kind == "stadium_spikemuth"]
check(len(acts) == 2, f"one action per distinct Marnie's name in deck (got {len(acts)})")
game.apply_action(st, acts[0])       # sorted: "Marnie's Grimmsnarl ex" first
check(a.hand and a.hand[-1].name == "Marnie's Grimmsnarl ex",
      "target_index 0 fetches the ex (sorted-name encoding)")
check(a.stadium_spikemuth_used_this_turn, "budget consumed")
check(not [x for x in game.legal_actions(st) if x.kind == "stadium_spikemuth"],
      "once per turn")

print("\n== the rest of the new attacks ==")
st, a, b = blank_state("Yveltal", "Dragapult ex")
b.active.damage = 10
b.bench = [InPlayPokemon(card=mk("Dreepy"), damage=10), InPlayPokemon(card=mk("Dreepy"))]
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("Yveltal", "Corrosive Winds")](ctx)
check(b.active.damage == 30 and b.bench[0].damage == 30 and b.bench[1].damage == 0,
      "Corrosive Winds: 2 counters on each DAMAGED opposing Pokémon only")

st, a, b = blank_state("Snorunt", "Dragapult ex")
b.hand = [mk("Ultra Ball"), mk("Boss's Orders")]
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("Snorunt", "Astonish")](ctx)
check(len(b.hand) == 1 and len(b.deck) == 21,
      "Astonish: one random opposing hand card shuffled into the deck")

st, a, b = blank_state("Seaking", "Dragapult ex")
b.active.tool = mk("Air Balloon")
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("Seaking", "Peck Off")](ctx)
check(b.active.tool is None and b.discard and b.discard[-1].name == "Air Balloon",
      "Peck Off discards the Defending Pokémon's Tool")

st, a, b = blank_state("Seaking (PRE)", "Dragapult ex")
check(fx.has_festival_lead(a.active.card), "Seaking (PRE) print carries Festival Lead")
check(not fx.has_festival_lead(mk("Seaking")), "the TWM Seaking print does not")
h0 = len(a.hand)
ctx = ctx_for(st, a, b, a.active)
fx.ATTACK_EFFECTS[("Seaking (PRE)", "Rapid Draw")](ctx)
check(len(a.hand) == h0 + 2, "Rapid Draw draws 2")

st, a, b = blank_state("Tatsugiri", "Dragapult ex")
a.deck = [mk("Ultra Ball"), mk("Boss's Orders")] + [mk("Basic Fire Energy")] * 10
ctx = fx.EffectContext(state=st, me=a, opp=b, source=a.active, db=db,
                       rng=st.rng, effect_kind="ability")
fx.ABILITY_EFFECTS[("Tatsugiri", "Attract Customers")](ctx)
check(any(c.name == "Boss's Orders" for c in a.hand),
      "Attract Customers takes a Supporter from the top 6")

st, a, b = blank_state("Marnie's Impidimp", "Dragapult ex")
a.hand = [mk("Iris's Fighting Spirit"), mk("Basic Fire Energy"), mk("Ultra Ball")]
check(fx.can_play_trainer(st, a, "Iris's Fighting Spirit"), "Iris playable with 2+ cards")
a.hand.pop(0)
ctx = ctx_for(st, a, b, a.active)
fx.TRAINER_EFFECTS["Iris's Fighting Spirit"](ctx)
check(len(a.hand) == 6, f"Iris: discard 1, draw to 6 (hand={len(a.hand)})")

print("\n== Forest of Vitality ==")
st, a, b = blank_state("Grookey", "Dragapult ex")
a.bench = [InPlayPokemon(card=mk("Grookey"), played_this_turn=True)]
a.hand = [mk("Thwackey")]
a.turns_taken = 2
st.turn_number = 3
evs = [x for x in game.legal_actions(st) if x.kind == "evolve" and x.target_index == 0]
check(not evs, "normally a just-played Pokémon can't evolve")
st.stadium, st.stadium_owner = mk("Forest of Vitality"), 0
evs = [x for x in game.legal_actions(st) if x.kind == "evolve" and x.target_index == 0]
check(len(evs) == 1, "Forest of Vitality lets a just-played Grass Pokémon evolve")

print("\n" + ("ALL PASS" if not fails else f"{fails} FAILURES"))
sys.exit(1 if fails else 0)
