#!/usr/bin/env python3
"""
test_phase1_crustle_rules.py — Phase 1 (2026-11): rules verification + the cards added
for Drew's Crustle v1.1 / Gantner's Basic Box. One numbered block per rule or card;
each states the card/rule text it pins down.

Rules sources: deck-guides/rules/RULES-CHEATSHEET.md (official rulebook + Compendium
rulings), Limitless card pages, the pool's printed text.

Run: python3 tests/test_phase1_crustle_rules.py   (exit 0 = pass; also runs under pytest)
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import effects as fx
from src.engine.game import (setup_game, start_turn, legal_actions, apply_action,
                             Action)
from src.engine.decks import load_deck, DECKS

DB = None
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def db():
    global DB
    if DB is None:
        DB = CardDB.from_pool("data/standard_pool.json")
    return DB


def fresh(turn=5, active_index=0):
    a, b = PlayerState(name="A"), PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db()
    st.turn_number = turn
    st.active_index = active_index
    st.phase = Phase.MAIN
    return st, a, b


def mon(name, *energy, damage=0, tool=None):
    m = InPlayPokemon(card=db().get(name), damage=damage)
    m.energy = [db().get(e) for e in energy]
    if tool:
        m.tool = db().get(tool)
    return m


def actx(st, me, opp, source, kind="attack"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=st.rng, effect_kind=kind)


# --------------------------------------------------------------------------- #
# RULES
# --------------------------------------------------------------------------- #
def test_rock_inn():
    """Crustle — Mysterious Rock Inn: "Prevent all damage done to this Pokémon by
    attacks from your opponent's Pokémon ex." Damage only, ex only: counters PLACED by
    an attack's effect and counters from Abilities are not "damage done by attacks"."""
    st, a, b = fresh()
    crustle = mon("Crustle", "Basic Grass Energy")
    b.active = crustle
    kanga = mon("Mega Kangaskhan ex"); a.active = kanga
    dealt = fx.apply_attack_damage(actx(st, a, b, kanga), crustle, 200, owner=b, source=kanga)
    check(dealt == 0 and crustle.damage == 0, f"Rock Inn: ex attack damage must be 0, got {dealt}")
    # non-ex attacker: damage goes through
    passi = mon("Passimian"); a.active = passi
    dealt = fx.apply_attack_damage(actx(st, a, b, passi), crustle, 60, owner=b, source=passi)
    check(crustle.damage == 60, f"Rock Inn must NOT stop a non-ex attacker, got {crustle.damage}")
    # counters placed by an ex's attack EFFECT: not damage -> Rock Inn doesn't stop them
    crustle.damage = 0
    drag = mon("Dragapult ex"); a.active = drag
    placed = fx.place_counters(actx(st, a, b, drag), crustle, 3, owner=b)
    check(placed == 3 and crustle.damage == 30,
          f"Rock Inn must not stop counters placed by an attack effect (got {crustle.damage})")
    # counters from an Ability (ex source): not stopped either
    crustle.damage = 0
    placed = fx.place_counters(actx(st, a, b, drag, kind="ability"), crustle, 2, owner=b)
    check(crustle.damage == 20, f"Rock Inn must not stop Ability counters (got {crustle.damage})")


def test_mist_energy():
    """Mist Energy: "Prevent all effects of attacks used by your opponent's Pokémon done
    to the Pokémon this card is attached to. (... Damage is not an effect.)" Counters
    PLACED by an attack are an effect (blocked); Ability counters are not an attack
    effect (not blocked); attack damage is not an effect (not blocked)."""
    st, a, b = fresh()
    target = mon("Mega Kangaskhan ex", "Mist Energy")
    b.active = mon("Crustle"); b.bench = [target]
    drag = mon("Dragapult ex"); a.active = drag
    placed = fx.place_counters(actx(st, a, b, drag), target, 6, owner=b)
    check(placed == 0 and target.damage == 0, f"Mist must block attack counters, got {target.damage}")
    placed = fx.place_counters(actx(st, a, b, mon("Munkidori"), kind="ability"), target, 3, owner=b)
    check(target.damage == 30, f"Mist must NOT block Ability counters, got {target.damage}")
    target.damage = 0
    b.bench = []; b.active = target
    fx.apply_attack_damage(actx(st, a, b, drag), target, 100, owner=b, source=drag)
    check(target.damage == 100, f"Mist must NOT block attack damage, got {target.damage}")


