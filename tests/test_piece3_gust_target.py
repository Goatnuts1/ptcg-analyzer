#!/usr/bin/env python3
"""
test_piece3_gust_target.py — gate test for piece 3, policy #1: gust_target.

THE SEAM (the thing this gate tests): when state.targeting_policy is set,
effects._boss_orders MUST consult it for the target choice instead of running
the v0 lowest-HP fallback. When unset, behavior is unchanged (the doc's
regression-safety guarantee for Random/Greedy).

We don't test SearchPolicy's CONTENT here — that's a policy-correctness test
CC adds when implementing src/engine/policies.py. The gate tests the SEAM
exists and is honored. A stub policy is sufficient and keeps this test
self-contained (no dependency on policies.py existing on main).

RED ON CURRENT MAIN: _boss_orders ignores state.targeting_policy → drags the
lowest-HP mon (the v0 path) → test asserts the stub's expected pick was
honored → fail.
GREEN AFTER INTEGRATION: _boss_orders consults state.targeting_policy → returns
the stub's expected pick → pass.

The scenario keeps the original weakness-flips-target shape so the SEAM test
also demonstrates a realistic case the stub would represent (50-dmg Lightning
active vs. 80-HP Lightning-weak bench A and 60-HP no-weakness bench B), with
the engine's own _apply_weakness_resistance helper as the anchor.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card, Attack
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


class _StubGustPolicy:
    """Records that it was consulted and returns the test's expected pick.
    Stands in for SearchPolicy.gust_target during the SEAM gate."""
    def __init__(self, expected_pick):
        self.expected_pick = expected_pick
        self.consulted = False

    def gust_target(self, state, me, opp, attacker):
        self.consulted = True
        return self.expected_pick

    # SearchPolicy will also define cursed_blast_target / phantom_dive_spread.
    # The stub doesn't need them for this gate, but we provide no-op stubs so
    # the same instance can be attached without errors if a multi-effect path
    # somehow runs during this test.
    def cursed_blast_target(self, *_a, **_k): return None
    def phantom_dive_spread(self, *_a, **_k): return None


def _mk_basic(name, hp, types=("Colorless",), weakness=None, attack_dmg=0):
    atks = ()
    if attack_dmg:
        atks = (Attack(name=f"{name} Hit", cost=("Colorless",),
                       damage=attack_dmg, damage_suffix="", text=""),)
    return Card(
        id=f"synth-{name.lower().replace(' ','-')}",
        name=name, supertype="Pokémon",
        subtypes=("Basic",), hp=hp, types=tuple(types),
        evolves_from=None, evolves_to=(),
        abilities=(), attacks=atks, rules=(),
        weaknesses=((weakness, "×2"),) if weakness else (),
        resistances=(), retreat_cost=1, regulation_mark="H",
    )


def main():
    fails = []
    def check(c, m):
        if not c: fails.append(m)

    active_card = _mk_basic("Bolt Attacker", hp=120, types=("Lightning",),
                            weakness=None, attack_dmg=50)
    bench_a_card = _mk_basic("Weak Whale", hp=80, types=("Water",),
                             weakness="Lightning")
    bench_b_card = _mk_basic("Lower Bystander", hp=60, types=("Colorless",))

    me = PlayerState(name="A")
    opp = PlayerState(name="B")
    st = GameState(players=(me, opp), rng=random.Random(0))
    st.turn_number = 5

    me.active = InPlayPokemon(card=active_card)
    opp.active = InPlayPokemon(card=_mk_basic("Opp Active", hp=200))
    bench_a = InPlayPokemon(card=bench_a_card)
    bench_b = InPlayPokemon(card=bench_b_card)
    opp.bench = [bench_a, bench_b]

    # Anchor: the engine's own weakness math agrees with the scenario premise
    # (we do NOT duplicate damage math in the policy or the test).
    dmg_to_A = fx._apply_weakness_resistance(active_card, bench_a, 50)
    dmg_to_B = fx._apply_weakness_resistance(active_card, bench_b, 50)
    check(dmg_to_A == 100, f"engine weakness math: 50 → 100 via Lightning-weak, got {dmg_to_A}")
    check(dmg_to_B == 50,  f"engine no-weakness math: 50 → 50, got {dmg_to_B}")
    check(dmg_to_A >= bench_a_card.hp, "premise: weakness pick is the KO")
    check(dmg_to_B <  bench_b_card.hp, "premise: no-weakness pick is NOT a KO")

    # Attach the stub policy. After integration, _boss_orders MUST consult it.
    stub = _StubGustPolicy(expected_pick=bench_a)
    st.targeting_policy = stub

    ctx = fx.EffectContext(state=st, me=me, opp=opp, source=me.active,
                           rng=st.rng, db=getattr(st, "db", None))
    ok = fx._boss_orders(ctx)
    check(ok, "Boss's Orders should succeed when opponent has a bench")

    # THE SEAM ASSERTIONS:
    # (1) the policy must have been consulted (proves _boss_orders read targeting_policy)
    # (2) the policy's expected pick must be the one actually dragged
    check(stub.consulted,
          "_boss_orders MUST consult state.targeting_policy.gust_target when set "
          "(currently it ignores the attribute — the seam is the integration point)")
    check(opp.active is bench_a,
          f"the policy-supplied pick (Weak Whale) must be the dragged-up target; "
          f"got '{opp.active.card.name}'")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails: print(" -", f)
        sys.exit(1)
    print("OK — gust seam: _boss_orders consults state.targeting_policy and honors its pick.")


if __name__ == "__main__":
    main()
