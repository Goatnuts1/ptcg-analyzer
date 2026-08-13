#!/usr/bin/env python3
"""
test_slowking_annihilape.py — the Slowking/Annihilape ladder additions:

- Annihilape's Destined Fight ("Both Active Pokémon are Knocked Out"): an
  effect-KO on both Actives, opponent side gated by effect-prevention, prizes
  (incl. the MEGA 3-prize rule) left to process_knockouts.
- Seek Inspiration's SEEK_VALUE_OVERRIDES: a discarded Annihilape must copy
  Destined Fight (override 400), not Tantrum (printed 130).
- Annihilape's Tantrum: 130 (engine) + SELF-confuse.
- Smoochum's Delightful Kiss: search up to 2 Basic Psychic Energy, both onto
  ONE Benched Pokémon.
- Shaymin (DRI)'s Flower Curtain: prevents attack damage to the owner's
  benched non-Rule-Box Pokémon from the OPPONENT's attacks only.
- Academy at Night: activated Stadium action — once per turn, put a hand card
  on top of the deck.

Run: python3 tests/test_slowking_annihilape.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import effects as fx
from src.engine.game import Action, legal_actions, apply_action, start_turn


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db, rng=st.rng)


def give_prizes(db, p, n=6):
    p.prizes = [db.get("Basic Psychic Energy") for _ in range(n)]


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # --- 1. Destined Fight KOs BOTH Actives, regardless of HP/energy. ---
    st, a, b = fresh_state(db)
    ape = InPlayPokemon(card=db.get("Annihilape"))
    mega = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.active, b.active = ape, mega
    give_prizes(db, a); give_prizes(db, b)
    fx._destined_fight(ctx_for(st, a, b, source=ape))
    check(ape.is_knocked_out, "Destined Fight must KO the user's own Active")
    check(mega.is_knocked_out, "Destined Fight must KO the opponent's Active (HP ignored)")

    # --- 2. process_knockouts awards prizes for both: 3 for the Mega, 1 for Annihilape. ---
    a_prizes_before, b_prizes_before = len(a.prizes), len(b.prizes)
    fx.process_knockouts(st)
    check(a_prizes_before - len(a.prizes) == 3,
          f"KOing a Mega must award 3 prizes (took {a_prizes_before - len(a.prizes)})")
    check(b_prizes_before - len(b.prizes) == 1,
          f"self-KO of Annihilape must award the opponent 1 prize "
          f"(took {b_prizes_before - len(b.prizes)})")

    # --- 3. Seek Inspiration picks Destined Fight over Tantrum (value override). ---
    st, a, b = fresh_state(db)
    slowking = InPlayPokemon(card=db.get("Slowking"))
    target = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    a.active, b.active = slowking, target
    give_prizes(db, a); give_prizes(db, b)
    a.deck = [db.get("Annihilape")]
    fx._seek_inspiration(ctx_for(st, a, b, source=slowking))
    check(slowking.is_knocked_out,
          "copied Destined Fight must KO Slowking itself (not Tantrum's self-confuse)")
    check(target.is_knocked_out, "copied Destined Fight must KO the opponent's Active")
    check(not slowking.confused, "Slowking must have copied Destined Fight, NOT Tantrum")

    # --- 4. Tantrum self-confuses the attacker. ---
    st, a, b = fresh_state(db)
    ape = InPlayPokemon(card=db.get("Annihilape"))
    a.active = ape
    b.active = InPlayPokemon(card=db.get("Slowpoke"))
    fx._tantrum(ctx_for(st, a, b, source=ape))
    check(ape.confused, "Tantrum must confuse the ATTACKER itself")
    check(not b.active.confused, "Tantrum must not confuse the Defending Pokémon")

    # --- 5. Delightful Kiss: 2 Basic Psychic from deck onto ONE benched Pokémon. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Smoochum"))
    slowpoke = InPlayPokemon(card=db.get("Slowpoke"))
    kyurem = InPlayPokemon(card=db.get("Kyurem"))
    a.bench = [slowpoke, kyurem]
    b.active = InPlayPokemon(card=db.get("Beldum"))
    a.deck = [db.get("Basic Psychic Energy"), db.get("Slowking"),
              db.get("Basic Psychic Energy"), db.get("Basic Psychic Energy")]
    fx._delightful_kiss(ctx_for(st, a, b, source=a.active))
    total_attached = slowpoke.energy_count() + kyurem.energy_count()
    check(total_attached == 2, f"Delightful Kiss must attach exactly 2 (got {total_attached})")
    check(slowpoke.energy_count() == 2 or kyurem.energy_count() == 2,
          "both cards must land on ONE benched Pokémon")
    check(sum(1 for c in a.deck if c.is_basic_energy and "Psychic" in c.types) == 1,
          "exactly 2 of the 3 deck copies must have been taken")

    # --- 6. Flower Curtain: benched non-Rule-Box protected from the opponent... ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Excadrill ex"))
    metang = InPlayPokemon(card=db.get("Metang"))
    shaymin = InPlayPokemon(card=db.get("Shaymin (DRI)"))
    benched_mega = InPlayPokemon(card=db.get("Genesect ex"))
    a.bench = [metang, shaymin, benched_mega]
    kyurem = InPlayPokemon(card=db.get("Kyurem"))
    b.active = kyurem
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=kyurem), metang, 110,
                                   owner=a, source=kyurem)
    check(dealt == 0 and metang.damage == 0,
          "Flower Curtain must prevent opponent attack damage to benched non-Rule-Box")
    # ...the Shaymin protects ITSELF (this print has no self-exception)...
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=kyurem), shaymin, 110,
                                   owner=a, source=kyurem)
    check(dealt == 0 and shaymin.damage == 0,
          "Flower Curtain must protect a benched Shaymin (DRI) itself")
    # ...but NOT a benched Rule-Box Pokémon... ---
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=kyurem), benched_mega, 110,
                                   owner=a, source=kyurem)
    check(dealt > 0 and benched_mega.damage > 0,
          "Flower Curtain must NOT protect a benched Rule-Box Pokémon")
    # ...and NOT the Active... ---
    dealt = fx.apply_attack_damage(ctx_for(st, b, a, source=kyurem), a.active, 110,
                                   owner=a, source=kyurem)
    check(dealt > 0, "Flower Curtain must NOT protect the Active")
    # ...and NOT against the owner's OWN attack's spread damage. ---
    own_src = InPlayPokemon(card=db.get("Kyurem"))
    a.bench.append(own_src)
    metang.damage = 0
    dealt = fx.apply_attack_damage(ctx_for(st, a, b, source=own_src), metang, 110,
                                   owner=a, source=own_src)
    check(dealt > 0, "Flower Curtain must NOT prevent damage from the owner's own Pokémon")

    # --- 7. Trifrost integration: vs a Flower Curtain board, the spread only
    # lands on Rule-Box / Active targets. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Slowpoke"))
    m1 = InPlayPokemon(card=db.get("Metang"))
    m2 = InPlayPokemon(card=db.get("Metang"))
    sh = InPlayPokemon(card=db.get("Shaymin (DRI)"))
    a.bench = [m1, m2, sh]
    kyurem = InPlayPokemon(card=db.get("Kyurem"))
    kyurem.energy = [db.get("Basic Psychic Energy")] * 2
    b.active = kyurem
    fx._trifrost(ctx_for(st, b, a, source=kyurem))
    check(m1.damage == 0 and m2.damage == 0,
          "Trifrost must be blanked on benched non-Rule-Box mons behind Flower Curtain")

    # --- 8. Academy at Night: activated action, once per turn, top-decks the card. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Slowking"))
    b.active = InPlayPokemon(card=db.get("Beldum"))
    st.stadium = db.get("Academy at Night")
    st.stadium_owner = 0
    a.hand = [db.get("Annihilape"), db.get("Switch")]
    a.deck = [db.get("Slowpoke")] * 4
    st.active_index = 0
    acts = [x for x in legal_actions(st) if x.kind == "stadium_academy"]
    check(len(acts) == 2, f"stadium_academy must be offered per hand card (got {len(acts)})")
    apply_action(st, Action("stadium_academy", hand_index=0))
    check(a.deck[0].name == "Annihilape", "the chosen hand card must go on TOP of the deck")
    check(len(a.hand) == 1, "the planted card must leave the hand")
    check(a.stadium_academy_used_this_turn, "the once-per-turn budget must be consumed")
    acts = [x for x in legal_actions(st) if x.kind == "stadium_academy"]
    check(len(acts) == 0, "stadium_academy must not be offered twice in a turn")

    # --- 9. The planted card is exactly what Seek Inspiration now eats. ---
    fx._seek_inspiration(ctx_for(st, a, b, source=a.active))
    check(b.active.is_knocked_out,
          "planted Annihilape -> Seek Inspiration must copy Destined Fight and KO the "
          "opponent's Active")

    if fails:
        print("FAILURES:")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_slowking_annihilape: all checks passed")


if __name__ == "__main__":
    main()