def test_spiky_energy():
    """Spiky Energy: "If the Pokémon this card is attached to is in the Active Spot and
    is damaged by an attack from your opponent's Pokémon (even if this Pokémon is
    Knocked Out), put 2 damage counters on the Attacking Pokémon." Not when the damage
    was prevented (Rock Inn), not from the Bench."""
    st, a, b = fresh()
    holder = mon("Mega Kangaskhan ex", "Spiky Energy"); b.active = holder
    passi = mon("Passimian"); a.active = passi
    fx.apply_attack_damage(actx(st, a, b, passi), holder, 60, owner=b, source=passi)
    check(passi.damage == 20, f"Spiky: attacker should take 20, got {passi.damage}")
    # prevented damage -> no retaliation
    st, a, b = fresh()
    crustle = mon("Crustle", "Spiky Energy"); b.active = crustle
    kanga = mon("Mega Kangaskhan ex"); a.active = kanga
    fx.apply_attack_damage(actx(st, a, b, kanga), crustle, 200, owner=b, source=kanga)
    check(kanga.damage == 0, f"Spiky: no retaliation when Rock Inn prevented it ({kanga.damage})")
    # benched holder -> no retaliation
    st, a, b = fresh()
    b.active = mon("Crustle"); benched = mon("Dwebble", "Spiky Energy"); b.bench = [benched]
    passi = mon("Passimian"); a.active = passi
    fx.apply_attack_damage(actx(st, a, b, passi), benched, 30, owner=b, source=passi)
    check(passi.damage == 0, f"Spiky: Benched holder must not retaliate ({passi.damage})")
    # KO'd holder still retaliates
    st, a, b = fresh()
    holder = mon("Dwebble", "Spiky Energy", damage=60); b.active = holder
    passi = mon("Passimian"); a.active = passi
    fx.apply_attack_damage(actx(st, a, b, passi), holder, 60, owner=b, source=passi)
    check(passi.damage == 20, f"Spiky: retaliates even if KO'd, got {passi.damage}")


def test_heros_cape():
    """Hero's Cape (ACE SPEC Tool): "The Pokémon this card is attached to gets +100 HP."""
    st, a, b = fresh()
    c = mon("Crustle", tool="Hero's Cape"); a.active = c
    b.active = mon("Dreepy")
    fx.refresh_hp_modifiers(st)
    check(c.max_hp == 250, f"Hero's Cape: Crustle 150 -> 250, got {c.max_hp}")


def test_jumbo_ice_cream():
    """Jumbo Ice Cream: "Heal 80 damage from your Active Pokémon that has 3 or more
    Energy attached." 3 Energy CARDS (Growing Grass counts as one)."""
    st, a, b = fresh()
    a.active = mon("Crustle", "Mist Energy", "Growing Grass Energy", damage=100)
    b.active = mon("Dreepy")
    check(not fx.can_play_trainer(st, a, "Jumbo Ice Cream"), "2 Energy: not playable")
    a.active.energy.append(db().get("Spiky Energy"))
    check(fx.can_play_trainer(st, a, "Jumbo Ice Cream"), "3 Energy: playable")
    fx._jumbo_ice_cream(fx.EffectContext(state=st, me=a, opp=b, db=st.db, rng=st.rng))
    check(a.active.damage == 20, f"heal 80 from 100 -> 20, got {a.active.damage}")


def _deck(name):
    return load_deck(db(), name)


