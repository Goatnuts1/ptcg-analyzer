#!/usr/bin/env python3
"""
test_piece3_policy_logic.py — correctness tests for the REAL SearchPolicy.

The three gate tests (test_piece3_*.py) prove the engine SEAM is honored using
STUB policies. This file pins the actual SearchPolicy decision logic so the
regression's mechanism metrics rest on tested behavior, not just a wired hook.

Covered:
  - gust_target: picks the KO-via-weakness target over a lower-HP non-KO one,
    and falls back to v0 (lowest HP) when no KO is available.
  - cursed_blast_target: prefers the engine piece on a prize tie; returns None
    (defer to v0) when nothing is KO-able.
  - phantom_dive_spread: distributes to set up >=2 next-turn threats, and
    returns None (defer to v0 pile-drive) when it can't.

Run from project root:  python3 tests/test_piece3_policy_logic.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card, Attack
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine.policies import SearchPolicy, ENGINE_PIECE_NAMES


def _mk(name, hp, types=("Colorless",), weakness=None, attack_dmg=0,
        attack_cost=("Colorless",), is_basic=True, abilities=()):
    atks = ()
    if attack_dmg:
        atks = (Attack(name=f"{name} Hit", cost=tuple(attack_cost),
                       damage=attack_dmg, damage_suffix="", text=""),)
    return Card(
        id=f"synth-{name.lower().replace(' ','-')}",
        name=name, supertype="Pokémon",
        subtypes=("Basic",) if is_basic else ("Stage 1",), hp=hp, types=tuple(types),
        evolves_from=None if is_basic else "Some Basic", evolves_to=(),
        abilities=abilities, attacks=atks, rules=(),
        weaknesses=((weakness, "×2"),) if weakness else (),
        resistances=(), retreat_cost=1, regulation_mark="H",
    )


def _state(me, opp):
    st = GameState(players=(me, opp), rng=random.Random(0))
    st.turn_number = 5
    return st


def main():
    fails = []
    def check(c, m):
        if not c: fails.append(m)
    pol = SearchPolicy()

    # ---- gust: weakness flips the target -------------------------------- #
    # Active: Lightning, 50 dmg, 1 Lightning energy attached (affordable).
    active = InPlayPokemon(card=_mk("Bolt", 120, types=("Lightning",), attack_dmg=50,
                                    attack_cost=("Lightning",)))
    from src.engine.cards import Card as _C
    # give it a Lightning energy so can_pay_cost passes
    active.energy.append(_mk("Basic Lightning Energy", 0))  # placeholder; see below
    # use a real basic-energy-like card: simplest is to fake provides via types
    # (can_pay_cost checks energy types) — set the energy card's types to Lightning.
    active.energy[-1] = type(active.card)(
        id="e-l", name="Lightning Energy", supertype="Energy", subtypes=("Basic",),
        hp=None, types=("Lightning",), evolves_from=None, evolves_to=(),
        abilities=(), attacks=(), rules=(), weaknesses=(), resistances=(),
        retreat_cost=0, regulation_mark="H")
    me = PlayerState(name="A"); me.active = active
    opp = PlayerState(name="B"); opp.active = InPlayPokemon(card=_mk("OppA", 200))
    weak = InPlayPokemon(card=_mk("Weak Whale", 80, types=("Water",), weakness="Lightning"))
    low  = InPlayPokemon(card=_mk("Low Bystander", 60))
    opp.bench = [weak, low]
    st = _state(me, opp)
    pick = pol.gust_target(st, me, opp, active)
    check(pick is weak, f"gust should pick the KO-via-weakness target (Weak Whale), got "
                        f"{pick.card.name if pick else None}")

    # gust fallback: no KO available -> lowest HP (v0)
    me2 = PlayerState(name="A"); me2.active = InPlayPokemon(card=_mk("NoAtk", 100))  # 0 dmg
    opp2 = PlayerState(name="B"); opp2.active = InPlayPokemon(card=_mk("OppA", 200))
    big = InPlayPokemon(card=_mk("Big", 200)); small = InPlayPokemon(card=_mk("Small", 70))
    opp2.bench = [big, small]
    st2 = _state(me2, opp2)
    pick2 = pol.gust_target(st2, me2, opp2, me2.active)
    check(pick2 is small, f"gust no-KO fallback should be lowest-HP (Small), got "
                          f"{pick2.card.name if pick2 else None}")

    # ---- cursed blast: engine piece beats lower-HP basic on prize tie --- #
    me3 = PlayerState(name="A"); me3.active = InPlayPokemon(card=_mk("Dusknoir", 160, is_basic=False))
    opp3 = PlayerState(name="B"); opp3.active = InPlayPokemon(card=_mk("OppA", 200))
    engine = InPlayPokemon(card=_mk("Dudunsparce", 120, is_basic=False))
    basic  = InPlayPokemon(card=_mk("Bystander Basic", 90))
    opp3.bench = [engine, basic]
    st3 = _state(me3, opp3)
    check("Dudunsparce" in ENGINE_PIECE_NAMES, "Dudunsparce must be in the allowlist")
    cpick = pol.cursed_blast_target(st3, me3, opp3, 130)
    check(cpick is engine, f"cursed blast should KO the engine piece, got "
                           f"{cpick.card.name if cpick else None}")
    # nothing KO-able -> None (defer to v0)
    opp3.bench = [InPlayPokemon(card=_mk("Tanky", 300))]
    opp3.active = InPlayPokemon(card=_mk("OppTank", 300))
    check(pol.cursed_blast_target(st3, me3, opp3, 130) is None,
          "cursed blast with no KO-able target should return None (defer to v0)")

    # ---- phantom dive: distribute for >=2 threats ----------------------- #
    me4 = PlayerState(name="A"); me4.active = InPlayPokemon(card=_mk("Phantom", 320))
    opp4 = PlayerState(name="B"); opp4.active = InPlayPokemon(card=_mk("OppA", 300))
    b1 = InPlayPokemon(card=_mk("B Low", 60))
    b2 = InPlayPokemon(card=_mk("B Mid", 80))
    b3 = InPlayPokemon(card=_mk("B High", 100))
    opp4.bench = [b1, b2, b3]
    st4 = _state(me4, opp4)
    dist = pol.phantom_dive_spread(st4, me4, opp4, 6)
    check(dist is not None and len(dist) >= 1, "phantom spread should return a distribution")
    total = sum(c for _, c in dist) if dist else 0
    check(total <= 6, f"distribution must respect the 6-counter budget, used {total}")
    # apply and count threats vs the recurring 60-dmg spread
    if dist:
        for t, c in dist:
            t.damage += c * 10
    in_range = sum(1 for m in opp4.bench if m.remaining_hp <= 60)
    check(in_range >= 2, f"phantom spread should set up >=2 next-turn threats, got {in_range}")

    # phantom fallback: a lone huge bencher -> can't make 2 threats -> None
    me5 = PlayerState(name="A"); me5.active = InPlayPokemon(card=_mk("Phantom", 320))
    opp5 = PlayerState(name="B"); opp5.active = InPlayPokemon(card=_mk("OppA", 300))
    opp5.bench = [InPlayPokemon(card=_mk("Lone", 300))]
    st5 = _state(me5, opp5)
    check(pol.phantom_dive_spread(st5, me5, opp5, 6) is None,
          "phantom spread with <2 benchers should return None (defer to v0)")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails: print(" -", f)
        sys.exit(1)
    print("OK — SearchPolicy logic: gust KO/fallback, cursed engine-pick/defer, phantom spread/defer.")


if __name__ == "__main__":
    main()
