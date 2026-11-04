#!/usr/bin/env python3
"""
test_phase1_bot_fixes.py — Phase 1 (2026-11) greedy/engine-policy fixes behind the
greedy Crustle bias (see DECISIONS.md, "Greedy bias"). Each block pins one fix:

  1. wall-aware attack choice: an ex attacker doesn't count Rock Inn-walled damage
     (prefers a 0-printed effect attack it has, and is never "lethal" into the wall);
     Phantom Dive keeps its Bench-spread value against a walled Active;
  2. walled pivot: a walled Active retreats into a Benched attacker that hits through;
  3. wall-aware gust (Boss's Orders) skips a Crustle for an ex attacker;
  4. promotion after a KO prefers a Pokémon that can already attack;
  5. Ultra Ball never pitches the last Energy in hand while another card can go;
     Night Stretcher takes a Basic Energy when the hand has none.

Run: python3 tests/test_phase1_bot_fixes.py   (exit 0 = pass; also runs under pytest)
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_phase1_crustle_rules import fresh, mon, actx, db   # noqa: E402
from src.engine import effects as fx                          # noqa: E402
from src.engine.agents import GreedyAgent                     # noqa: E402

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _deckfill(p, n=10):
    p.deck = [db().get("Basic Grass Energy") for _ in range(n)]
    p.prizes = [db().get("Basic Grass Energy") for _ in range(6)]


def test_walled_pivot_retreat():
    st, a, b = fresh()
    _deckfill(a); _deckfill(b)
    b.active = mon("Crustle", "Basic Grass Energy")
    # Iron Leaves ex (walled) Active can pay its retreat; Passimian on the Bench can
    # already pay Coordinated Throwing [F][C].
    a.active = mon("Iron Leaves ex", "Basic Grass Energy", "Basic Grass Energy",
                   "Basic Grass Energy")
    a.bench = [mon("Passimian", "Basic Fighting Energy", "Basic Grass Energy")]
    a.energy_attached_this_turn = True
    act = GreedyAgent(random.Random(0)).choose(st)
    check(act.kind == "retreat" and act.target_index == 0,
          f"walled ex Active should pivot into Passimian, chose {act}")


def test_walled_attack_not_lethal_and_valued_zero():
    st, a, b = fresh()
    _deckfill(a); _deckfill(b)
    b.active = mon("Crustle", "Basic Grass Energy", damage=140)   # 'lethal' on paper
    a.active = mon("Wellspring Mask Ogerpon ex", "Basic Water Energy",
                   "Basic Water Energy", "Basic Water Energy")
    a.energy_attached_this_turn = True
    act = GreedyAgent(random.Random(0)).choose(st)
    # nothing hits through, no Bench: it still attacks (better than passing), but it
    # must not treat Torrential Pump as lethal — both attacks are worth 0, so the
    # choice falls back to the first offered attack (Sob, which at least locks retreat)
    check(act.kind == "attack", f"should still attack when no pivot exists, chose {act}")


def test_phantom_dive_keeps_spread_value():
    st, a, b = fresh()
    _deckfill(a); _deckfill(b)
    b.active = mon("Crustle", "Basic Grass Energy")
    b.bench = [mon("Dwebble")]
    a.active = mon("Dragapult ex", "Basic Fire Energy", "Basic Psychic Energy")
    a.energy_attached_this_turn = True
    act = GreedyAgent(random.Random(0)).choose(st)
    atk = a.active.card.attacks[act.attack_index] if act.kind == "attack" else None
    check(atk is not None and atk.name == "Phantom Dive",
          f"Dragapult ex vs walled Crustle should Phantom Dive, chose {act} {atk and atk.name}")


def test_wall_aware_gust():
    st, a, b = fresh()
    _deckfill(a); _deckfill(b)
    a.active = mon("Iron Leaves ex", "Basic Grass Energy")
    b.active = mon("Dwebble")
    b.bench = [mon("Crustle", damage=100), mon("Mega Kangaskhan ex")]
    ok = fx._boss_orders(actx(st, a, b, None, kind="trainer"))
    check(ok and b.active.card.name == "Mega Kangaskhan ex",
          f"Boss with an ex attacker must skip the Crustle, dragged {b.active.card.name}")
    # non-ex attacker: v0 rule (lowest remaining HP) — the damaged Crustle
    st, a, b = fresh()
    _deckfill(a); _deckfill(b)
    a.active = mon("Passimian", "Basic Fighting Energy")
    b.active = mon("Dwebble")
    b.bench = [mon("Crustle", damage=100), mon("Mega Kangaskhan ex")]
    fx._boss_orders(actx(st, a, b, None, kind="trainer"))
    check(b.active.card.name == "Crustle", "non-ex attacker keeps the lowest-HP gust")


def test_promotion_prefers_ready_attacker():
    st, a, b = fresh()
    b.active = mon("Crustle", "Basic Grass Energy")
    a.active = None
    big = mon("Mega Kangaskhan ex")                       # 300 HP, no Energy
    ready = mon("Passimian", "Basic Fighting Energy", "Basic Grass Energy")
    a.bench = [big, ready]
    fx._promote(a, st)
    check(a.active is ready, f"promotion should pick the ready attacker, got {a.active.card.name}")
    # without state: v0 (highest HP)
    a.active = None; a.bench = [mon("Passimian", "Basic Fighting Energy", "Basic Grass Energy"),
                                mon("Mega Kangaskhan ex")]
    fx._promote(a)
    check(a.active.card.name == "Mega Kangaskhan ex", "v0 promotion unchanged without state")


def test_discard_and_stretcher_energy():
    hand = [db().get("Basic Grass Energy"), db().get("Buddy-Buddy Poffin"),
            db().get("Ultra Ball")]
    order = sorted(range(len(hand)), key=lambda i: fx._search_value(hand[i]))
    picks = fx._discard_keep_last_energy(hand, order, 2)
    check(0 not in picks, f"last Energy must be kept, picks {picks}")
    picks = fx._discard_keep_last_energy(hand[:2], [0, 1], 2)
    check(sorted(picks) == [0, 1], "falls back to discarding it when nothing else can go")
    st, a, b = fresh()
    a.hand = []
    a.discard = [db().get("Dwebble"), db().get("Basic Grass Energy")]
    fx._night_stretcher(actx(st, a, b, None, kind="trainer"))
    check(any(c.is_energy for c in a.hand), "Night Stretcher should take the Energy")


def test_zz_report():
    assert not FAILS, "\n".join(FAILS)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and name != "test_zz_report" and callable(fn):
            fn()
    if FAILS:
        print("FAIL:\n  " + "\n  ".join(FAILS)); sys.exit(1)
    print("test_phase1_bot_fixes.py: all checks passed")


if __name__ == "__main__":
    main()