def test_one_supporter_and_first_turn():
    """One Supporter per turn; the player going FIRST can't play a Supporter or attack
    on their first turn (turn_number 1). The second player can on their turn 1 (turn 2)."""
    for seed in range(40):
        st = setup_game(_deck("crustle_drew_v11"), _deck("dragapult_puebla"),
                        seed=seed, db=db(), first_player=0)
        start_turn(st)
        p = st.current
        acts = legal_actions(st)
        sup = [x for x in acts if x.kind == "play_trainer" and p.hand[x.hand_index].is_supporter]
        check(not sup, f"seed {seed}: going-first player offered a Supporter on turn 1")
        check(not any(x.kind == "attack" for x in acts),
              f"seed {seed}: going-first player offered an attack on turn 1")
    # the second player, turn 2: Supporters legal; after one, no more
    found = False
    for seed in range(200):
        st = setup_game(_deck("crustle_drew_v11"), _deck("crustle_drew_v11"),
                        seed=seed, db=db(), first_player=0)
        start_turn(st)
        st.phase = Phase.BETWEEN_TURNS
        from src.engine.game import end_turn
        end_turn(st)
        start_turn(st)
        p = st.current
        sups = [x for x in legal_actions(st) if x.kind == "play_trainer"
                and p.hand[x.hand_index].is_supporter]
        if len(sups) >= 1 and sum(c.is_supporter for c in p.hand) >= 2:
            found = True
            apply_action(st, sups[0])
            again = [x for x in legal_actions(st) if x.kind == "play_trainer"
                     and p.hand[x.hand_index].is_supporter]
            check(not again, f"seed {seed}: a second Supporter was offered in one turn")
            break
    check(found, "no seed gave the second player 2+ playable Supporters on turn 2")


def test_turn_order_before_draw():
    """"Flip a coin; the winner decides who goes first" happens BEFORE hands are drawn,
    so the deal cannot depend on who goes first: same seed, either seat -> identical
    opening hands, prizes and Actives. And the default seat is the FIRST rng draw."""
    for seed in range(30):
        s0 = setup_game(_deck("crustle_drew_v11"), _deck("basic_box_gantner"),
                        seed=seed, db=db(), first_player=0)
        s1 = setup_game(_deck("crustle_drew_v11"), _deck("basic_box_gantner"),
                        seed=seed, db=db(), first_player=1)
        sd = setup_game(_deck("crustle_drew_v11"), _deck("basic_box_gantner"),
                        seed=seed, db=db())
        for i in (0, 1):
            check([c.name for c in s0.players[i].hand] == [c.name for c in s1.players[i].hand],
                  f"seed {seed}: hand of P{i} depends on who goes first")
            check([c.name for c in s0.players[i].prizes] == [c.name for c in sd.players[i].prizes],
                  f"seed {seed}: prizes of P{i} depend on the seat override")
        check(sd.active_index == random.Random(seed).randint(0, 1),
              f"seed {seed}: the coin flip must be the first rng draw")


def test_mulligan_draws():
    """"For each mulligan your opponent took, you may draw 1 card." Hand size after
    setup = 7 - 1 (Active) + opponent's mulligans."""
    seen = False
    for seed in range(300):
        st = setup_game(_deck("crustle_drew_v11"), _deck("dragapult_puebla"),
                        seed=seed, db=db(), first_player=0)
        m = st.setup_mulligans
        for i in (0, 1):
            check(len(st.players[i].hand) == 6 + m[1 - i],
                  f"seed {seed}: P{i} hand {len(st.players[i].hand)} with opp mulligans {m[1 - i]}")
            check(len(st.players[i].deck) == 60 - 7 - 6 - m[1 - i],
                  f"seed {seed}: P{i} deck size wrong")
        if any(m):
            seen = True
    check(seen, "no seed produced a mulligan; widen the range")


