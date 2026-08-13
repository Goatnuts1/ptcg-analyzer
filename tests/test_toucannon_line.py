#!/usr/bin/env python3
"""
test_toucannon_line.py — the Pitch Black Toucannon line and its Stellar Crown /
Temporal Forces support, asserted against the exact printed text of each card.

CARDS UNDER TEST

  Pikipek (me5 66)      [C] Double Stab 10×: "Flip 2 coins. This attack does 10 damage
                        for each heads."
  Trumbeak (me5 67)     [C] Fly 30: "Flip a coin. If tails, this attack does nothing. If
                        heads, during your opponent's next turn, prevent all damage from
                        and effects of attacks done to this Pokémon."
  Toucannon (me5 68)    Ability "Aerial Draw": "Once during your turn, you may use this
                        Ability. Draw a card."
                        [C] Feather Rondo 60+: "This attack does 20 more damage for each
                        Benched Pokémon (both yours and your opponent's)."
  Hoothoot (SCR)        [C] Triple Stab 10×: "Flip 3 coins. This attack does 10 damage
  (sv7-114)             for each heads."  — the SUFFIXED print. The pool's BARE
                        "Hoothoot" is sv5-126 (Temporal Forces): [C][C] Silent Wing 20,
                        "Your opponent reveals their hand." Both are asserted here.
  Noctowl (SCR 115 /    Ability "Jewel Seeker": "Once during your turn, when you play this
  svp-141)              Pokémon from your hand to evolve 1 of your Pokémon, if you have
                        any Tera Pokémon in play, you may search your deck for up to 2
                        Trainer cards, reveal them, and put them into your hand. Then,
                        shuffle your deck."
                        [C][C] Speed Wing 60 (no text).
  Iron Leaves ex        Ability "Rapid Vernier": "When you play this Pokémon from your
  (TEF 25 / svp-128)    hand onto your Bench during your turn, you may switch it with
                        your Active Pokémon. If you do, you may move any amount of Energy
                        from your other Pokémon to this Pokémon."
                        [G][G][C] Prism Edge 180: "During your next turn, this Pokémon
                        can't attack."

Run: python3 tests/test_toucannon_line.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine import game
from src.engine.game import Action


class ScriptedRNG(random.Random):
    """A Random whose randint() returns a scripted sequence, so coin flips are exact.
    effects.flip() is `bool(ctx.rng.randint(0, 1))` -> 1 is heads, 0 is tails."""

    def __init__(self, values):
        super().__init__(0)
        self._values = list(values)

    def randint(self, a, b):
        return self._values.pop(0) if self._values else 0


HEADS, TAILS = 1, 0


def fresh_state(db, rng=None):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=rng or random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None, kind="attack"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=st.rng, effect_kind=kind)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # ----------------------------------------------------------------- #
    # 0. THE PRINTS THEMSELVES.
    # ----------------------------------------------------------------- #
    pikipek = db.get("Pikipek")
    check(pikipek.hp == 70 and pikipek.is_basic and "Colorless" in pikipek.types
          and pikipek.regulation_mark == "J",
          f"Pikipek (me5 66) should be a 70 HP Basic Colorless, mark J; got "
          f"{pikipek.hp}/{pikipek.types}/{pikipek.regulation_mark}")
    check([a.name for a in pikipek.attacks] == ["Double Stab"]
          and pikipek.attacks[0].cost == ("Colorless",),
          f"Pikipek's only attack is [C] Double Stab, got {pikipek.attacks}")

    trumbeak = db.get("Trumbeak")
    check(trumbeak.hp == 90 and trumbeak.evolves_from == "Pikipek"
          and "Stage 1" in trumbeak.subtypes,
          f"Trumbeak (me5 67) should be a 90 HP Stage 1 from Pikipek, got "
          f"{trumbeak.hp}/{trumbeak.evolves_from}")
    check(trumbeak.attacks[0].damage == 30 and trumbeak.attacks[0].cost == ("Colorless",),
          f"Trumbeak's Fly is [C] 30, got {trumbeak.attacks[0]}")

    toucannon = db.get("Toucannon")
    check(toucannon.hp == 150 and toucannon.evolves_from == "Trumbeak"
          and "Stage 2" in toucannon.subtypes and toucannon.retreat_cost == 2,
          f"Toucannon (me5 68) should be a 150 HP Stage 2 from Trumbeak, retreat 2; got "
          f"{toucannon.hp}/{toucannon.evolves_from}/{toucannon.retreat_cost}")
    check(any(ab.name == "Aerial Draw" for ab in toucannon.abilities),
          "Toucannon must have the Aerial Draw Ability")
    check(toucannon.attacks[0].name == "Feather Rondo"
          and toucannon.attacks[0].cost == ("Colorless",)
          and toucannon.attacks[0].damage_suffix == "+",
          f"Feather Rondo is [C] 60+ (variable), got {toucannon.attacks[0]}")

    # PRINT COLLISION: the suffixed SCR print vs the pool's bare TEF print.
    hoot_scr = db.get("Hoothoot (SCR)")
    check(hoot_scr.hp == 70 and hoot_scr.regulation_mark == "H"
          and [a.name for a in hoot_scr.attacks] == ["Triple Stab"]
          and hoot_scr.attacks[0].cost == ("Colorless",),
          f"Hoothoot (SCR) (sv7-114) is a 70 HP Basic with [C] Triple Stab, got "
          f"{hoot_scr.hp}/{hoot_scr.attacks}")
    hoot_bare = db.get("Hoothoot")
    check(hoot_bare.hp == 70 and [a.name for a in hoot_bare.attacks] == ["Silent Wing"]
          and hoot_bare.attacks[0].cost == ("Colorless", "Colorless")
          and hoot_bare.attacks[0].damage == 20,
          "the pool's OLD bare 'Hoothoot' (sv5-126 TEF, [C][C] Silent Wing 20) must be "
          f"left exactly as it was, got {hoot_bare.attacks}")
    check(fx.get_attack_effect("Hoothoot", "Triple Stab") is None
          and fx.get_attack_effect("Hoothoot (SCR)", "Silent Wing") is None,
          "the two Hoothoot prints must not share effects — each is keyed on its own "
          "exact pool name")
    check(fx.print_base_name("Hoothoot (SCR)") == "Hoothoot",
          "print_base_name must strip the (SCR) suffix so Noctowl can still evolve onto it")

    noctowl = db.get("Noctowl")
    check(noctowl.evolves_from == "Hoothoot" and noctowl.hp == 100,
          f"Noctowl should be a 100 HP Stage 1 from Hoothoot, got {noctowl.hp}")
    check(any(ab.name == "Jewel Seeker" for ab in noctowl.abilities),
          "Noctowl must have the Jewel Seeker Ability")

    iron_leaves = db.get("Iron Leaves ex")
    check(iron_leaves.hp == 220 and iron_leaves.is_basic
          and any(ab.name == "Rapid Vernier" for ab in iron_leaves.abilities),
          f"Iron Leaves ex should be a 220 HP Basic with Rapid Vernier, got "
          f"{iron_leaves.hp}/{[a.name for a in iron_leaves.abilities]}")
    prism = next(a for a in iron_leaves.attacks if a.name == "Prism Edge")
    check(prism.cost == ("Grass", "Grass", "Colorless") and prism.damage == 180,
          f"Prism Edge is [G][G][C] 180, got {prism}")

    # ----------------------------------------------------------------- #
    # 1. Pikipek — Double Stab 10×: "Flip 2 coins. This attack does 10 damage
    #    for each heads." OWNS its damage (variable), so the engine applies 0 base.
    # ----------------------------------------------------------------- #
    check(fx.get_attack_effect("Pikipek", "Double Stab") is fx._double_stab,
          "Double Stab must be registered")

    for heads_flips, expect in ((( HEADS, HEADS), 20), ((HEADS, TAILS), 10),
                                ((TAILS, TAILS), 0)):
        st, a, b = fresh_state(db, ScriptedRNG(list(heads_flips)))
        src = InPlayPokemon(card=pikipek)
        a.active = src
        b.active = InPlayPokemon(card=db.get("Dudunsparce"))   # Colorless, no W/R vs C
        fx._double_stab(ctx_for(st, a, b, source=src))
        check(b.active.damage == expect,
              f"Double Stab with flips {heads_flips} should do {expect}, got "
              f"{b.active.damage}")

    # 1b. NO DOUBLE-COUNT, end-to-end: "10×" must make the engine apply 0 base, so
    #     2 heads is exactly 20 — not the printed 10 plus the effect's 20.
    st, a, b = fresh_state(db, ScriptedRNG([HEADS, HEADS]))
    st.active_index = 0
    a.active = InPlayPokemon(card=pikipek, energy=[db.get("Basic Grass Energy")])
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    game.apply_action(st, Action("attack", attack_index=0))
    check(b.active is not None and b.active.damage == 20,
          f"through the real attack action Double Stab on 2 heads must deal exactly 20, "
          f"got {b.active.damage if b.active else 'KO'}")

    # ----------------------------------------------------------------- #
    # 2. Hoothoot (SCR) — Triple Stab 10×: "Flip 3 coins... 10 damage for each heads."
    # ----------------------------------------------------------------- #
    check(fx.get_attack_effect("Hoothoot (SCR)", "Triple Stab") is fx._triple_stab,
          "Triple Stab must be registered under the SUFFIXED print name")
    for flips, expect in (((HEADS, HEADS, HEADS), 30), ((HEADS, TAILS, HEADS), 20),
                          ((TAILS, TAILS, TAILS), 0)):
        st, a, b = fresh_state(db, ScriptedRNG(list(flips)))
        src = InPlayPokemon(card=hoot_scr)
        a.active = src
        b.active = InPlayPokemon(card=db.get("Dudunsparce"))
        fx._triple_stab(ctx_for(st, a, b, source=src))
        check(b.active.damage == expect,
              f"Triple Stab with flips {flips} should do {expect}, got {b.active.damage}")

    # ----------------------------------------------------------------- #
    # 3. Trumbeak — Fly: "Flip a coin. If tails, this attack does nothing. If heads,
    #    during your opponent's next turn, prevent all damage from and effects of
    #    attacks done to this Pokémon."
    # ----------------------------------------------------------------- #
    check(("Trumbeak", "Fly") in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Fly must own its damage — otherwise a TAILS would still land the printed 30")

    # 3a. HEADS -> 30 damage AND the shield.
    st, a, b = fresh_state(db, ScriptedRNG([HEADS]))
    src = InPlayPokemon(card=trumbeak)
    a.active = src
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    fx._fly(ctx_for(st, a, b, source=src))
    check(b.active.damage == 30, f"Fly heads should do 30, got {b.active.damage}")
    check(src.shielded is True, "Fly heads must shield the attacker for the opponent's turn")

    # 3b. TAILS -> literally nothing: no damage, no shield.
    st, a, b = fresh_state(db, ScriptedRNG([TAILS]))
    src = InPlayPokemon(card=trumbeak)
    a.active = src
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    fx._fly(ctx_for(st, a, b, source=src))
    check(b.active.damage == 0, f"Fly tails must do NOTHING, got {b.active.damage} damage")
    check(src.shielded is False, "Fly tails must not shield the attacker")

    # 3b-ii. the same through the REAL attack action — this is what ATTACK_EFFECT_OWNS_
    #        DAMAGE buys: without it the engine would pre-apply the printed 30 and a
    #        tails would still hit for 30.
    st, a, b = fresh_state(db, ScriptedRNG([TAILS]))
    st.active_index = 0
    a.active = InPlayPokemon(card=trumbeak, energy=[db.get("Basic Grass Energy")])
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    game.apply_action(st, Action("attack", attack_index=0))
    check(b.active is not None and b.active.damage == 0,
          f"through the real attack action a TAILS Fly must deal 0, got "
          f"{b.active.damage if b.active else 'KO'}")

    # 3c. the shield really blocks an opposing attack's damage (the engine chokepoint).
    st, a, b = fresh_state(db)
    shielded = InPlayPokemon(card=trumbeak)
    shielded.shielded = True
    a.active = shielded
    attacker = InPlayPokemon(card=db.get("Dudunsparce"))
    b.active = attacker
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=attacker), shielded, 90,
                                   owner=a, source=attacker)
    check(dealt == 0 and shielded.damage == 0,
          f"a shielded Trumbeak must take 0 attack damage, got {dealt}/{shielded.damage}")

    # ----------------------------------------------------------------- #
    # 4. Toucannon — Feather Rondo 60+: "20 more damage for each Benched Pokémon
    #    (both yours and your opponent's)." BOTH benches; neither Active counts.
    # ----------------------------------------------------------------- #
    check(fx.get_attack_effect("Toucannon", "Feather Rondo") is fx._feather_rondo,
          "Feather Rondo must be registered")
    for mine, theirs in ((0, 0), (3, 2), (5, 5)):
        st, a, b = fresh_state(db)
        src = InPlayPokemon(card=toucannon)
        a.active = src
        a.bench = [InPlayPokemon(card=pikipek) for _ in range(mine)]
        b.active = InPlayPokemon(card=db.get("Dudunsparce"))
        b.bench = [InPlayPokemon(card=pikipek) for _ in range(theirs)]
        fx._feather_rondo(ctx_for(st, a, b, source=src))
        expect = 60 + 20 * (mine + theirs)
        check(b.active.damage == expect,
              f"Feather Rondo with {mine}+{theirs} benched should do {expect}, got "
              f"{b.active.damage}")

    # 4b. NO DOUBLE-COUNT: the engine must apply 0 base for a "+" attack, so the whole
    #     hit comes from the effect once. Proved end-to-end through the real attack
    #     action: 1 bench each side -> 60 + 20*2 = 100, NOT 160 (60 printed + 100).
    st, a, b = fresh_state(db)
    check(toucannon.attacks[0].damage_suffix == "+",
          "Feather Rondo must be a '+' variable-damage attack so the engine applies 0 base")
    src = InPlayPokemon(card=toucannon, energy=[db.get("Basic Grass Energy")])
    a.active = src
    a.bench = [InPlayPokemon(card=pikipek)]
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    b.bench = [InPlayPokemon(card=pikipek)]
    st.active_index = 0
    game.apply_action(st, Action("attack", attack_index=0))
    check(b.active is not None and b.active.damage == 100,
          f"through the real attack action Feather Rondo must deal exactly 100 "
          f"(60 + 20×2 benched), not the printed 60 plus the effect; got "
          f"{b.active.damage if b.active else 'KO'}")

    # ----------------------------------------------------------------- #
    # 5. Toucannon — Aerial Draw: "Once during your turn, you may use this Ability.
    #    Draw a card."
    # ----------------------------------------------------------------- #
    check(fx.get_ability_effect("Toucannon", "Aerial Draw") is fx._aerial_draw,
          "Aerial Draw must be registered as an activated Ability")
    check(not fx.is_repeatable_ability("Toucannon", "Aerial Draw"),
          "Aerial Draw is once per turn per Toucannon — it must NOT be repeatable")
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=toucannon)
    a.active = src
    a.deck = [db.get("Ultra Ball"), db.get("Rare Candy")]
    fx._aerial_draw(ctx_for(st, a, b, source=src, kind="ability"))
    check(len(a.hand) == 1 and len(a.deck) == 1,
          f"Aerial Draw should draw exactly 1, got hand={len(a.hand)} deck={len(a.deck)}")
    # NEGATIVE: an empty deck draws nothing and does not crash.
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=toucannon)
    a.active = src
    a.deck = []
    fx._aerial_draw(ctx_for(st, a, b, source=src, kind="ability"))
    check(len(a.hand) == 0, "Aerial Draw with an empty deck must draw nothing")

    # ----------------------------------------------------------------- #
    # 6. Noctowl — Jewel Seeker. Fires ONLY on evolve-from-hand, ONLY with a Tera
    #    Pokémon in play, and finds UP TO 2 Trainers.
    # ----------------------------------------------------------------- #
    check(fx.get_on_evolve_trigger("Noctowl") is fx._jewel_seeker,
          "Jewel Seeker must be wired as an ON_EVOLVE trigger, not an activated Ability")
    check(fx.get_ability_effect("Noctowl", "Jewel Seeker") is None,
          "Jewel Seeker must NOT be an activated Ability — it only fires on evolution")
    check(fx.get_on_bench_trigger("Noctowl") is None,
          "Jewel Seeker must NOT fire when Noctowl merely reaches the Bench")

    # 6a. POSITIVE: a Tera Pokémon in play -> up to 2 Trainers into hand.
    st, a, b = fresh_state(db)
    evolved = InPlayPokemon(card=noctowl)
    a.active = evolved
    a.bench = [InPlayPokemon(card=db.get("Teal Mask Ogerpon ex"))]     # Tera
    check("Tera" in db.get("Teal Mask Ogerpon ex").subtypes,
          "setup: Teal Mask Ogerpon ex must be Tera-typed")
    a.deck = [db.get("Ultra Ball"), db.get("Boss's Orders"), db.get("Basic Grass Energy")]
    fx._jewel_seeker(ctx_for(st, a, b, source=evolved, kind="ability"))
    check(len(a.hand) == 2 and all(c.is_trainer for c in a.hand),
          f"Jewel Seeker with a Tera in play should fetch 2 Trainers, got "
          f"{[c.name for c in a.hand]}")
    check(all(c.is_basic_energy for c in a.deck),
          "Jewel Seeker must only take Trainer cards, leaving the Energy in the deck")

    # 6b. NEGATIVE: NO Tera Pokémon in play -> nothing happens at all.
    st, a, b = fresh_state(db)
    evolved = InPlayPokemon(card=noctowl)
    a.active = evolved
    a.bench = [InPlayPokemon(card=db.get("Latias ex"))]                # ex, but NOT Tera
    check("Tera" not in db.get("Latias ex").subtypes,
          "setup: Latias ex must NOT be Tera-typed (that is the point of this case)")
    a.deck = [db.get("Ultra Ball"), db.get("Boss's Orders")]
    fx._jewel_seeker(ctx_for(st, a, b, source=evolved, kind="ability"))
    check(len(a.hand) == 0 and len(a.deck) == 2,
          f"Jewel Seeker with no Tera Pokémon in play must do NOTHING, got hand="
          f"{[c.name for c in a.hand]}")

    # 6c. "up to 2": one Trainer in the deck finds exactly 1.
    st, a, b = fresh_state(db)
    evolved = InPlayPokemon(card=noctowl)
    a.active = evolved
    a.bench = [InPlayPokemon(card=db.get("Teal Mask Ogerpon ex"))]
    a.deck = [db.get("Ultra Ball"), db.get("Basic Grass Energy")]
    fx._jewel_seeker(ctx_for(st, a, b, source=evolved, kind="ability"))
    check(len(a.hand) == 1 and a.hand[0].name == "Ultra Ball",
          f"'up to 2' must find 1 when only 1 Trainer is left, got "
          f"{[c.name for c in a.hand]}")

    # 6d. INTEGRATION: the trigger really fires through the engine's evolve action.
    st, a, b = fresh_state(db)
    base = InPlayPokemon(card=hoot_scr)
    a.active = base
    a.bench = [InPlayPokemon(card=db.get("Teal Mask Ogerpon ex"))]
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    a.hand = [noctowl]
    a.deck = [db.get("Ultra Ball"), db.get("Boss's Orders")]
    a.turns_taken = 3
    st.active_index = 0
    game.apply_action(st, Action("evolve", hand_index=0, target_index=-1))
    check(a.active.card.name == "Noctowl",
          f"the Hoothoot (SCR) must have evolved into Noctowl, got {a.active.card.name}")
    check(len(a.hand) == 2 and all(c.is_trainer for c in a.hand),
          f"Jewel Seeker must fire through the real evolve action, got hand="
          f"{[c.name for c in a.hand]}")

    # ----------------------------------------------------------------- #
    # 7. Iron Leaves ex — Rapid Vernier (on-bench) + Prism Edge.
    # ----------------------------------------------------------------- #
    check(fx.get_on_bench_trigger("Iron Leaves ex") is fx._rapid_vernier,
          "Rapid Vernier must be wired as an ON_BENCH trigger")
    check(("Iron Leaves ex", "Rapid Vernier") in fx.PASSIVE_ABILITIES,
          "Rapid Vernier must be recorded in PASSIVE_ABILITIES so coverage counts it")

    grass = db.get("Basic Grass Energy")

    # 7a. POSITIVE: the other Pokémon hold enough Energy to pay [G][G][C] -> switch
    #     happens and exactly the needed Energy moves.
    st, a, b = fresh_state(db)
    old_active = InPlayPokemon(card=db.get("Teal Mask Ogerpon ex"),
                               energy=[grass, grass, grass, grass])
    a.active = old_active
    newmon = InPlayPokemon(card=iron_leaves, played_this_turn=True)
    a.bench = [newmon]
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    fx._rapid_vernier(ctx_for(st, a, b, source=newmon, kind="ability"))
    check(a.active is newmon, "Rapid Vernier should have switched Iron Leaves ex Active")
    check(a.bench and a.bench[0] is old_active,
          "the outgoing Active must land on the Bench slot Iron Leaves ex vacated")
    check(game.can_pay_cost(newmon, prism.cost),
          f"Iron Leaves ex must now be able to pay [G][G][C], has "
          f"{newmon.provided_types()}")
    check(len(newmon.energy) == 3 and len(old_active.energy) == 1,
          f"exactly the 3 Energy needed should move, got {len(newmon.energy)} moved / "
          f"{len(old_active.energy)} left behind")

    # 7b. NEGATIVE: not enough Energy on the other Pokémon -> the switch is DECLINED
    #     (the whole point: never drag a healthy Active off for nothing).
    st, a, b = fresh_state(db)
    old_active = InPlayPokemon(card=db.get("Teal Mask Ogerpon ex"), energy=[grass])
    a.active = old_active
    newmon = InPlayPokemon(card=iron_leaves, played_this_turn=True)
    a.bench = [newmon]
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    fx._rapid_vernier(ctx_for(st, a, b, source=newmon, kind="ability"))
    check(a.active is old_active and a.bench[0] is newmon,
          "with too little Energy to pay Prism Edge, Rapid Vernier must decline the switch")
    check(len(old_active.energy) == 1 and not newmon.energy,
          "a declined Rapid Vernier must not move any Energy")

    # 7c. NEGATIVE: the wrong TYPE of Energy cannot pay [G][G][C], so no switch.
    st, a, b = fresh_state(db)
    fire = db.get("Basic Fire Energy")
    old_active = InPlayPokemon(card=db.get("Teal Mask Ogerpon ex"),
                               energy=[fire, fire, fire])
    a.active = old_active
    newmon = InPlayPokemon(card=iron_leaves, played_this_turn=True)
    a.bench = [newmon]
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    fx._rapid_vernier(ctx_for(st, a, b, source=newmon, kind="ability"))
    check(a.active is old_active,
          "3 Fire Energy cannot pay [G][G][C] — Rapid Vernier must decline")

    # 7d. INTEGRATION: benching Iron Leaves ex through the real engine action fires it.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Teal Mask Ogerpon ex"),
                             energy=[grass, grass, grass])
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    a.hand = [iron_leaves]
    st.active_index = 0
    game.apply_action(st, Action("play_basic", hand_index=0))
    check(a.active.card.name == "Iron Leaves ex",
          f"Rapid Vernier must fire through the real play_basic action, active is "
          f"{a.active.card.name}")

    # 7e. Prism Edge: 180 is FLAT (engine-applied); the effect is only the self-lock.
    check(fx.get_attack_effect("Iron Leaves ex", "Prism Edge") is fx._prism_edge,
          "Prism Edge must be registered")
    check(("Iron Leaves ex", "Prism Edge") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Prism Edge's 180 is flat printed damage — the engine applies it, the effect "
          "must NOT also apply it")
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=iron_leaves)
    a.active = src
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    fx._prism_edge(ctx_for(st, a, b, source=src))
    check(src.pending_cannot_attack is True,
          "Prism Edge must set the 'can't attack next turn' lock")
    check(b.active.damage == 0,
          "the Prism Edge EFFECT must deal no damage of its own (the engine owns the 180)")

    # ----------------------------------------------------------------- #
    # 8. Silent Wing (the pool's BARE Hoothoot, sv5-126) — registered as a
    #    documented no-op. It must not change anything except the log.
    # ----------------------------------------------------------------- #
    check(fx.get_attack_effect("Hoothoot", "Silent Wing") is fx._silent_wing,
          "Silent Wing must be registered (as a documented no-op)")
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=hoot_bare)
    a.active = src
    b.active = InPlayPokemon(card=db.get("Dudunsparce"))
    b.hand = [db.get("Ultra Ball"), db.get("Rare Candy")]
    before = (list(b.hand), len(a.hand), b.active.damage)
    fx._silent_wing(ctx_for(st, a, b, source=src))
    check((list(b.hand), len(a.hand), b.active.damage) == before,
          "Silent Wing's reveal clause is a NO-OP: it must not move or change a card")
    check(any("Silent Wing" in line for line in st.log),
          "the Silent Wing no-op must still be logged so it is visible, not silent")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_toucannon_line.py: all checks passed — every card matches its printed "
          "text, both Hoothoot prints stay distinct, and the negative cases hold")


if __name__ == "__main__":
    main()
