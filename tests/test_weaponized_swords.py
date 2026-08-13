#!/usr/bin/env python3
"""
test_weaponized_swords.py — Doublade (Perfect Order 57/88) "Weaponized Swords":

    [C][C]  60×
    "Reveal any number of Honedge, Doublade, and Aegislash from your hand, and this
     attack does 60 damage for each card you revealed in this way."

THE POINT OF THIS FILE. "Reveal" is an INFORMATION action, not a cost: the cards are
shown to the opponent and then stay exactly where they were, in hand, fully reusable
next turn and every turn after. That is unusual for this engine's effect vocabulary —
every other scaling attack here PAYS for its damage by moving cards (Inferno X and
Metallic Hammer discard Energy, Garland Ray discards Energy, Cursed Blast KOs itself).
So the tests below pin the hand-invariance down from several directions: exact hand
contents before/after, repeated use across turns with no decay, and a negative case
proving nothing reaches the discard pile.

Also pinned: only the three NAMED cards count (not "any Metal Pokémon", not cards in
play or in the discard), damage is exactly 60 per revealed card, Weakness multiplies
the WHOLE total once (60× is variable damage -> the engine applies 0 base and this
effect lands the entire hit), and an empty reveal does exactly nothing.

Run: python3 tests/test_weaponized_swords.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon, Phase
from src.engine import effects as fx
from src.engine.game import legal_actions, apply_action, start_turn, Action

CARD_TEXT = ("Reveal any number of Honedge, Doublade, and Aegislash from your hand, "
             "and this attack does 60 damage for each card you revealed in this way.")


def fresh_state(db, defender="Dragapult ex"):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    st.phase = Phase.MAIN
    a.active = InPlayPokemon(card=db.get("Doublade"))
    b.active = InPlayPokemon(card=db.get(defender))
    a.turns_taken = 3
    b.turns_taken = 3
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 0. the pool entry really is the card this file claims to test. ---
    doublade = db.get("Doublade")
    atk = next((x for x in doublade.attacks if x.name == "Weaponized Swords"), None)
    check(atk is not None, "Doublade must have a 'Weaponized Swords' attack")
    check(atk.text == CARD_TEXT,
          f"the pool's attack text must match the printed card, got {atk.text!r}")
    check(atk.cost == ("Colorless", "Colorless"),
          f"Weaponized Swords costs [C][C], got {atk.cost}")
    check((atk.damage, atk.damage_suffix) == (60, "×"),
          f"printed damage is '60×', got {atk.damage}{atk.damage_suffix!r}")
    check(("Doublade", "Weaponized Swords") in fx.ATTACK_EFFECTS,
          "Weaponized Swords must be registered in ATTACK_EFFECTS")
    # Variable-damage ("×") attacks get 0 engine base automatically, so this attack must
    # NOT also be listed in ATTACK_EFFECT_OWNS_DAMAGE (that set is for FLAT-printed
    # attacks only). Listing it in both places is harmless today but records a wrong
    # reason, so pin the precedent.
    check(("Doublade", "Weaponized Swords") not in fx.ATTACK_EFFECT_OWNS_DAMAGE,
          "a '×'-printed attack is already zero-based by the engine — it does not belong "
          "in ATTACK_EFFECT_OWNS_DAMAGE (Maximum Drilling / Raging Curse precedent)")

    # --- 1. damage is exactly 60 per revealed card, counting only the three named ones. ---
    for hand_names, expected_revealed in (
        ([], 0),
        (["Honedge"], 1),
        (["Honedge", "Doublade"], 2),
        (["Honedge", "Honedge", "Doublade", "Aegislash"], 4),
        # decoys: real Metal Pokémon and real cards from this deck that are NOT named
        # on Weaponized Swords must contribute nothing.
        (["Steven's Beldum", "Genesect ex", "Basic Metal Energy", "Rare Candy"], 0),
        (["Honedge", "Steven's Metagross ex", "Aegislash", "Basic Metal Energy"], 2),
    ):
        # Dragapult ex is [N] Dragon with NO printed Weakness at all, so these numbers
        # are the raw 60-per-card total with no W/R math in the way.
        st, a, b = fresh_state(db, defender="Dragapult ex")
        a.hand = [db.get(n) for n in hand_names]
        fx._weaponized_swords(ctx_for(st, a, b, source=a.active))
        check(b.active.damage == 60 * expected_revealed,
              f"hand {hand_names} must reveal {expected_revealed} and do "
              f"{60 * expected_revealed}, got {b.active.damage}")

    # --- 2. THE CENTRAL PROPERTY: the hand is byte-for-byte unchanged, and nothing
    #        reaches the discard pile. Revealing is not paying. ---
    st, a, b = fresh_state(db)
    hand_names = ["Honedge", "Doublade", "Aegislash", "Rare Candy", "Basic Metal Energy"]
    a.hand = [db.get(n) for n in hand_names]
    before_ids = [id(c) for c in a.hand]
    fx._weaponized_swords(ctx_for(st, a, b, source=a.active))
    check([c.name for c in a.hand] == hand_names,
          f"the hand must be UNCHANGED after a reveal, got {[c.name for c in a.hand]}")
    check([id(c) for c in a.hand] == before_ids,
          "the hand must be the same card objects in the same order — a reveal must not "
          "even reorder it")
    check(a.discard == [],
          f"a reveal must put NOTHING in the discard pile, got {[c.name for c in a.discard]}")
    check(a.deck == [], "a reveal must not touch the deck either")

    # --- 3. ...so the SAME hand keeps paying, turn after turn, forever. Three uses in
    #        a row off one hand, each for the full amount. ---
    st, a, b = fresh_state(db)
    a.hand = [db.get(n) for n in ("Honedge", "Honedge", "Doublade")]
    totals = []
    for _ in range(3):
        b.active.damage = 0
        fx._weaponized_swords(ctx_for(st, a, b, source=a.active))
        totals.append(b.active.damage)
    check(totals == [180, 180, 180],
          f"the same 3-card hand must do 180 every time it is revealed, got {totals}")
    check(len(a.hand) == 3, f"and the hand must still hold 3 cards, got {len(a.hand)}")

    # --- 4. Weakness multiplies the WHOLE total once (not per revealed card): the
    #        engine applies 0 base for a '×' attack, so this effect owns the hit and
    #        pushes it through the W/R chokepoint a single time. Doublade is Metal;
    #        Charmander is Fire-weak... so pick a defender that IS weak to Metal. ---
    metal_weak = None
    for name in db.names():
        c = db.get(name)
        if (c.is_pokemon and any(t == "Metal" for t, _ in c.weaknesses)
                and (c.hp or 0) >= 200):
            metal_weak = name
            break
    if metal_weak is None:
        print("NOTE: no Metal-weak Pokémon in the pool — skipping the Weakness check")
    else:
        st, a, b = fresh_state(db, defender=metal_weak)
        a.hand = [db.get("Honedge"), db.get("Aegislash")]
        fx._weaponized_swords(ctx_for(st, a, b, source=a.active))
        check(b.active.damage == 240,
              f"2 revealed = 120 base, doubled ONCE by Weakness = 240 into {metal_weak}, "
              f"got {b.active.damage}")

    # --- 5. NEGATIVE: an empty reveal does nothing at all — no damage, no crash. ---
    st, a, b = fresh_state(db)
    a.hand = [db.get("Rare Candy")]
    fx._weaponized_swords(ctx_for(st, a, b, source=a.active))
    check(b.active.damage == 0,
          f"revealing nothing must do 0 damage, got {b.active.damage}")
    check([c.name for c in a.hand] == ["Rare Candy"], "and still not touch the hand")

    # --- 6. NEGATIVE: cards IN PLAY and IN THE DISCARD are not "in your hand" and must
    #        not count. Three Honedge on the Bench + two in the discard = 0 damage. ---
    st, a, b = fresh_state(db)
    a.hand = []
    a.bench = [InPlayPokemon(card=db.get("Honedge")) for _ in range(3)]
    a.discard = [db.get("Aegislash"), db.get("Doublade")]
    fx._weaponized_swords(ctx_for(st, a, b, source=a.active))
    check(b.active.damage == 0,
          f"only cards in HAND are revealed — bench/discard copies must do nothing, "
          f"got {b.active.damage}")

    # --- 7. END TO END through the real engine: legal_actions offers it, apply_action
    #        resolves it, and after a full attack the hand STILL holds every copy. This
    #        is the whole card working through the normal path, not just the effect fn. ---
    st, a, b = fresh_state(db)
    a.hand = [db.get(n) for n in ("Honedge", "Doublade", "Aegislash")]
    a.active.energy = [db.get("Basic Metal Energy"), db.get("Basic Psychic Energy")]
    a.deck = [db.get("Basic Metal Energy")] * 10
    b.deck = [db.get("Basic Psychic Energy")] * 10
    b.active.card = db.get("Dragapult ex")
    swings = [x for x in legal_actions(st)
              if x.kind == "attack"
              and a.active.card.attacks[x.attack_index].name == "Weaponized Swords"]
    check(len(swings) == 1,
          f"[C][C] paid by 2 attached Energy must make Weaponized Swords legal, "
          f"got {len(swings)} offers")
    if swings:
        apply_action(st, swings[0])
        check(b.active.damage == 180,
              f"3 revealed through the engine = 180, got {b.active.damage}")
        check(sorted(c.name for c in a.hand) == ["Aegislash", "Doublade", "Honedge"],
              f"after a REAL attack the hand must still hold all 3, got "
              f"{sorted(c.name for c in a.hand)}")
        check(a.discard == [],
              f"and the discard must still be empty, got {[c.name for c in a.discard]}")
        log = "\n".join(st.log)
        check("Weaponized Swords: revealed 3" in log,
              f"the reveal must be visible in the game log, got:\n{log}")
        check("STAY in hand" in log,
              "the log line must record that the revealed cards stayed in hand")

    # --- 8. and there is no cooldown: the very next turn it swings for 180 again. ---
        st.phase = Phase.MAIN
        st.active_index = 1
        start_turn(st)              # B's turn
        st.active_index = 0
        start_turn(st)              # back to A
        b.active.damage = 0
        swings2 = [x for x in legal_actions(st)
                   if x.kind == "attack"
                   and a.active.card.attacks[x.attack_index].name == "Weaponized Swords"]
        check(len(swings2) == 1, "Weaponized Swords has no cooldown — offer it again")
        if swings2:
            apply_action(st, swings2[0])
            check(b.active.damage >= 180,
                  f"the next turn's swing must still find at least the same 3 cards in "
                  f"hand (it may have drawn more), got {b.active.damage}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_weaponized_swords.py: all checks passed — 60 per revealed "
          "Honedge/Doublade/Aegislash, Weakness applied once to the total, and the "
          "revealed cards provably STAY in hand (reusable every turn, nothing discarded)")


if __name__ == "__main__":
    main()