def test_retreat_once_per_turn():
    """Retreat: "You may retreat only once during your turn"."""
    st, a, b = fresh()
    a.active = mon("Mega Kangaskhan ex", *(["Basic Grass Energy"] * 6))
    a.bench = [mon("Meowth ex", *(["Basic Grass Energy"] * 3)), mon("Dwebble")]
    b.active = mon("Dreepy")
    r = [x for x in legal_actions(st) if x.kind == "retreat"]
    check(r, "retreat should be legal")
    apply_action(st, r[0])
    r2 = [x for x in legal_actions(st) if x.kind == "retreat"]
    check(not r2, "a second retreat in the same turn must not be offered")


# --------------------------------------------------------------------------- #
# CARDS
# --------------------------------------------------------------------------- #
def test_ascension():
    """Dwebble — Ascension [C]: "Search your deck for a card that evolves from this
    Pokémon and put it onto this Pokémon to evolve it. Then, shuffle your deck." Works
    the turn Dwebble was played (Compendium ruling); damage/energy carry over."""
    st, a, b = fresh()
    dw = mon("Dwebble", "Mist Energy", damage=20); dw.played_this_turn = True
    a.active = dw; b.active = mon("Dreepy")
    a.deck = [db().get("Crustle"), db().get("Boss's Orders")]
    fx.get_attack_effect("Dwebble", "Ascension")(actx(st, a, b, dw))
    check(dw.card.name == "Crustle", f"Ascension must evolve into Crustle, got {dw.card.name}")
    check(dw.damage == 20 and len(dw.energy) == 1, "damage and Energy carry over")
    check(len(a.deck) == 1, "Crustle left the deck")
    # whiff: no Crustle in deck
    st, a, b = fresh()
    dw = mon("Dwebble"); a.active = dw; b.active = mon("Dreepy")
    a.deck = [db().get("Boss's Orders")]
    fx.get_attack_effect("Dwebble", "Ascension")(actx(st, a, b, dw))
    check(dw.card.name == "Dwebble", "no Crustle in deck: stays Dwebble")


def test_growing_grass_energy():
    """Growing Grass Energy (POR 86): provides [G]; "The [G] Pokémon this card is
    attached to gets +20 HP." Non-[G] holders get nothing."""
    gge = db().get("Growing Grass Energy")
    check(list(gge.types) == ["Grass"], f"provides Grass, got {gge.types}")
    check("Growing Grass Energy" in fx.SPECIAL_ENERGY_IMPLEMENTED, "registered")
    st, a, b = fresh()
    c = mon("Crustle", "Growing Grass Energy", "Growing Grass Energy", tool="Hero's Cape")
    k = mon("Mega Kangaskhan ex", "Growing Grass Energy")
    a.active = c; a.bench = [k]; b.active = mon("Dreepy")
    fx.refresh_hp_modifiers(st)
    check(c.max_hp == 150 + 100 + 40, f"Crustle + Cape + 2 GGE = 290, got {c.max_hp}")
    check(k.max_hp == 300, f"Colorless holder gets no HP, got {k.max_hp}")
    check(c.provided_types().count("Grass") == 2, "each GGE provides one [G]")
    # losing it lowers HP and can KO
    c.damage = 270
    c.energy.pop()
    fx.process_knockouts(st)
    check(a.active is not c, "dropping to 270 max HP with 270 damage must KO")


def test_lumiose_city():
    """Lumiose City (POR 77): "Once during each player's turn, that player may search
    their deck for a Basic Pokémon and put it onto their Bench. Then, that player
    shuffles their deck. If a player searches their deck in this way, their turn ends." """
    st, a, b = fresh()
    st.stadium = db().get("Lumiose City")
    a.active = mon("Crustle"); b.active = mon("Dreepy")
    a.deck = [db().get("Dwebble"), db().get("Mega Kangaskhan ex"), db().get("Crustle")]
    acts = [x for x in legal_actions(st) if x.kind == "stadium_lumiose"]
    check(len(acts) == 2, f"two distinct Basics -> 2 options, got {len(acts)}")
    apply_action(st, acts[0])
    check(len(a.bench) == 1 and a.bench[0].card.is_basic, "benched a Basic")
    check(st.phase == Phase.BETWEEN_TURNS, "Lumiose City ends the turn")
    # full Bench -> not offered; and either player may use it
    st, a, b = fresh(active_index=1)
    st.stadium = db().get("Lumiose City")
    a.active = mon("Crustle"); b.active = mon("Dreepy")
    b.deck = [db().get("Dreepy")]
    b.bench = [mon("Dreepy") for _ in range(5)]
    check(not [x for x in legal_actions(st) if x.kind == "stadium_lumiose"],
          "full Bench: not offered")
    b.bench.pop()
    check([x for x in legal_actions(st) if x.kind == "stadium_lumiose"],
          "the opponent of the Stadium's owner may use it too")
    check("Lumiose City" in fx.STADIUM_IMPLEMENTED, "registered")


