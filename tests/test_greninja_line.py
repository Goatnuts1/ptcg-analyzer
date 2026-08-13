#!/usr/bin/env python3
"""
test_greninja_line.py — assert Frogadier's Numbing Water, Froakie's Flock, and
Mega Starmie ex's Nebula Beam / Jetting Blow do EXACTLY what their card text says
(data/standard_pool.json quoted inline, verified against limitlesstcg.com this
session).

Covers:
  - Frogadier (sv6-57): "Numbing Water" [W] 20 damage + coin-flip Paralysis rider
    (Paralysis not modeled in this engine — disclosed limitation, same class as
    Milotic ex's Hypno Splash Sleep rider).
  - Froakie (sv6-56): "Flock" [W] 0 damage, search up to 2 Froakie to the Bench.
  - Mega Starmie ex (me3-21): "Nebula Beam" [CCC] 210, ignores Weakness/Resistance
    AND any effects on the opponent's Active — the CRITICAL wall-bypass case
    (Crustle's Mysterious Rock Inn, which Mega Starmie ex's own 'ex' subtype
    actually gates) — contrasted against "Jetting Blow" [W] 120 + 50 bench, which
    does NOT bypass the same wall, proving the bypass is attack-specific.

Run from project root:  python3 tests/test_greninja_line.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import Card, CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db                    # effects read state.db for searches/chains
    st.turn_number = 5            # past turn-1 attack restriction
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source,
                            db=st.db, rng=st.rng)


class _FixedCoin:
    """A stand-in for ctx.rng that forces flip()'s randint(0,1) call to a fixed
    result, so the heads/tails branches of Numbing Water can each be exercised
    deterministically without hunting for a real Random() seed."""
    def __init__(self, value):
        self._value = value

    def randint(self, lo, hi):
        return self._value


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # =================================================================== #
    # FROGADIER (sv6-57, Water, 90 HP, Stage 1 evolves from Froakie)
    # Attack "Numbing Water" [W] 20 (pool text): "Flip a coin. If heads, your
    # opponent's Active Pokémon is now Paralyzed."
    # =================================================================== #

    # --- 1a. Effect called directly, HEADS: still exactly 20 base damage (the
    # engine applies the fixed base; the effect only handles the coin-flip rider),
    # and no crash/attribute mutation for the (unmodeled) Paralysis condition. ---
    st, a, b = fresh_state(db)
    frogadier = InPlayPokemon(card=db.get("Frogadier"))
    a.active = frogadier
    defender = InPlayPokemon(card=db.get("Pikachu ex"))     # not weak to Water
    b.active = defender
    ctx = ctx_for(st, me=a, opp=b, source=frogadier)
    ctx.rng = _FixedCoin(1)                                  # force heads
    fx._numbing_water(ctx)
    check(defender.damage == 0,
          "Numbing Water's registered effect must NOT itself apply the 20 base "
          "damage (that's the engine's job on the fixed-damage path) — it should "
          "only handle the coin-flip rider")
    check(not defender.confused,
          "Numbing Water's Paralysis rider must not spuriously set Confused "
          "(a different Special Condition) as a substitute")
    check(any("Paralyzed" in line for line in st.log),
          "heads should log the (unimplemented) Paralysis rider so the gap is "
          "visible, not silently swallowed")

    # --- 1b. Effect called directly, TAILS: logs tails, no rider mentioned. ---
    st, a, b = fresh_state(db)
    frogadier = InPlayPokemon(card=db.get("Frogadier"))
    a.active = frogadier
    defender = InPlayPokemon(card=db.get("Pikachu ex"))
    b.active = defender
    ctx = ctx_for(st, me=a, opp=b, source=frogadier)
    ctx.rng = _FixedCoin(0)                                   # force tails
    fx._numbing_water(ctx)
    check(any("tails" in line for line in st.log),
          "tails should be logged")
    check(not any("Paralyzed" in line for line in st.log),
          "tails must NOT log/apply the Paralysis rider")

    # --- 1c. Full attack resolution: exactly 20 damage lands on the opponent's
    # Active regardless of the coin flip (fixed damage, no Weakness in play here
    # since Pikachu ex isn't weak to Water). ---
    st, a, b = fresh_state(db)
    frogadier = InPlayPokemon(card=db.get("Frogadier"))
    a.active = frogadier
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    st.active_index = 0
    nw_i = next(i for i, atk in enumerate(frogadier.card.attacks)
                if atk.name == "Numbing Water")
    game._resolve_attack(st, nw_i)
    check(b.active is not None and b.active.damage == 20,
          f"Numbing Water should deal exactly 20 via full attack resolution, "
          f"got {b.active.damage if b.active else 'KO'}")

    # --- 1d. Full attack resolution + Weakness: Frogadier is Water-typed, so a
    # Lightning-weak defender (Pikachu ex is itself Lightning-typed and only weak
    # to Fighting — use a card actually weak to Water) takes 20x2=40. Charmander
    # (Fire, weak to Water x2, no Ability, not ex) isolates pure W/R math. ---
    st, a, b = fresh_state(db)
    frogadier = InPlayPokemon(card=db.get("Frogadier"))
    a.active = frogadier
    b.active = InPlayPokemon(card=db.get("Charmander"))       # weak to Water x2
    st.active_index = 0
    game._resolve_attack(st, nw_i)
    check(b.active is not None and b.active.damage == 40,
          f"Numbing Water should apply normal Weakness (20x2=40 vs a Water-weak "
          f"defender), got {b.active.damage if b.active else 'KO'}")

    # =================================================================== #
    # FROAKIE (sv6-56, Water, 60 HP, Basic)
    # Attack "Flock" [W] (pool text): "Search your deck for up to 2 Froakie and
    # put them onto your Bench. Then, shuffle your deck." (0 base damage.)
    # =================================================================== #

    # --- 2a. POSITIVE: 2 Froakie in the deck -> both benched, deck shuffled
    # (search_deck's shuffle=True default), 0 damage to the opponent. ---
    st, a, b = fresh_state(db)
    froakie = InPlayPokemon(card=db.get("Froakie"))
    a.active = froakie
    a.deck = [db.get("Froakie"), db.get("Froakie"), db.get("Basic Fire Energy")] * 1
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    st.active_index = 0
    fl_i = next(i for i, atk in enumerate(froakie.card.attacks) if atk.name == "Flock")
    game._resolve_attack(st, fl_i)
    check(sum(1 for m in a.bench if m.card.name == "Froakie") == 2,
          f"Flock with 2 Froakie in the deck should bench BOTH, got "
          f"{[m.card.name for m in a.bench]}")
    check(not any(c.name == "Froakie" for c in a.deck),
          "both Froakie should have left the deck")
    check(b.active is not None and b.active.damage == 0,
          f"Flock should deal 0 damage (search-only attack), "
          f"got {b.active.damage if b.active else 'KO'}")

    # --- 2b. Only 1 Froakie available in the deck -> benches exactly 1 (up to 2,
    # not fewer/more), no crash. ---
    st, a, b = fresh_state(db)
    froakie = InPlayPokemon(card=db.get("Froakie"))
    a.active = froakie
    a.deck = [db.get("Froakie"), db.get("Basic Fire Energy"), db.get("Basic Fire Energy")]
    ctx = ctx_for(st, me=a, opp=b, source=froakie)
    fx._flock(ctx)
    check(sum(1 for m in a.bench if m.card.name == "Froakie") == 1,
          f"Flock with only 1 Froakie in the deck should bench exactly 1, got "
          f"{[m.card.name for m in a.bench]}")

    # --- 2c. NEGATIVE: no Froakie in the deck at all -> no-op, no crash, no log
    # of a benched count. ---
    st, a, b = fresh_state(db)
    froakie = InPlayPokemon(card=db.get("Froakie"))
    a.active = froakie
    a.deck = [db.get("Basic Fire Energy")] * 5
    ctx = ctx_for(st, me=a, opp=b, source=froakie)
    fx._flock(ctx)
    check(len(a.bench) == 0,
          "Flock with no Froakie in the deck must bench nothing")
    check(not any("Flock: benched" in line for line in st.log),
          "Flock must not log a benched-count message when nothing was found")

    # --- 2d. Respects bench space: with the bench already at MAX_BENCH (5), Flock
    # must not overflow it even with 2 Froakie available in the deck. ---
    st, a, b = fresh_state(db)
    froakie = InPlayPokemon(card=db.get("Froakie"))
    a.active = froakie
    a.bench = [InPlayPokemon(card=db.get("Dreepy")) for _ in range(PlayerState.MAX_BENCH)]
    a.deck = [db.get("Froakie"), db.get("Froakie")]
    ctx = ctx_for(st, me=a, opp=b, source=froakie)
    fx._flock(ctx)
    check(len(a.bench) == PlayerState.MAX_BENCH,
          f"Flock must not push the bench past MAX_BENCH ({PlayerState.MAX_BENCH}), "
          f"got {len(a.bench)}")
    check(sum(1 for c in a.deck if c.name == "Froakie") == 2,
          "with the bench already full, both Froakie must remain in the deck "
          "(search_deck's bench-space guard breaks before removing any)")

    # =================================================================== #
    # MEGA STARMIE EX (me3-21, Water, 330 HP, Stage 1 MEGA ex, evolves from Staryu)
    # Attack "Jetting Blow" [W] 120 (pool text): "This attack also does 50 damage
    #   to 1 of your opponent's Benched Pokémon. (Don't apply Weakness and
    #   Resistance for Benched Pokémon.)"
    # Attack "Nebula Beam" [CCC] 210 (pool text): "This attack's damage isn't
    #   affected by Weakness or Resistance, or by any effects on your opponent's
    #   Active Pokémon."
    # =================================================================== #

    # --- 3a. CRITICAL: Nebula Beam bypasses Crustle's "Mysterious Rock Inn"
    # ("Prevent all damage done to this Pokémon by attacks from your opponent's
    # Pokémon ex") — gated on the ATTACKER being an opponent's Pokémon ex, which
    # Mega Starmie ex genuinely is (subtypes include 'ex'), so the wall's own
    # condition is truly satisfied here; Nebula Beam's ignore_active_effects=True
    # bypasses it anyway for the FULL 210. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    crustle = InPlayPokemon(card=db.get("Crustle"))            # Mysterious Rock Inn
    b.active = crustle
    st.active_index = 0
    nb_i = next(i for i, atk in enumerate(starmie.card.attacks)
                if atk.name == "Nebula Beam")
    check("ex" in starmie.card.subtypes,
          "setup: Mega Starmie ex must carry the 'ex' subtype (satisfies Mysterious "
          "Rock Inn's own gating condition) for this to be a meaningful bypass test")
    game._resolve_attack(st, nb_i)
    check(crustle.damage == 210,
          f"Nebula Beam must deal the FULL 210, unprevented, through Crustle's "
          f"Mysterious Rock Inn wall (bypass-by-attack, not a blanket Ability "
          f"suppression), got {crustle.damage}")

    # --- 3b. CRITICAL CONTRAST: the SAME defender (a fresh, undamaged Crustle)
    # takes 0 to its Active slot from Jetting Blow's 120 component — proving the
    # bypass is ATTACK-SPECIFIC (Jetting Blow does not carry ignore_active_effects),
    # not a blanket disable of the wall for the whole Mega Starmie ex card. The
    # bench-hit 50 still lands on a separate (non-wall-holding) benched Pokémon,
    # confirming Jetting Blow otherwise resolves normally. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    crustle2 = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle2
    bench_mon = InPlayPokemon(card=db.get("Dreepy"))
    b.bench = [bench_mon]
    st.active_index = 0
    jb_i = next(i for i, atk in enumerate(starmie.card.attacks)
                if atk.name == "Jetting Blow")
    game._resolve_attack(st, jb_i)
    check(crustle2.damage == 0,
          f"Jetting Blow's 120-to-Active component must be BLOCKED by Mysterious "
          f"Rock Inn (Mega Starmie ex is an opponent ex, and Jetting Blow does not "
          f"ignore active effects), got {crustle2.damage}")
    check(bench_mon.damage == 50,
          f"Jetting Blow's 50-to-bench component must still land normally on a "
          f"non-wall-holding Benched Pokémon, got {bench_mon.damage}")

    # --- 3c. Nebula Beam ignores Weakness too: Charmander is weak to Water x2
    # (Mega Starmie ex's type) — a normal Water attack would deal double, but
    # Nebula Beam must deal exactly 210, not 420. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    charmander = InPlayPokemon(card=db.get("Charmander"))       # weak to Water x2
    b.active = charmander
    st.active_index = 0
    game._resolve_attack(st, nb_i)
    check(charmander.damage == 210,
          f"Nebula Beam must ignore Weakness (210, not 420 despite Charmander's "
          f"Water weakness), got {charmander.damage}")

    # --- 3d. Nebula Beam bypasses a shield ("effects on the opponent's Active"),
    # same chokepoint as Superb Scissors/Demolish. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    shielded_def = InPlayPokemon(card=db.get("Dragapult ex"))    # 320 HP, no weakness
    shielded_def.shielded = True
    b.active = shielded_def
    st.active_index = 0
    game._resolve_attack(st, nb_i)
    check(shielded_def.damage == 210,
          f"Nebula Beam should bypass a shield for the full 210, "
          f"got {shielded_def.damage}")

    # --- 3e. Baseline (no wall/weakness/shield noise): exactly 210, proving the
    # engine doesn't double-apply base damage + the registered effect (Nebula
    # Beam owns its damage via ATTACK_EFFECT_OWNS_DAMAGE). ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    plain_def = InPlayPokemon(card=db.get("Pikachu ex"))         # not weak to Water
    b.active = plain_def
    st.active_index = 0
    game._resolve_attack(st, nb_i)
    check(plain_def.damage == 210,
          f"Nebula Beam should deal exactly 210 (no double-apply), "
          f"got {plain_def.damage}")

    # --- 3f. NEGATIVE: without any wall/ex-gate in play, Jetting Blow's Active
    # component resolves as a plain 120 (isolating that the block in 3b really
    # was the wall, not some other bug suppressing Jetting Blow's base damage
    # unconditionally). ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    plain_def2 = InPlayPokemon(card=db.get("Pikachu ex"))        # no wall Ability
    b.active = plain_def2
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(plain_def2.damage == 120,
          f"Jetting Blow's Active component should deal a plain 120 against a "
          f"non-wall defender, got {plain_def2.damage}")

    # --- 3g. Jetting Blow bench-target v0 policy: with 2 benched Pokémon, the
    # LOWEST remaining-HP one (closest to KO) is hit for 50 — mirrors the gust-
    # style policy used elsewhere in this engine (Break Through / Insta-Strike). ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    low_hp_bench = InPlayPokemon(card=db.get("Dreepy"))          # 80 HP
    low_hp_bench.damage = 60                                      # remaining_hp = 20
    high_hp_bench = InPlayPokemon(card=db.get("Abra"))
    b.bench = [high_hp_bench, low_hp_bench]
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(low_hp_bench.damage == 60 + 50,
          f"Jetting Blow should target the LOWEST remaining-HP bencher, "
          f"got low_hp_bench.damage={low_hp_bench.damage}")
    check(high_hp_bench.damage == 0,
          f"Jetting Blow should NOT also hit the higher-HP bencher, "
          f"got high_hp_bench.damage={high_hp_bench.damage}")

    # --- 3h. NEGATIVE: with no benched Pokémon at all, Jetting Blow's spread
    # component is a no-op (no crash), while the 120 to Active still lands. ---
    st, a, b = fresh_state(db)
    starmie = InPlayPokemon(card=db.get("Mega Starmie ex"))
    a.active = starmie
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    b.bench = []
    st.active_index = 0
    game._resolve_attack(st, jb_i)
    check(b.active is not None and b.active.damage == 120,
          f"Jetting Blow with an empty opponent bench should still deal 120 to "
          f"the Active with no crash, got "
          f"{b.active.damage if b.active else 'KO'}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — Frogadier (Numbing Water), Froakie (Flock), and Mega Starmie ex "
          "(Nebula Beam wall-bypass vs Jetting Blow's attack-specific non-bypass, "
          "contrasted on the SAME Crustle defender) all hold.")


if __name__ == "__main__":
    main()
