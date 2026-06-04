#!/usr/bin/env python3
"""
test_piece3_phantom_dive_spread.py — gate test for piece 3, policy #3.

THE SEAM: _phantom_dive (NOT place_counters_on_bench unconditionally) MUST
consult state.targeting_policy for the spread distribution. place_counters_on_bench
keeps its v0 "maximize_ko" default — other effects that call it (grep for
policy="maximize_ko") MUST continue to pile-drive unless explicitly opted in.
The hook lives at _phantom_dive (effects.py:443-445), like:
    pol = getattr(ctx.state, "targeting_policy", None)
    dist = pol.phantom_dive_spread(...) if pol else None
    if dist:  apply dist counter-by-counter via place_counters
    else:     place_counters_on_bench(ctx, counters=6, policy="maximize_ko")

THE SPEC (ratified — see PIECE3_target_policies.md §3 and review verdict):
distribute 6 counters to MAXIMIZE benched mons in 1HKO range of the active's
expected next-turn attack damage, accepting the trade of 1 immediate KO for
deferred double-threat. Spread-attacker playstyle.

Scenario: bench [60, 80, 100] HP, 6 counters, modeled next-turn dmg = 50.
v0 pile-drives bench[0] (60→KO) → 0 survivors in 1HKO range of 50.
Correct: 1 on bench[0] (60→50: in range), 3 on bench[1] (80→50: in range),
         2 leftover wherever → 2 survivors in 1HKO range.

RED ON CURRENT MAIN: _phantom_dive ignores state.targeting_policy → calls bare
place_counters_on_bench with maximize_ko → pile-drive → 0 survivors in range
→ test asserts stub was consulted AND ≥2 in range → fail.
GREEN AFTER INTEGRATION: _phantom_dive consults the seam, stub-supplied
distribution applied → ≥2 in range → pass.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


NEXT_TURN_DMG = 50


class _StubPhantomDivePolicy:
    """Records consultation, returns a list of (target, counters) pairs.

    Contract: list of (InPlayPokemon, int_counters). Sum of counters ≤ budget.
    List (not dict) because InPlayPokemon is @dataclass and therefore unhashable
    — the engine identifies targets by object identity, not value equality.
    """
    def __init__(self, bench_index_to_counters):
        # tests pass in bench indexes; we resolve to live InPlayPokemon at call time
        self.bench_index_to_counters = bench_index_to_counters
        self.consulted = False

    def phantom_dive_spread(self, state, me, opp, counters):
        self.consulted = True
        total = sum(c for _, c in self.bench_index_to_counters)
        assert total <= counters, f"stub distribution over budget: {total} > {counters}"
        return [(opp.bench[i], c) for i, c in self.bench_index_to_counters]

    def gust_target(self, *_a, **_k): return None
    def cursed_blast_target(self, *_a, **_k): return None


def _mk_basic(name, hp):
    return Card(
        id=f"synth-{name.lower().replace(' ','-')}",
        name=name, supertype="Pokémon",
        subtypes=("Basic",), hp=hp, types=("Colorless",),
        evolves_from=None, evolves_to=(),
        abilities=(), attacks=(), rules=(),
        weaknesses=(), resistances=(), retreat_cost=1, regulation_mark="H",
    )


def _count_in_1hko_range(opp, dmg):
    return sum(1 for m in opp.bench
               if not m.is_knocked_out and m.remaining_hp <= dmg)


def main():
    fails = []
    def check(c, m):
        if not c: fails.append(m)

    me = PlayerState(name="A")
    opp = PlayerState(name="B")
    st = GameState(players=(me, opp), rng=random.Random(0))
    st.turn_number = 5

    # Active: Dragapult ex stand-in. Opp active: stays alive through 200 base.
    dragapult = InPlayPokemon(card=_mk_basic("Phantom Source", hp=320))
    # Phantom Dive in effects.py applies 200 to opp.active via the engine's
    # attack chokepoint BEFORE the registered effect runs (per the engine note),
    # so opp.active needs to survive 200. 300 HP synth keeps the scenario stable.
    me.active = dragapult
    opp.active = InPlayPokemon(card=_mk_basic("Opp Active", hp=300))
    bench_low  = InPlayPokemon(card=_mk_basic("Bench Low",  60))
    bench_mid  = InPlayPokemon(card=_mk_basic("Bench Mid",  80))
    bench_high = InPlayPokemon(card=_mk_basic("Bench High", 100))
    opp.bench = [bench_low, bench_mid, bench_high]

    # Premise: at full HP none in 1HKO range of 50 dmg.
    pre = _count_in_1hko_range(opp, NEXT_TURN_DMG)
    check(pre == 0, f"premise: 0 in 1HKO range at full HP, got {pre}")

    # Stub supplies the correct distribution: 1 on Low (60→50), 3 on Mid (80→50).
    # 2 leftover counters allowed by the contract (total 4 ≤ 6 budget).
    # Bench indexes: 0=Low, 1=Mid, 2=High.
    stub = _StubPhantomDivePolicy(bench_index_to_counters=[(0, 1), (1, 3)])
    st.targeting_policy = stub

    ctx = fx.EffectContext(state=st, me=me, opp=opp, source=dragapult,
                           rng=st.rng, db=getattr(st, "db", None))
    # Invoke _phantom_dive end-to-end (it applies 200 to opp.active via the
    # attack chokepoint, then the registered effect runs the spread). This is
    # the SEAM-bearing call site.
    fx._phantom_dive(ctx)

    in_range = _count_in_1hko_range(opp, NEXT_TURN_DMG)
    survived = [m for m in opp.bench if not m.is_knocked_out]
    print(f"  diag: consulted={stub.consulted}; survivors in 1HKO range of "
          f"{NEXT_TURN_DMG}: {in_range} / {len(survived)}")

    check(stub.consulted,
          "_phantom_dive MUST consult state.targeting_policy.phantom_dive_spread "
          "when set. The hook lives at the _phantom_dive call site — "
          "place_counters_on_bench stays v0 for its other callers.")
    check(in_range >= 2,
          f"piece-3 spread policy: ≥2 survivors in 1HKO range of "
          f"{NEXT_TURN_DMG} dmg; got {in_range}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails: print(" -", f)
        sys.exit(1)
    print("OK — Phantom Dive seam: _phantom_dive consults state.targeting_policy and honors its distribution.")


if __name__ == "__main__":
    main()