def test_xerosic():
    """Xerosic's Machinations: "Your opponent discards cards from their hand until they
    have 3 cards in their hand." Not playable when that does nothing (≤3 cards)."""
    st, a, b = fresh()
    a.active = mon("Crustle"); b.active = mon("Dreepy")
    b.hand = [db().get(n) for n in ("Dreepy", "Boss's Orders", "Ultra Ball",
                                    "Basic Fire Energy", "Crushing Hammer", "Drakloak")]
    check(fx.can_play_trainer(st, a, "Xerosic's Machinations"), "6 cards: playable")
    fx.TRAINER_EFFECTS["Xerosic's Machinations"](fx.EffectContext(state=st, me=a, opp=b,
                                                                  db=st.db, rng=st.rng))
    check(len(b.hand) == 3 and len(b.discard) == 3, f"down to 3, got {len(b.hand)}")
    check(not fx.can_play_trainer(st, a, "Xerosic's Machinations"), "3 cards: not playable")


def test_pokemon_center_lady():
    """Pokémon Center Lady: "Heal 60 damage from 1 of your Pokémon, and it recovers from
    all Special Conditions." """
    st, a, b = fresh()
    act = mon("Crustle", damage=30); ben = mon("Mega Kangaskhan ex", damage=120)
    a.active = act; a.bench = [ben]; b.active = mon("Dreepy")
    fx.TRAINER_EFFECTS["Pokémon Center Lady"](fx.EffectContext(state=st, me=a, opp=b,
                                                               db=st.db, rng=st.rng))
    check(ben.damage == 60 and act.damage == 30, "heals 60 from the most-damaged one")
    act.damage = 0; ben.damage = 0
    check(not fx.can_play_trainer(st, a, "Pokémon Center Lady"), "nothing to heal: not playable")
    act.poisoned = True
    check(fx.can_play_trainer(st, a, "Pokémon Center Lady"), "Poisoned: playable")


def test_festival_grounds():
    """Festival Grounds: "Each Pokémon that has any Energy attached (both yours and your
    opponent's) recovers from all Special Conditions and can't be affected by any
    Special Conditions." """
    st, a, b = fresh()
    a.active = mon("Crustle"); a.active.poisoned = True; a.active.confused = True
    b.active = mon("Dreepy", "Basic Fire Energy"); b.active.poisoned = True
    st.stadium = db().get("Festival Grounds")
    fx.process_knockouts(st)
    check(not b.active.poisoned, "Energy holder recovers")
    check(a.active.poisoned and a.active.confused, "no Energy: conditions stay")
    a.active.energy.append(db().get("Mist Energy"))
    fx.process_knockouts(st)
    check(not a.active.poisoned and not a.active.confused, "after attaching: recovers")
    check(not fx.can_be_conditioned(st, a.active), "and can't be conditioned")
    check("Festival Grounds" in fx.STADIUM_IMPLEMENTED, "registered")


def test_snow_sink_registered():
    check(("Chien-Pao", "Snow Sink") in fx.PASSIVE_ABILITIES, "Snow Sink registered")
    check(fx.get_on_bench_trigger("Chien-Pao") is not None, "Snow Sink trigger wired")


