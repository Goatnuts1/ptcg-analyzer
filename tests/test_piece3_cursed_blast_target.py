#!/usr/bin/env python3
"""
test_piece3_cursed_blast_target.py — gate test for piece 3, policy #2.

THE SEAM: _cursed_blast (NOT _pick_ko_target) MUST consult state.targeting_policy
for the engine-value tie-break. _pick_ko_target stays v0 — it's shared by
_cruel_arrow, the 280-dmg discard attack, and _adrena_brain, and we MUST NOT
silently re-target those (the same scoping caveat the doc has for
place_counters_on_bench being scoped to Phantom Dive's call site).

So the hook lives at effects.py:545 (the _cursed_blast body), like:
    pol = getattr(ctx.state, "targeting_policy", None)
    target = (pol.cursed_blast_target(...) if pol else None) \\
             or _pick_ko_target(opp, counters * 10) or opp.active

RED ON CURRENT MAIN: _cursed_blast ignores state.targeting_policy → calls bare
_pick_ko_target → on prize-tie, lowest-HP (Bystander) → test asserts the stub
was consulted AND its pick (Dudunsparce) was KO'd → fail.
GREEN AFTER INTEGRATION: _cursed_blast consults the seam, stub returns
Dudunsparce, Dudunsparce KO'd → pass.

We invoke _cursed_blast_13 end-to-end (not just _pick_ko_target) so the test
actually exercises the call-site hook, not the shared helper.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


class _StubCursedBlastPolicy:
    """Records consultation, returns the test's expected pick."""
    def __init__(self, expected_pick):
        self.expected_pick = expected_pick
        self.consulted = False

    def cursed_blast_target(self, state, me, opp, dmg):
        self.consulted = True
        return self.expected_pick

    def gust_target(self, *_a, **_k): return None
    def phantom_dive_spread(self, *_a, **_k): return None


def _mk_card(name, hp, is_basic=True):
    subtypes = ("Basic",) if is_basic else ("Stage 1",)
    return Card(
        id=f"synth-{name.lower().replace(' ', '-')}",
        name=name, supertype="Pokémon",
        subtypes=subtypes, hp=hp, types=("Colorless",),
        evolves_from=None if is_basic else "Some Basic",
        evolves_to=(), abilities=(), attacks=(), rules=(),
        weaknesses=(), resistances=(), retreat_cost=1, regulation_mark="H",
    )


def main():
    fails = []
    def check(c, m):
        if not c: fails.append(m)

    dudunsparce = InPlayPokemon(card=_mk_card("Dudunsparce", hp=120, is_basic=False))
    bystander   = InPlayPokemon(card=_mk_card("Bystander Basic", hp=90, is_basic=True))

    me = PlayerState(name="A")
    opp = PlayerState(name="B")
    st = GameState(players=(me, opp), rng=random.Random(0))
    st.turn_number = 5

    # Source: Dusknoir stand-in (the Cursed Blast caster). 13 counters = 130 dmg.
    dusknoir = InPlayPokemon(card=_mk_card("Dusknoir Stand-in", hp=160, is_basic=False))
    me.active = dusknoir
    opp.active = InPlayPokemon(card=_mk_card("Opp Active", hp=200))
    opp.bench = [dudunsparce, bystander]

    # Premise sanity.
    dmg = 130
    check(dudunsparce.remaining_hp <= dmg, "Dudunsparce must be KO-able at 130")
    check(bystander.remaining_hp   <= dmg, "Bystander must be KO-able at 130")
    check(dudunsparce.card.gives_up_prizes == bystander.card.gives_up_prizes,
          "premise: same prizes — engine value is the only differentiator")

    # Attach the stub. After integration, _cursed_blast MUST consult it.
    stub = _StubCursedBlastPolicy(expected_pick=dudunsparce)
    st.targeting_policy = stub

    ctx = fx.EffectContext(state=st, me=me, opp=opp, source=dusknoir,
                           rng=st.rng, db=getattr(st, "db", None))
    fx._cursed_blast_13(ctx)   # end-to-end: exercises the call-site seam

    check(stub.consulted,
          "_cursed_blast MUST consult state.targeting_policy.cursed_blast_target "
          "when set. NOTE: the hook must live in _cursed_blast (effects.py:545), "
          "NOT in _pick_ko_target — that helper is shared by Cruel Arrow / "
          "Explosion Y / Adrena-Brain and must remain v0.")
    check(dudunsparce.is_knocked_out,
          f"the policy-supplied pick (Dudunsparce) must be the one KO'd; "
          f"Dudunsparce KO'd={dudunsparce.is_knocked_out}, "
          f"Bystander KO'd={bystander.is_knocked_out}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails: print(" -", f)
        sys.exit(1)
    print("OK — Cursed Blast seam: _cursed_blast consults state.targeting_policy and honors its pick.")


if __name__ == "__main__":
    main()
