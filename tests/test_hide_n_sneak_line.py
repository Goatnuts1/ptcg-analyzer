#!/usr/bin/env python3
"""
test_hide_n_sneak_line.py — the Pitch Black "Hide 'n' Sneak" line, asserted
against the exact printed text of each card.

CARDS UNDER TEST (all NEW prints; the pool's same-named entries are OLDER, different
cards and must keep falling through to vanilla — that is asserted here too):

  Shuppet (PBL 33)      Ability "Hide 'n' Sneak": "Prevent all effects of your
                        opponent's Pokémon's attacks and Abilities done to this Pokémon.
                        (Damage is not an effect.)"
                        [P] Hang Down 10 (no text).
  Banette (PBL 34)      Same Ability. [P] Puppet Pull 80: "You may search your deck for a
                        card and put it into your hand. Then, shuffle your deck."
  Dhelmise (PBL 39)     [P] Vengeful Anchor 30+: "If you have 4 or more Pokémon that have
                        the Hide 'n' Sneak Ability in your discard pile, this attack does
                        140 more damage."
  Poltchageist (PBL 5)  Same Ability. [C] Furtive Drop: "Place 1 damage counter on your
                        opponent's Active Pokémon."
  Sinistcha (PBL 6)     Same Ability. [C] Matcha Spin: "If you have 6 or more Pokémon that
                        have the Hide 'n' Sneak Ability in your discard pile, place 4
                        damage counters on each of your opponent's Pokémon."
  Gwynn (PBL 78)        Supporter: "Discard up to 2 Pokémon that don't have a Rule Box
                        from your hand, and draw 3 cards for each card you discarded in
                        this way."
  Flutter Mane          [C][C][C] Hex Hurl 90: "Put 2 damage counters on your opponent's
                        Benched Pokémon in any way you like."

Run: python3 tests/test_hide_n_sneak_line.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
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
    # 0. THE PRINTS THEMSELVES — the new entries carry the PBL text, and the
    #    pool's older same-named entries are untouched and still vanilla.
    # ----------------------------------------------------------------- #
    shuppet = db.get("Shuppet (PBL)")
    check(shuppet.hp == 50 and "Psychic" in shuppet.types and shuppet.is_basic,
          f"Shuppet (PBL) should be a 50 HP Basic Psychic, got {shuppet.hp}/{shuppet.types}")
    check(any(ab.name == "Hide 'n' Sneak" for ab in shuppet.abilities),
          "Shuppet (PBL) must have the Hide 'n' Sneak Ability")
    check([a.name for a in shuppet.attacks] == ["Hang Down"]
          and shuppet.attacks[0].damage == 10 and shuppet.attacks[0].cost == ("Psychic",),
          f"Shuppet (PBL)'s only attack is [P] Hang Down 10, got {shuppet.attacks}")

    old_shuppet = db.get("Shuppet")
    check(old_shuppet.hp == 60 and not old_shuppet.abilities
          and [a.name for a in old_shuppet.attacks] == ["Spooky Shot"],
          "the pool's OLD bare 'Shuppet' (JTG, 60 HP, Spooky Shot, no Ability) must be "
          "left exactly as it was")
    check(fx.get_attack_effect("Shuppet", "Spooky Shot") is None
          and fx.get_ability_effect("Shuppet", "Hide 'n' Sneak") is None,
          "the old bare 'Shuppet' print must stay vanilla — no effect may leak onto it")

    banette = db.get("Banette (PBL)")
    check(banette.hp == 80 and banette.evolves_from == "Shuppet",
          f"Banette (PBL) should be an 80 HP Stage 1 from Shuppet, got "
          f"{banette.hp}/{banette.evolves_from}")
    check([a.name for a in banette.attacks] == ["Puppet Pull"],
          f"Banette (PBL)'s ONLY attack is Puppet Pull — 'Cursed Words' belongs to the "
          f"old print, got {[a.name for a in banette.attacks]}")

    dhelmise = db.get("Dhelmise (PBL)")
    check(dhelmise.hp == 140 and "Psychic" in dhelmise.types,
          f"Dhelmise (PBL) is a 140 HP PSYCHIC Basic (the pool's old print is Grass/130), "
          f"got {dhelmise.hp}/{dhelmise.types}")
    check(dhelmise.attacks[0].damage == 30 and dhelmise.attacks[0].damage_suffix == "+",
          f"Vengeful Anchor must be printed '30+', got "
          f"{dhelmise.attacks[0].damage}{dhelmise.attacks[0].damage_suffix!r}")
    check("Grass" in db.get("Dhelmise").types,
          "the pool's old bare 'Dhelmise' (TEF, Grass) must be left untouched")

    sinistcha = db.get("Sinistcha (PBL)")
    check([a.name for a in sinistcha.attacks] == ["Matcha Spin"],
          f"Sinistcha (PBL)'s only attack is Matcha Spin — 'Cursed Drop'/'Spill the Tea' "
          f"belong to the old print, got {[a.name for a in sinistcha.attacks]}")
    check(any(ab.name == "Storehouse Hideaway" for ab in db.get("Poltchageist").abilities),
          "the pool's old bare 'Poltchageist' must keep its bench-only Storehouse Hideaway")

    # ----------------------------------------------------------------- #
    # 1. HIDE 'N' SNEAK — "Prevent all effects of your opponent's Pokémon's
    #    attacks and Abilities done to this Pokémon. (Damage is not an effect.)"
    # ----------------------------------------------------------------- #
    # 1a. POSITIVE: an opposing ATTACK's damage counters are prevented, on the Bench...
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Shuppet (PBL)"))
    a.active = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    a.bench = [holder]
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    ctx = ctx_for(st, b, a, source=attacker, kind="attack")
    placed = fx.place_counters(ctx, holder, 6, owner=a)
    check(placed == 0 and holder.damage == 0,
          f"Hide 'n' Sneak must prevent an opposing attack's damage counters on the "
          f"BENCH, got {placed} counter(s)/{holder.damage} damage")

    # 1b. ...and in the Active Spot too (it is NOT the old bench-only Storehouse
    #     Hideaway — the Ability has no location clause at all).
    st, a, b = fresh_state(db)
    active_holder = InPlayPokemon(card=db.get("Sinistcha (PBL)"))
    a.active = active_holder
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    ctx = ctx_for(st, b, a, source=attacker, kind="attack")
    check(fx.place_counters(ctx, active_holder, 3, owner=a) == 0,
          "Hide 'n' Sneak is not bench-restricted — it must protect the Active too")

    # 1c. POSITIVE: it also prevents the effects of an opposing ABILITY (this is where
    #     it is strictly stronger than Rocky Fighting Energy, which covers attacks only).
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Banette (PBL)"))
    a.active = holder
    dusknoir = InPlayPokemon(card=db.get("Dusknoir"))
    b.active = dusknoir
    ctx = ctx_for(st, b, a, source=dusknoir, kind="ability")
    check(fx.place_counters(ctx, holder, 13, owner=a) == 0,
          "Hide 'n' Sneak must prevent an opposing ABILITY's damage counters too "
          "(Cursed Blast)")

    # 1d. NEGATIVE: "Damage is not an effect" — attack DAMAGE lands in full.
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Banette (PBL)"))   # 80 HP
    a.active = holder
    attacker = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = attacker
    ctx = ctx_for(st, b, a, source=attacker, kind="attack")
    dealt = fx.apply_attack_damage(ctx, holder, 60, owner=a, source=attacker)
    check(dealt == 60 and holder.damage == 60,
          f"Hide 'n' Sneak must NOT prevent attack damage — 'Damage is not an effect', "
          f"got {dealt} dealt / {holder.damage} on the holder")

    # 1e. NEGATIVE: it only stops your OPPONENT'S Pokémon. Your own effects land.
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Shuppet (PBL)"))
    friend = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    a.active = friend
    a.bench = [holder]
    ctx = ctx_for(st, a, b, source=friend, kind="attack")
    check(fx.place_counters(ctx, holder, 2, owner=a) == 2,
          "Hide 'n' Sneak names your OPPONENT's Pokémon — your own effects still land")

    # 1f. NEGATIVE: TRAINER cards are not "your opponent's Pokémon's attacks and
    #     Abilities", so a Trainer-sourced effect is NOT prevented.
    st, a, b = fresh_state(db)
    holder = InPlayPokemon(card=db.get("Shuppet (PBL)"))
    a.active = holder
    foe = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = foe
    ctx = ctx_for(st, b, a, source=foe, kind="trainer")
    check(fx.place_counters(ctx, holder, 1, owner=a) == 1,
          "Hide 'n' Sneak covers Pokémon attacks/Abilities only — a Trainer's effect "
          "must still land")

    # 1g. NEGATIVE: a Pokémon WITHOUT the Ability is unprotected (the gate really is
    #     keyed on the Ability, not on being in this deck).
    st, a, b = fresh_state(db)
    plain = InPlayPokemon(card=db.get("Dhelmise (PBL)"))   # no Ability
    a.active = plain
    foe = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = foe
    ctx = ctx_for(st, b, a, source=foe, kind="attack")
    check(fx.place_counters(ctx, plain, 2, owner=a) == 2,
          "Dhelmise (PBL) has NO Ability — it must take opposing counters normally")

    # 1h. Phantom Dive end-to-end: the spread skips the protected bencher and the
    #     unprotected one eats the counters instead.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    protected = InPlayPokemon(card=db.get("Poltchageist (PBL)"))    # 30 HP, protected
    exposed = InPlayPokemon(card=db.get("Dhelmise (PBL)"))          # 140 HP, no Ability
    a.bench = [protected, exposed]
    pult = InPlayPokemon(card=db.get("Dragapult ex"))
    b.active = pult
    ctx = ctx_for(st, b, a, source=pult, kind="attack")
    fx._phantom_dive(ctx)
    check(protected.damage == 0,
          f"Phantom Dive must not put a single counter on a Hide 'n' Sneak bencher, "
          f"got {protected.damage}")
    check(exposed.damage == 60,
          f"all 6 Phantom Dive counters should land on the unprotected bencher, got "
          f"{exposed.damage}")

    # ----------------------------------------------------------------- #
    # 2. VENGEFUL ANCHOR — 30 base, +140 at 4 or more Hide 'n' Sneak Pokémon in
    #    YOUR discard pile.
    # ----------------------------------------------------------------- #
    HNS = db.get("Shuppet (PBL)")
    NOT_HNS = db.get("Dhelmise (PBL)")     # a Pokémon in the deck WITHOUT the Ability

    def anchor(discard_cards, defender_name="Pikachu ex"):
        st, a, b = fresh_state(db)
        src = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
        a.active = src
        a.discard = list(discard_cards)
        d = InPlayPokemon(card=db.get(defender_name))
        b.active = d
        fx._vengeful_anchor(ctx_for(st, a, b, source=src))
        return d.damage

    check(anchor([]) == 30, f"0 in discard -> 30, got {anchor([])}")
    check(anchor([HNS] * 3) == 30,
          f"3 is below the '4 or more' threshold -> still 30, got {anchor([HNS] * 3)}")
    check(anchor([HNS] * 4) == 170,
          f"4 in discard -> 30+140 = 170, got {anchor([HNS] * 4)}")
    check(anchor([HNS] * 9) == 170,
          f"the bonus is flat +140, it does not scale past 4, got {anchor([HNS] * 9)}")
    # NEGATIVE: only Pokémon that HAVE the Ability count.
    check(anchor([NOT_HNS] * 6) == 30,
          f"Dhelmise has no Hide 'n' Sneak Ability, so 6 of them in the discard count "
          f"for nothing, got {anchor([NOT_HNS] * 6)}")
    # NEGATIVE: it's YOUR discard pile — the opponent's doesn't count.
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    a.active = src
    b.discard = [HNS] * 6
    d = InPlayPokemon(card=db.get("Pikachu ex"))
    b.active = d
    fx._vengeful_anchor(ctx_for(st, a, b, source=src))
    check(d.damage == 30,
          f"'in YOUR discard pile' — the opponent's discard must not power it, got {d.damage}")
    # Weakness multiplies the WHOLE 170, once — that is exactly why a "+" attack gets
    # 0 engine base and the effect lands the entire hit in one apply_attack_damage call.
    check(anchor([HNS] * 4, defender_name="Greninja ex") == 340,
          f"Greninja ex is Psychic-weak, so the full 170 must double to 340 (not "
          f"30x2+140), got {anchor([HNS] * 4, defender_name='Greninja ex')}")

    # ----------------------------------------------------------------- #
    # 3. PUPPET PULL — 80 (engine-applied flat damage) + search your deck for A card.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Banette (PBL)"))
    a.active = src
    a.deck = [db.get("Basic Psychic Energy"), db.get("Boss's Orders"), db.get("Shuppet (PBL)")]
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    fx._puppet_pull(ctx_for(st, a, b, source=src))
    check(len(a.hand) == 1 and len(a.deck) == 2,
          f"Puppet Pull searches for exactly ONE card, got hand={len(a.hand)} "
          f"deck={len(a.deck)}")
    check(b.active.damage == 0,
          "Puppet Pull's 80 is a FLAT printed number applied by the engine — the effect "
          "itself must not deal damage a second time")
    # NEGATIVE: "a card" is unrestricted, so it still works with an all-Energy deck.
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Banette (PBL)"))
    a.active = src
    a.deck = [db.get("Basic Psychic Energy")] * 3
    fx._puppet_pull(ctx_for(st, a, b, source=src))
    check(len(a.hand) == 1 and a.hand[0].is_energy,
          "Puppet Pull searches for ANY card — an Energy is a legal grab")

    # ----------------------------------------------------------------- #
    # 4. FURTIVE DROP — place 1 damage counter on the opponent's ACTIVE.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Poltchageist (PBL)"))
    a.active = src
    d = InPlayPokemon(card=db.get("Dragapult ex"))       # Psychic-weak
    bench = InPlayPokemon(card=db.get("Pikachu ex"))
    b.active, b.bench = d, [bench]
    fx._furtive_drop(ctx_for(st, a, b, source=src))
    check(d.damage == 10,
          f"Furtive Drop places exactly 1 damage counter (10 damage), got {d.damage}")
    check(bench.damage == 0, "Furtive Drop hits the ACTIVE only, never the Bench")
    # NEGATIVE: counters are NOT attack damage, so Weakness must not double them —
    # Poltchageist is Grass and the defender is Psychic-weak either way; the point is
    # that 1 counter is 10, never 20.
    check(d.damage == 10,
          f"a damage COUNTER is never multiplied by Weakness, got {d.damage}")

    # ----------------------------------------------------------------- #
    # 5. MATCHA SPIN — nothing below 6; at 6+, 4 counters on EACH opposing Pokémon.
    # ----------------------------------------------------------------- #
    def matcha(n_in_discard):
        st, a, b = fresh_state(db)
        src = InPlayPokemon(card=db.get("Sinistcha (PBL)"))
        a.active = src
        a.discard = [HNS] * n_in_discard
        act = InPlayPokemon(card=db.get("Dragapult ex"))
        b1 = InPlayPokemon(card=db.get("Pikachu ex"))
        b2 = InPlayPokemon(card=db.get("Dreepy"))
        b.active, b.bench = act, [b1, b2]
        fx._matcha_spin(ctx_for(st, a, b, source=src))
        return act.damage, b1.damage, b2.damage

    check(matcha(5) == (0, 0, 0),
          f"5 in discard is below the '6 or more' gate — the attack does nothing, "
          f"got {matcha(5)}")
    check(matcha(6) == (40, 40, 40),
          f"6 in discard -> 4 counters (40) on EACH of the opponent's Pokémon, Active "
          f"and Bench, got {matcha(6)}")
    # NEGATIVE: it never touches your own board.
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Sinistcha (PBL)"))
    mine = InPlayPokemon(card=db.get("Dhelmise (PBL)"))
    a.active, a.bench = src, [mine]
    a.discard = [HNS] * 6
    b.active = InPlayPokemon(card=db.get("Pikachu ex"))
    fx._matcha_spin(ctx_for(st, a, b, source=src))
    check(src.damage == 0 and mine.damage == 0,
          "Matcha Spin hits your OPPONENT's Pokémon only")

    # ----------------------------------------------------------------- #
    # 6. HEX HURL (Flutter Mane) — 2 damage counters on the opponent's BENCH.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    src = InPlayPokemon(card=db.get("Flutter Mane"))
    a.active = src
    act = InPlayPokemon(card=db.get("Pikachu ex"))
    ben = InPlayPokemon(card=db.get("Dreepy"))
    b.active, b.bench = act, [ben]
    fx._hex_hurl(ctx_for(st, a, b, source=src))
    check(ben.damage == 20 and act.damage == 0,
          f"Hex Hurl puts its 2 counters on the BENCH, not the Active, got "
          f"bench={ben.damage} active={act.damage}")

    # ----------------------------------------------------------------- #
    # 7. GWYNN — discard up to 2 non-Rule-Box Pokémon from hand, draw 3 for EACH.
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    a.hand = [db.get("Shuppet (PBL)"), db.get("Dhelmise (PBL)"), db.get("Boss's Orders")]
    a.deck = [db.get("Basic Psychic Energy")] * 10
    ok = fx._gwynn(ctx_for(st, a, b, kind="trainer"))
    check(ok is True, "Gwynn must report that it acted")
    check(len(a.discard) == 2 and all(c.is_pokemon for c in a.discard),
          f"Gwynn discards 2 Pokémon, got {[c.name for c in a.discard]}")
    check(len(a.hand) == 1 + 6,
          f"2 discarded -> draw 3 for each = 6; hand should be the leftover Supporter "
          f"plus 6, got {len(a.hand)}")

    # exactly 1 eligible Pokémon -> discard 1, draw 3 ("up to 2").
    st, a, b = fresh_state(db)
    a.hand = [db.get("Shuppet (PBL)"), db.get("Boss's Orders")]
    a.deck = [db.get("Basic Psychic Energy")] * 10
    fx._gwynn(ctx_for(st, a, b, kind="trainer"))
    check(len(a.discard) == 1 and len(a.hand) == 1 + 3,
          f"'up to 2' — with one eligible Pokémon it discards 1 and draws 3, got "
          f"discard={len(a.discard)} hand={len(a.hand)}")

    # NEGATIVE: Rule Box Pokémon can never be discarded to it, and with none eligible
    # the Supporter is not playable at all.
    st, a, b = fresh_state(db)
    a.hand = [db.get("Lillie's Clefairy ex"), db.get("Bloodmoon Ursaluna ex"),
              db.get("Boss's Orders")]
    a.deck = [db.get("Basic Psychic Energy")] * 10
    check(fx.can_play_gwynn(st, a) is False,
          "with only Rule Box Pokémon in hand, Gwynn must not be playable")
    check(fx._gwynn(ctx_for(st, a, b, kind="trainer")) is False and a.discard == [],
          "Gwynn must never discard a Pokémon ex (they have Rule Boxes)")
    check(fx.get_trainer_effect("Gwynn") is not None, "Gwynn must be a registered Trainer")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_hide_n_sneak_line.py: all checks passed — Hide 'n' Sneak prevents "
          "opposing attack/Ability EFFECTS (never damage), the discard-pile payoffs "
          "count only Pokémon with the Ability in your own discard, and the old prints "
          "stay vanilla")


if __name__ == "__main__":
    main()