def test_basic_box_cards():
    """Passimian (20× per your Basic in play), Iron Crown ex Cobalt Command (+20 to the
    opponent's Active for Future attackers other than Iron Crown ex), Glass Trumpet."""
    st, a, b = fresh()
    passi = mon("Passimian"); a.active = passi
    a.bench = [mon("Meowth ex"), mon("Latias ex"), mon("Dwebble"), mon("Crustle")]
    b.active = mon("Dragapult ex")          # Dragon: no Weakness to [F]
    fx.get_attack_effect("Passimian", "Coordinated Throwing")(actx(st, a, b, passi))
    check(b.active.damage == 80, f"4 Basics x 20 = 80 (Crustle is Stage 1), got {b.active.damage}")
    b.active = mon("Mega Kangaskhan ex")    # Colorless: Weakness [F] x2 on the total
    fx.get_attack_effect("Passimian", "Coordinated Throwing")(actx(st, a, b, passi))
    check(b.active.damage == 160, f"Weakness doubles the total once, got {b.active.damage}")
    # Cobalt Command
    st, a, b = fresh()
    leaves = mon("Iron Leaves ex"); a.active = leaves
    a.bench = [mon("Iron Crown ex"), mon("Iron Crown ex")]
    b.active = mon("Mega Kangaskhan ex")
    fx.apply_attack_damage(actx(st, a, b, leaves), b.active, 100, owner=b, source=leaves)
    check(b.active.damage == 140, f"two Iron Crown ex: +40, got {b.active.damage}")
    st, a, b = fresh()
    crown = mon("Iron Crown ex"); a.active = crown; a.bench = [mon("Iron Crown ex")]
    b.active = mon("Mega Kangaskhan ex")
    fx.apply_attack_damage(actx(st, a, b, crown), b.active, 100, owner=b, source=crown)
    check(b.active.damage == 100, f"Iron Crown ex itself gets no bonus, got {b.active.damage}")
    # Glass Trumpet
    st, a, b = fresh()
    a.active = mon("Raging Bolt ex"); a.bench = [mon("Mega Kangaskhan ex"), mon("Meowth ex"),
                                                 mon("Latias ex")]
    a.discard = [db().get("Basic Grass Energy"), db().get("Basic Fighting Energy")]
    b.active = mon("Dreepy")
    check(not fx.can_play_trainer(st, a, "Glass Trumpet"), "no Tera in play: unplayable")
    a.bench.append(mon("Teal Mask Ogerpon ex"))
    check(fx.can_play_trainer(st, a, "Glass Trumpet"), "Tera in play: playable")
    fx.TRAINER_EFFECTS["Glass Trumpet"](fx.EffectContext(state=st, me=a, opp=b,
                                                         db=st.db, rng=st.rng))
    check(sum(len(m.energy) for m in a.bench[:2]) == 2 and len(a.bench[2].energy) == 0,
          "two Benched Colorless Pokémon get 1 each; Latias (Psychic) none")


def test_decks_registered():
    for name in ("crustle_drew_v11", "dragapult_puebla", "basic_box_gantner"):
        check(name in DECKS and len(load_deck(db(), name)) == 60, f"{name} registered, 60")
    from src.analysis.gap_check import check_deck_implementation
    for name in ("crustle_drew_v11", "dragapult_puebla", "basic_box_gantner"):
        gaps = check_deck_implementation(DECKS[name], db())
        check(gaps == [], f"{name}: unimplemented card text {gaps}")


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def test_zz_report():
    """pytest entry point: the groups above append to FAILS instead of raising (so the
    script form reports everything at once); this last test makes pytest fail on them."""
    assert not FAILS, "\n".join(FAILS)


def main():
    for t in ALL:
        try:
            t()
        except Exception as e:  # a crash is a failure, not an abort
            import traceback
            FAILS.append(f"{t.__name__} crashed: {e!r}\n{traceback.format_exc()}")
    if FAILS:
        print(f"test_phase1_crustle_rules.py: {len(FAILS)} FAILURE(S)")
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print(f"test_phase1_crustle_rules.py: all {len(ALL)} groups passed")


if __name__ == "__main__":
    main()
