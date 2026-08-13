#!/usr/bin/env python3
"""
test_aegislash_line.py — the rest of the `doublade` archetype's cards, each asserted
against its printed text. (Doublade's Weaponized Swords has its own file,
tests/test_weaponized_swords.py, because it is the unusual one.)

  Honedge (Perfect Order 56/88)   — Basic, 70 HP [M]. "Cut" [C] 10, NO effect text.
      Deliberately VANILLA: it must have no registry entry at all.
  Aegislash (Perfect Order 58/88) — Stage 2 (from Doublade), 150 HP [M], NO Ability.
      "Slash" [C][C][C] 80, no additional effect text (vanilla).
      "Metal Slash" [M][C][C][C] 230 — "During your next turn, this Pokémon can't use
      attacks."
      RECON GUARD: Aegislash does NOT inherit or reprint Weaponized Swords; it carries
      two entirely distinct attacks. Asserted below, because that was the single most
      likely thing to get wrong about this line.
  Steven's Metang (Destined Rivals 144/182) — "Metal Slash" [M][C] 70 — "During your
      next turn, this Pokémon can't attack." Same rule, different wording, same effect.
  Steven's Metagross ex (Destined Rivals 145/182) — Ability "X-Boot": "Once during your
      turn, you may search your deck for a Basic Psychic Energy card, a Basic Metal
      Energy card, or 1 of each and attach them to your Psychic Pokémon and Metal
      Pokémon in any way you like. Then, shuffle your deck."

Also pinned here: the Honedge -> Doublade -> Aegislash evolution chain works through the
real engine, and Rare Candy really can skip Steven's Metang (the reason 2 copies are in
the list).

Run: python3 tests/test_aegislash_line.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import effects as fx
from src.engine.game import legal_actions, apply_action, start_turn, evolves_onto, Action


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.turns_taken = 3
    b.turns_taken = 3
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    a.deck = [db.get("Basic Metal Energy")] * 10
    b.deck = [db.get("Basic Psychic Energy")] * 10
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng,
                            effect_kind="ability")


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # ------------------------------------------------------------------ #
    # 1. HONEDGE — stats + a genuinely vanilla attack.
    # ------------------------------------------------------------------ #
    honedge = db.get("Honedge")
    check(honedge.hp == 70 and honedge.types == ("Metal",) and honedge.is_basic,
          f"Honedge: 70 HP Basic [M], got hp={honedge.hp} types={honedge.types} "
          f"subtypes={honedge.subtypes}")
    check(honedge.retreat_cost == 2, f"Honedge retreats for 2, got {honedge.retreat_cost}")
    cut = next((x for x in honedge.attacks if x.name == "Cut"), None)
    check(cut is not None and cut.cost == ("Colorless",) and cut.damage == 10
          and cut.text == "",
          f"Honedge's only attack is Cut [C] 10 with NO effect text, got {honedge.attacks}")
    check(("Honedge", "Cut") not in fx.ATTACK_EFFECTS,
          "Cut has no effect text — it must stay vanilla, with no registry entry")

    # ------------------------------------------------------------------ #
    # 2. AEGISLASH — the recon guard, then Slash (vanilla) and Metal Slash (lock).
    # ------------------------------------------------------------------ #
    aegis = db.get("Aegislash")
    check(aegis.hp == 150 and aegis.types == ("Metal",) and "Stage 2" in aegis.subtypes,
          f"Aegislash: 150 HP Stage 2 [M], got hp={aegis.hp} subtypes={aegis.subtypes}")
    check(aegis.evolves_from == "Doublade",
          f"Aegislash evolves from Doublade, got {aegis.evolves_from!r}")
    check(aegis.abilities == (),
          f"Aegislash has NO Ability, got {[ab.name for ab in aegis.abilities]}")
    names = [x.name for x in aegis.attacks]
    check(names == ["Slash", "Metal Slash"],
          f"Aegislash's attacks are Slash and Metal Slash, got {names}")
    check("Weaponized Swords" not in names,
          "RECON GUARD: Aegislash must NOT have Doublade's Weaponized Swords — it carries "
          "two entirely distinct attacks")
    slash = aegis.attacks[0]
    check(slash.cost == ("Colorless",) * 3 and slash.damage == 80 and slash.text == "",
          f"Slash is [C][C][C] 80 with no additional effect text, got {slash}")
    check(("Aegislash", "Slash") not in fx.ATTACK_EFFECTS,
          "Slash has no effect text — it must stay vanilla")
    mslash = aegis.attacks[1]
    check(mslash.cost == ("Metal", "Colorless", "Colorless", "Colorless")
          and mslash.damage == 230,
          f"Metal Slash is [M][C][C][C] 230, got cost={mslash.cost} dmg={mslash.damage}")
    check(mslash.text == "During your next turn, this Pokémon can't use attacks.",
          f"Metal Slash's text must match the printed card, got {mslash.text!r}")
    check(("Aegislash", "Metal Slash") in fx.ATTACK_EFFECTS,
          "Metal Slash must be registered (its lock is real effect text)")
    check(("Aegislash", "Metal Slash") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "Metal Slash's 230 is FLAT and engine-applied — the effect must not own damage, "
          "or the hit would land twice")

    # 2a. the lock, through the real engine: 230 lands, then no attacks next turn,
    #     then it comes back the turn after.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=aegis)
    a.active.energy = [db.get("Basic Metal Energy")] + [db.get("Basic Psychic Energy")] * 3
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))   # 320 HP, survives 230
    acts = [x for x in legal_actions(st) if x.kind == "attack"
            and a.active.card.attacks[x.attack_index].name == "Metal Slash"]
    check(len(acts) == 1, f"[M][C][C][C] paid -> Metal Slash is legal, got {len(acts)}")
    if acts:
        apply_action(st, acts[0])
        check(b.active.damage == 230,
              f"Metal Slash's flat 230 must land exactly once, got {b.active.damage}")
        check(a.active.pending_cannot_attack is True,
              "Metal Slash must arm the can't-attack lock for the owner's NEXT turn")
        check(a.active.cannot_attack is False,
              "the lock is PENDING — it must not bite during the turn it was used")
    st.phase = Phase.MAIN
    st.active_index = 1
    start_turn(st)                       # opponent's intervening turn
    check(a.active.cannot_attack is False,
          "the lock must not activate on the OPPONENT's turn")
    st.active_index = 0
    start_turn(st)                       # owner's next turn — locked
    check(a.active.cannot_attack is True,
          "on the owner's next turn the Pokémon must be unable to attack")
    check(not [x for x in legal_actions(st) if x.kind == "attack"],
          "'can't use attacks' means NO attack is offered — not even Slash")
    st.active_index = 1
    start_turn(st)
    st.active_index = 0
    start_turn(st)                       # a turn later — free again
    check(a.active.cannot_attack is False,
          "the lock lasts exactly one turn and must clear afterwards")
    check([x for x in legal_actions(st) if x.kind == "attack"],
          "with the lock cleared, attacks must be offered again")

    # ------------------------------------------------------------------ #
    # 3. STEVEN'S METANG — the same lock, its own printed wording, 70 flat.
    # ------------------------------------------------------------------ #
    metang = db.get("Steven's Metang")
    ms = next((x for x in metang.attacks if x.name == "Metal Slash"), None)
    check(ms is not None and ms.cost == ("Metal", "Colorless") and ms.damage == 70,
          f"Steven's Metang: Metal Slash [M][C] 70, got {metang.attacks}")
    check(ms is not None and ms.text == "During your next turn, this Pokémon can't attack.",
          f"its printed wording is 'can't attack' (not 'can't use attacks'), got "
          f"{ms.text if ms else None!r}")
    check(("Steven's Metang", "Metal Slash") in fx.ATTACK_EFFECTS,
          "Steven's Metang's Metal Slash must be registered too")
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=metang)
    a.active.energy = [db.get("Basic Metal Energy"), db.get("Basic Psychic Energy")]
    acts = [x for x in legal_actions(st) if x.kind == "attack"]
    check(len(acts) == 1, f"Metal Slash must be its only payable attack, got {len(acts)}")
    if acts:
        apply_action(st, acts[0])
        check(b.active.damage == 70,
              f"Steven's Metang's flat 70 must land once, got {b.active.damage}")
        check(a.active.pending_cannot_attack is True,
              "and it must arm the same one-turn can't-attack lock")

    # ------------------------------------------------------------------ #
    # 4. X-BOOT — search a Basic [P] and/or a Basic [M] Energy out of the deck and
    #    attach each to a Pokémon of the MATCHING type.
    # ------------------------------------------------------------------ #
    gross = db.get("Steven's Metagross ex")
    ability = next((ab for ab in gross.abilities if ab.name == "X-Boot"), None)
    check(ability is not None, "Steven's Metagross ex must have the X-Boot Ability")
    check(ability is not None and ability.text.startswith("Once during your turn"),
          f"X-Boot is once per turn, got {ability.text if ability else None!r}")
    check(("Steven's Metagross ex", "X-Boot") in fx.ABILITY_EFFECTS,
          "X-Boot must be registered in ABILITY_EFFECTS")
    check(("Steven's Metagross ex", "X-Boot") not in fx.REPEATABLE_ABILITIES,
          "'Once during your turn' — X-Boot must NOT be repeatable")

    # 4a. both halves available (a [M] holder and a [P] holder in play): 1 of each,
    #     each landing on its own type.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=gross)                       # Metal
    psychic = InPlayPokemon(card=db.get("Munkidori"))          # a real [P] Pokémon
    a.bench = [psychic]
    a.deck = ([db.get("Basic Metal Energy")] * 3 + [db.get("Basic Psychic Energy")] * 3
              + [db.get("Rare Candy")] * 4)
    deck_before = len(a.deck)
    fx._x_boot(ctx_for(st, a, b, source=a.active))
    check(len(a.deck) == deck_before - 2,
          f"'1 of each' must take exactly 2 cards out of the deck, got "
          f"{deck_before - len(a.deck)}")
    check([e.name for e in a.active.energy] == ["Basic Metal Energy"],
          f"the Basic [M] Energy must land on the [M] Pokémon, got "
          f"{[e.name for e in a.active.energy]}")
    check([e.name for e in psychic.energy] == ["Basic Psychic Energy"],
          f"the Basic [P] Energy must land on the [P] Pokémon, got "
          f"{[e.name for e in psychic.energy]}")
    check(not a.energy_attached_this_turn,
          "X-Boot is an Ability — it must NOT consume the turn's manual Energy attachment")

    # 4b. NO Psychic Pokémon in play (the `doublade` list's actual situation): only the
    #     Metal half happens, and the Psychic Energy stays in the deck.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=gross)
    a.bench = [InPlayPokemon(card=db.get("Honedge"))]          # also Metal
    a.deck = [db.get("Basic Metal Energy"), db.get("Basic Psychic Energy")]
    fx._x_boot(ctx_for(st, a, b, source=a.active))
    check([e.name for e in a.active.energy] == ["Basic Metal Energy"],
          f"with no [P] Pokémon only the Metal half fires, got "
          f"{[e.name for e in a.active.energy]}")
    check([c.name for c in a.deck] == ["Basic Psychic Energy"],
          f"the Basic [P] Energy must stay in the deck (nothing legal to attach it to), "
          f"got {[c.name for c in a.deck]}")
    check(a.bench[0].energy == [],
          "and it must certainly not be attached to a Metal Pokémon instead")

    # 4c. NEGATIVE: neither half available -> the Ability is not even offered.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=gross)
    a.deck = [db.get("Rare Candy")] * 5                        # no Basic Energy at all
    check(fx.can_use_x_boot(st, a, a.active) is False,
          "with no Basic [P]/[M] Energy left in the deck X-Boot must not be offered")
    check(not [x for x in legal_actions(st) if x.kind == "use_ability"],
          "and legal_actions must not offer it either")

    # 4d. once per turn: after using it through the engine it is gone until next turn.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=gross)
    a.deck = [db.get("Basic Metal Energy")] * 4
    offers = [x for x in legal_actions(st) if x.kind == "use_ability"]
    check(len(offers) == 1, f"X-Boot must be offered once, got {len(offers)}")
    if offers:
        apply_action(st, offers[0])
        check(a.active.energy_count() == 1,
              f"one Basic [M] Energy attached, got {a.active.energy_count()}")
        check(not [x for x in legal_actions(st) if x.kind == "use_ability"],
              "'Once during your turn' — no second use in the same turn")
        st.active_index = 1
        start_turn(st)
        st.active_index = 0
        start_turn(st)
        check([x for x in legal_actions(st) if x.kind == "use_ability"],
              "and it must be available again next turn")

    # ------------------------------------------------------------------ #
    # 5. EVOLUTION CHAINS — the line really links, and Rare Candy really skips
    #    Steven's Metang (which is why the list runs only 1 copy of it).
    # ------------------------------------------------------------------ #
    check(evolves_onto(db.get("Honedge"), db.get("Doublade")),
          "Honedge must evolve into Doublade")
    check(evolves_onto(db.get("Doublade"), db.get("Aegislash")),
          "Doublade must evolve into Aegislash")
    check(evolves_onto(db.get("Steven's Beldum"), db.get("Steven's Metang")),
          "Steven's Beldum must evolve into Steven's Metang")
    check(evolves_onto(db.get("Steven's Metang"), db.get("Steven's Metagross ex")),
          "Steven's Metang must evolve into Steven's Metagross ex")
    check(not evolves_onto(db.get("Honedge"), db.get("Aegislash")),
          "Honedge must NOT evolve straight into Aegislash without Rare Candy")
    check(fx._evolution_chain_basic(db, db.get("Aegislash")) == "Honedge",
          "Rare Candy's chain walk: Aegislash -> Doublade -> Honedge")
    check(fx._evolution_chain_basic(db, db.get("Steven's Metagross ex")) == "Steven's Beldum",
          "Rare Candy's chain walk: Steven's Metagross ex -> Steven's Metang -> "
          "Steven's Beldum")

    # 5a. Rare Candy in a real engine turn, on BOTH Stage 2s in this list.
    for basic_name, stage2_name in (("Honedge", "Aegislash"),
                                    ("Steven's Beldum", "Steven's Metagross ex")):
        st, a, b = fresh_state(db)
        a.active = InPlayPokemon(card=db.get(basic_name))
        a.hand = [db.get("Rare Candy"), db.get(stage2_name)]
        candies = [x for x in legal_actions(st) if x.kind == "play_trainer"
                   and a.hand[x.hand_index].name == "Rare Candy"]
        check(len(candies) == 1,
              f"Rare Candy must be playable onto {basic_name} with {stage2_name} in hand, "
              f"got {len(candies)}")
        if candies:
            apply_action(st, candies[0])
            check(a.active.card.name == stage2_name,
                  f"Rare Candy must turn {basic_name} into {stage2_name}, got "
                  f"{a.active.card.name}")

    # 5b. the natural chain, one stage at a time, through legal_actions.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Honedge"))
    a.hand = [db.get("Doublade")]
    evs = [x for x in legal_actions(st) if x.kind == "evolve"]
    check(len(evs) == 1, f"Doublade must be offered onto Honedge, got {len(evs)}")
    if evs:
        apply_action(st, evs[0])
        check(a.active.card.name == "Doublade", "Honedge -> Doublade")
        a.hand = [db.get("Aegislash")]
        a.active.evolved_this_turn = False        # next turn, in effect
        evs2 = [x for x in legal_actions(st) if x.kind == "evolve"]
        check(len(evs2) == 1, f"Aegislash must be offered onto Doublade, got {len(evs2)}")
        if evs2:
            apply_action(st, evs2[0])
            check(a.active.card.name == "Aegislash", "Doublade -> Aegislash")
            check(a.active.damage == 0 and a.active.card.hp == 150,
                  "the evolved Aegislash is a 150 HP Stage 2")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_aegislash_line.py: all checks passed — Honedge/Slash stay vanilla, "
          "Aegislash has NO Weaponized Swords and its Metal Slash locks for exactly one "
          "turn, Steven's Metang shares that lock, X-Boot attaches type-matched Basic "
          "Energy once per turn, and both evolution lines (incl. Rare Candy) link")


if __name__ == "__main__":
    main()
