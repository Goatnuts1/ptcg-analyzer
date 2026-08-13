#!/usr/bin/env python3
"""
test_bloodmoon.py — Bloodmoon Ursaluna ex (sv6-141).

Exact card text (data/standard_pool.json, Bulbapedia-verified per the implementer's
report):
  Ability "Seasoned Skill": "Blood Moon used by this Pokémon costs [Colorless] less
      for each Prize card your opponent has taken."
  Attack "Blood Moon" [C][C][C][C][C] 240: "During your next turn, this Pokémon
      can't attack."

Covers:
  - card shape matches the pool exactly (HP, types, weakness, cost, damage, text)
  - Seasoned Skill's Colorless discount scales with the OPPONENT's prizes taken,
    clamped at 0, and does not leak onto other cards/attacks
  - ability suppression (Team Rocket's Watchtower; Ursaluna is Colorless-typed)
    disables the discount, restoring the full 5-cost
  - the discount is wired all the way through game.legal_actions (not just the
    pure fx.effective_cost helper)
  - Blood Moon deals exactly 240 (once — not double-applied) and sets
    pending_cannot_attack, which the engine promotes to a real one-turn
    can't-attack lock on the attacker's own next turn and then clears
  - negative control: Crustle's "Mysterious Rock Inn" wall (prevents damage from
    an opponent's Pokémon ex) DOES block Blood Moon (Ursaluna ex is exactly that
    ex attacker) but does NOT block an otherwise-identical hit from a non-ex
    attacker — confirms the wall chokepoint's specificity, not just its presence

Run from project root:  python3 tests/test_bloodmoon.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5      # not turn 1, so the "starting player can't attack" rule is moot
    st.active_index = 0
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source,
                            db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    URSALUNA = db.get("Bloodmoon Ursaluna ex")
    DREEPY = db.get("Dreepy")                 # Dragon, Basic (no 'ex') — non-matching attacker
    CRUSTLE = db.get("Crustle")               # Mysterious Rock Inn wall vs opponent's ex
    PSY = db.get("Basic Psychic Energy")

    check(URSALUNA is not None, "Bloodmoon Ursaluna ex should be in the pool")
    check(CRUSTLE is not None, "Crustle should be in the pool")

    atk = next(a for a in URSALUNA.attacks if a.name == "Blood Moon")
    ability = next(ab for ab in URSALUNA.abilities if ab.name == "Seasoned Skill")

    # ----------------------------------------------------------------- #
    # 1. Card shape matches the pool exactly.
    # ----------------------------------------------------------------- #
    check(URSALUNA.hp == 260, f"Bloodmoon Ursaluna ex should be 260 HP (got {URSALUNA.hp})")
    check("ex" in URSALUNA.subtypes and "Basic" in URSALUNA.subtypes,
          f"should be a Basic ex (got {URSALUNA.subtypes})")
    check(URSALUNA.types == ("Colorless",),
          f"should be Colorless-typed (got {URSALUNA.types}) — this is what makes "
          f"Team Rocket's Watchtower able to suppress its Ability below")
    check(URSALUNA.weaknesses == (("Fighting", "×2"),),
          f"weakness should be Fighting ×2 (got {URSALUNA.weaknesses})")
    check(URSALUNA.retreat_cost == 3, f"retreat cost should be 3 (got {URSALUNA.retreat_cost})")

    check(atk.cost == ("Colorless",) * 5, f"Blood Moon printed cost should be [C]x5 (got {atk.cost})")
    check(atk.damage == 240, f"Blood Moon printed damage should be 240 (got {atk.damage})")
    check(atk.damage_suffix == "", f"Blood Moon is a fixed-damage attack (got suffix {atk.damage_suffix!r})")
    check(atk.text == "During your next turn, this Pokémon can't attack.",
          f"Blood Moon text mismatch: {atk.text!r}")
    check(ability.text == ("Blood Moon used by this Pokémon costs Colorless less for each "
                           "Prize card your opponent has taken."),
          f"Seasoned Skill text mismatch: {ability.text!r}")

    # ----------------------------------------------------------------- #
    # 2. Seasoned Skill: Colorless discount scales with the OPPONENT's prizes
    #    taken (= 6 - len(opp.prizes)), clamped at 0, never touching typed symbols
    #    (moot here since Blood Moon is all-Colorless, but the clamp matters).
    # ----------------------------------------------------------------- #
    st, a, b = fresh(db)
    src = InPlayPokemon(card=URSALUNA)
    a.active = src

    # 0 prizes taken (opponent still has all 6 remaining) -> full cost, no discount.
    b.prizes = ["placeholder"] * 6
    cost0 = fx.effective_cost(st, src, atk)
    check(cost0 == ("Colorless",) * 5,
          f"0 prizes taken: full 5-cost expected (got {cost0})")

    # 1 prize taken -> discount 1.
    b.prizes = ["placeholder"] * 5
    cost1 = fx.effective_cost(st, src, atk)
    check(cost1 == ("Colorless",) * 4,
          f"1 prize taken: cost should drop to 4 (got {cost1})")

    # 3 prizes taken -> discount 3.
    b.prizes = ["placeholder"] * 3
    cost3 = fx.effective_cost(st, src, atk)
    check(cost3 == ("Colorless",) * 2,
          f"3 prizes taken: cost should drop to 2 (got {cost3})")

    # 5 prizes taken (1 remaining) -> discount 5 -> cost floors at 0.
    b.prizes = ["placeholder"] * 1
    cost5 = fx.effective_cost(st, src, atk)
    check(cost5 == (),
          f"5 prizes taken: cost should floor at 0 symbols (got {cost5})")

    # Pathological over-discount (all 6 prizes "taken", opp.prizes empty) must still
    # clamp at 0, never go negative / produce a malformed tuple.
    b.prizes = []
    cost6 = fx.effective_cost(st, src, atk)
    check(cost6 == (),
          f"over-discount must clamp at 0, not go negative (got {cost6})")

    # The modifier must NOT leak onto an unrelated card/attack pair — Dreepy's own
    # attack cost is untouched regardless of the opponent's prizes.
    dreepy_atk = DREEPY.attacks[0]
    other_mon = InPlayPokemon(card=DREEPY)
    a.active = other_mon
    b.prizes = ["placeholder"] * 1     # would be a big discount if it applied
    unaffected = fx.effective_cost(st, other_mon, dreepy_atk)
    check(unaffected == dreepy_atk.cost,
          f"Seasoned Skill must not affect a different card/attack (got {unaffected}, "
          f"printed {dreepy_atk.cost})")
    a.active = src   # restore for the tests below

    # ----------------------------------------------------------------- #
    # 3. Ability suppression (Team Rocket's Watchtower) disables the discount.
    #    TRW only suppresses Colorless-typed Pokémon's Abilities — Ursaluna IS
    #    Colorless-typed, so this is a real, in-scope interaction, not a no-op.
    # ----------------------------------------------------------------- #
    st, a, b = fresh(db)
    src = InPlayPokemon(card=URSALUNA)
    a.active = src
    b.prizes = ["placeholder"] * 3    # would discount to 2 if the Ability were live

    check(not fx.ability_suppressed(st, src),
          "sanity: no Ability suppression with no Stadium in play")
    cost_normal = fx.effective_cost(st, src, atk)
    check(cost_normal == ("Colorless",) * 2,
          f"control: discount should apply with no Stadium up (got {cost_normal})")

    st.stadium = db.get("Team Rocket's Watchtower")
    st.stadium_owner = 1
    check(fx.ability_suppressed(st, src),
          "Team Rocket's Watchtower should suppress a Colorless-typed Pokémon's Ability")
    cost_suppressed = fx.effective_cost(st, src, atk)
    check(cost_suppressed == ("Colorless",) * 5,
          f"suppressed: Seasoned Skill disabled, full 5-cost restored (got {cost_suppressed})")

    # ----------------------------------------------------------------- #
    # 4. The discount is wired through game.legal_actions, not just the pure
    #    fx.effective_cost helper (game.py:226 consults it before can_pay_cost).
    # ----------------------------------------------------------------- #
    st, a, b = fresh(db)
    src = InPlayPokemon(card=URSALUNA, energy=[PSY, PSY])   # only 2 energy attached
    a.active = src
    b.active = InPlayPokemon(card=DREEPY)

    b.prizes = ["placeholder"] * 6    # 0 taken -> cost stays 5 -> unaffordable with 2 energy
    acts = game.legal_actions(st)
    check(not any(x.kind == "attack" for x in acts),
          "0 prizes taken: Blood Moon should be unaffordable with only 2 energy")

    b.prizes = ["placeholder"] * 3    # 3 taken -> cost 2 -> exactly affordable
    acts = game.legal_actions(st)
    check(any(x.kind == "attack" for x in acts),
          "3 prizes taken: Blood Moon (discounted to 2) should be affordable with 2 energy")

    src.energy = []
    b.prizes = ["placeholder"] * 1    # 5 taken -> cost 0 -> affordable even with 0 energy
    acts = game.legal_actions(st)
    check(any(x.kind == "attack" for x in acts),
          "5 prizes taken: Blood Moon (discounted to 0) should be affordable with 0 energy")

    # ...but suppression restores the full cost, making it unaffordable again even
    # at 5 prizes taken with 0 energy attached.
    st.stadium = db.get("Team Rocket's Watchtower")
    st.stadium_owner = 1
    acts = game.legal_actions(st)
    check(not any(x.kind == "attack" for x in acts),
          "suppressed: full cost restored, unaffordable with 0 energy even at 5 prizes taken")

    # ----------------------------------------------------------------- #
    # 5. Blood Moon deals exactly 240 (once), and directly sets
    #    pending_cannot_attack (isolated effect call).
    # ----------------------------------------------------------------- #
    check(("Bloodmoon Ursaluna ex", "Blood Moon") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Blood Moon must rely on the engine's default base-damage application "
          "(240 applied once), not ATTACK_EFFECT_OWNS_DAMAGE — else it would double-hit")

    st, a, b = fresh(db)
    src = InPlayPokemon(card=URSALUNA)
    fx._blood_moon(ctx_for(st, a, b, source=src))
    check(src.pending_cannot_attack,
          "Blood Moon effect should set pending_cannot_attack on the attacker")

    # Full engine-level resolution: attach 5 energy, attack via apply_action, and
    # confirm the 240 lands on the defender exactly once AND the lock is armed.
    st, a, b = fresh(db)
    src = InPlayPokemon(card=URSALUNA, energy=[PSY] * 5)
    a.active = src
    defender = InPlayPokemon(card=DREEPY)
    b.active = defender
    b.prizes = ["placeholder"] * 6    # 0 discount so the printed 5-cost is exactly paid
    game.apply_action(st, game.Action("attack", attack_index=0))
    check(defender.damage == 240,
          f"Blood Moon should deal exactly 240 to a non-matching, non-weak defender "
          f"(got {defender.damage})")
    check(src.pending_cannot_attack,
          "after resolving Blood Moon, the attacker's pending_cannot_attack should be set")

    # ----------------------------------------------------------------- #
    # 6. The lock is a real, ONE-TURN can't-attack — engine-level via start_turn/
    #    end_turn cycling (mirrors the Latias ex Eon Blade pattern in test_more_cards.py).
    # ----------------------------------------------------------------- #
    st = game.setup_game([URSALUNA] + [PSY] * 59,
                         [DREEPY] + [PSY] * 59, seed=1, db=db)
    p0 = st.players[0]      # always Ursaluna's controller (their own deck's only Basic),
                            # regardless of who the coin flip gives the first turn to
    check(p0.active.card.name == "Bloodmoon Ursaluna ex",
          "sanity: player 0's active should come from their own (Ursaluna) deck")

    game.start_turn(st)                        # first turn overall (whoever the coin flip favors)
    while st.current is not p0:                # advance until it's actually p0's own turn
        game.end_turn(st); game.start_turn(st)

    p0.active.energy = [PSY] * 5              # can pay Blood Moon's full 5-cost
    p0.active.pending_cannot_attack = True     # simulate having used Blood Moon THIS turn
    check(not p0.active.cannot_attack, "lock not yet active on the turn it was set")

    game.end_turn(st); game.start_turn(st)    # opponent's turn — p0's lock untouched
    check(not p0.active.cannot_attack,
          "lock still not active during the opponent's intervening turn")

    game.end_turn(st); game.start_turn(st)    # back to p0 — lock now promoted to active
    check(p0.active.cannot_attack, "lock should be active on the owner's own next turn")
    acts = game.legal_actions(st)
    check(not any(x.kind == "attack" for x in acts),
          "no attack should be offered while cannot_attack is set, despite affordable energy")

    game.end_turn(st); game.start_turn(st)    # opponent's turn again
    game.end_turn(st); game.start_turn(st)    # back to p0 a second time — lock should be gone
    check(not p0.active.cannot_attack,
          "the can't-attack lock should last exactly one turn, then clear")
    acts = game.legal_actions(st)
    check(any(x.kind == "attack" for x in acts),
          "attack should be offered again once the one-turn lock has cleared")

    # ----------------------------------------------------------------- #
    # 7. Negative control: Crustle's Mysterious Rock Inn ("Prevent all damage
    #    done to this Pokémon by attacks from your opponent's Pokémon ex.") DOES
    #    block Blood Moon (Ursaluna ex is exactly an opponent's Pokémon ex) but
    #    must NOT block an otherwise-identical hit from a non-ex attacker.
    # ----------------------------------------------------------------- #
    st, a, b = fresh(db)
    ursaluna_src = InPlayPokemon(card=URSALUNA)
    a.active = ursaluna_src
    wall = InPlayPokemon(card=CRUSTLE)
    b.active = wall
    ctx = ctx_for(st, me=a, opp=b, source=ursaluna_src)

    dealt = fx.apply_attack_damage(ctx, wall, 240, owner=b, source=ursaluna_src)
    check(dealt == 0 and wall.damage == 0,
          f"Mysterious Rock Inn should prevent Blood Moon's 240 (an opponent's ex "
          f"attack) entirely (dealt={dealt}, damage={wall.damage})")

    # Same wall, same target, non-matching (non-ex) attacker -> damage goes through.
    st2, a2, b2 = fresh(db)
    dreepy_src = InPlayPokemon(card=DREEPY)
    a2.active = dreepy_src
    wall2 = InPlayPokemon(card=CRUSTLE)
    b2.active = wall2
    ctx2 = ctx_for(st2, me=a2, opp=b2, source=dreepy_src)
    check("ex" not in DREEPY.subtypes, "test assumes Dreepy is a plain (non-ex) attacker")

    dealt2 = fx.apply_attack_damage(ctx2, wall2, 240, owner=b2, source=dreepy_src)
    check(dealt2 == 240 and wall2.damage == 240,
          f"Mysterious Rock Inn must NOT block a non-ex attacker's damage "
          f"(dealt={dealt2}, damage={wall2.damage})")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — Bloodmoon Ursaluna ex: Seasoned Skill discount (+clamp, +suppression, "
          "+legal_actions wiring), Blood Moon 240 dmg (once) + one-turn can't-attack lock, "
          "and the Mysterious Rock Inn ex-only wall control all match card text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
