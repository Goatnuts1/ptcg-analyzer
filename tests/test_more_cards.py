#!/usr/bin/env python3
"""
test_more_cards.py — the feature/more-cards archetypes (Mega Gardevoir / Colorless /
Fire + Tapu Koko). Each new effect is asserted against its printed card text.

Covers: Ralts (Collect), Kirlia (Call Sign), Mega Gardevoir ex (Overflowing Wishes,
Mega Symphonia), Mega Diancie ex (Garland Ray), Iron Crown ex (Twin Shotels),
Latias ex (Eon Blade + the can't-attack-next-turn lock), Lugia ex (Hyper Whirlpool),
Snorlax ex (Toss-and-Turn Press), Cyclizar ex (Break Through, Zircon Road),
Mega Kangaskhan ex (Run Errand, Rapid-Fire Combo), Terapagos ex (Unified Beatdown),
Reshiram ex (Scorching Fire), Volcanion ex (Scorching Cyclone), Ethan's Ho-Oh ex
(Shining Feathers), Tapu Koko ex (Linked Lightning).

Run from project root:  python3 tests/test_more_cards.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine.game import setup_game, start_turn, legal_actions
from src.engine import effects as fx


def fresh(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx(st, me, opp, source=None, rng=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=rng or st.rng)


class _SeqCoin:
    """Scripted coin: randint(0,1) returns the next value in `seq`, then 0 (tails)
    forever. Lets 'flip until tails' / 'flip 3' tests be deterministic."""
    def __init__(self, seq): self._seq = list(seq); self._i = 0
    def randint(self, a, b):
        v = self._seq[self._i] if self._i < len(self._seq) else 0
        self._i += 1
        return v
    def shuffle(self, seq): pass
    def random(self): return 0.0


def expected_dmg(attacker, defender, raw):
    """Mirror the engine's Weakness math so damage assertions are exact."""
    if raw <= 0:
        return 0
    if attacker.types and defender.types:
        for w, _ in defender.weaknesses:
            if w == attacker.types[0]:
                return raw * 2
    return raw


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    DREEPY = db.get("Dreepy")
    PSY = db.get("Basic Psychic Energy")
    FIRE = db.get("Basic Fire Energy")
    WATER = db.get("Basic Water Energy")

    def defender(b, card_name="Dreepy"):
        b.active = InPlayPokemon(card=db.get(card_name))
        return b.active

    # --- Ralts: Collect — draw a card. ---
    st, a, b = fresh(db)
    a.deck = [DREEPY] * 3
    fx._collect(ctx(st, a, b))
    check(len(a.hand) == 1, f"Collect: draw 1 (hand={len(a.hand)})")

    # --- Kirlia: Call Sign — search up to 3 Pokémon to hand. ---
    st, a, b = fresh(db)
    a.deck = [DREEPY, DREEPY, DREEPY, PSY, FIRE]
    fx._call_sign(ctx(st, a, b))
    check(a.hand.count(DREEPY) == 3, f"Call Sign: fetch 3 Pokémon (got {a.hand.count(DREEPY)})")

    # --- Mega Gardevoir ex: Overflowing Wishes — a Basic Psychic to each Benched. ---
    st, a, b = fresh(db)
    a.bench = [InPlayPokemon(card=DREEPY), InPlayPokemon(card=DREEPY)]
    a.deck = [PSY, PSY, PSY, FIRE]
    fx._overflowing_wishes(ctx(st, a, b))
    check(all(any(e is PSY or e.name == PSY.name for e in m.energy) for m in a.bench),
          "Overflowing Wishes: a Psychic Energy attached to each benched Pokémon")
    check(sum(len(m.energy) for m in a.bench) == 2, "exactly one per bench Pokémon")

    # --- Mega Gardevoir ex: Mega Symphonia — 50 per Psychic Energy on your Pokémon. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Mega Gardevoir ex"), energy=[PSY, PSY])
    a.active = src
    a.bench = [InPlayPokemon(card=DREEPY, energy=[PSY])]      # 3 Psychic total
    d = defender(b)
    fx._mega_symphonia(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 150),
          f"Mega Symphonia: 50×3 = 150 (got {d.damage})")

    # --- Mega Diancie ex: Garland Ray — discard up to 2 Energy, 120 each. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Mega Diancie ex"), energy=[PSY, PSY, PSY])
    a.active = src
    d = defender(b)
    fx._garland_ray(ctx(st, a, b, source=src))
    check(len(src.energy) == 1 and a.discard.count(PSY) == 2,
          f"Garland Ray: discard 2 Energy (left {len(src.energy)})")
    check(d.damage == expected_dmg(src.card, d.card, 240), f"Garland Ray: 120×2 = 240 (got {d.damage})")

    # --- Iron Crown ex: Twin Shotels — 50 to 2 of the opponent's Pokémon. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Iron Crown ex"))
    a.active = src
    b.active = InPlayPokemon(card=DREEPY)
    b.bench = [InPlayPokemon(card=DREEPY), InPlayPokemon(card=DREEPY)]
    fx._twin_shotels(ctx(st, a, b, source=src))
    hit = sum(1 for m in ([b.active] + b.bench) if m.damage == 50)
    check(hit == 2, f"Twin Shotels: exactly 2 Pokémon take 50 (got {hit})")

    # --- Latias ex: Eon Blade — sets the can't-attack-next-turn lock. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Latias ex"))
    fx._eon_blade(ctx(st, a, b, source=src))
    check(src.pending_cannot_attack, "Eon Blade: pending_cannot_attack set")

    # --- the lock actually blocks attacking on the owner's next turn (engine-level) ---
    st = setup_game([db.get("Latias ex")] + [PSY] * 59,
                    [DREEPY] + [WATER] * 59, seed=1, db=db)
    start_turn(st)
    p0 = st.players[0]
    p0.active.energy = [PSY, PSY, PSY]          # can pay Eon Blade (PPC)
    p0.active.pending_cannot_attack = True       # simulate having used Eon Blade last turn
    # advance: opponent's turn, then back to player 0
    from src.engine.game import end_turn
    end_turn(st); start_turn(st)                 # P1
    end_turn(st); start_turn(st)                 # back to P0 — lock should now be active
    check(p0.active.cannot_attack, "lock active on owner's next turn")
    acts = legal_actions(st)
    check(not any(x.kind == "attack" for x in acts),
          "no attack offered while cannot_attack is set")

    # --- Lugia ex: Hyper Whirlpool — flip until tails; discard opp Energy per heads. ---
    st, a, b = fresh(db)
    d = defender(b); d.energy = [WATER, WATER, WATER]
    fx._hyper_whirlpool(ctx(st, a, b, rng=_SeqCoin([1, 1, 0])))   # 2 heads
    check(len(d.energy) == 1 and b.discard.count(WATER) == 2,
          f"Hyper Whirlpool: 2 heads discard 2 Energy (left {len(d.energy)})")

    # --- Snorlax ex: Toss-and-Turn Press — flip 3, 120 per heads. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Snorlax ex"))
    a.active = src
    d = defender(b)
    fx._toss_and_turn(ctx(st, a, b, source=src, rng=_SeqCoin([1, 1, 0])))  # 2 heads
    check(d.damage == expected_dmg(src.card, d.card, 240), f"Toss-and-Turn: 120×2 = 240 (got {d.damage})")

    # --- Cyclizar ex: Break Through — 30 to a Benched opponent (rider). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Cyclizar ex"))
    a.active = src
    b.active = InPlayPokemon(card=DREEPY)
    benched = InPlayPokemon(card=DREEPY)
    b.bench = [benched]
    fx._break_through(ctx(st, a, b, source=src))
    check(benched.damage == 30, f"Break Through: 30 to a benched Pokémon (got {benched.damage})")

    # --- Cyclizar ex: Zircon Road — draw 5 (rider). ---
    st, a, b = fresh(db)
    a.deck = [DREEPY] * 8
    fx._zircon_road(ctx(st, a, b))
    check(len(a.hand) == 5, f"Zircon Road: draw 5 (hand={len(a.hand)})")

    # --- Mega Kangaskhan ex: Run Errand — draw 2. ---
    st, a, b = fresh(db)
    a.deck = [DREEPY] * 3
    fx._run_errand(ctx(st, a, b))
    check(len(a.hand) == 2, f"Run Errand: draw 2 (hand={len(a.hand)})")

    # --- Mega Kangaskhan ex: Rapid-Fire Combo — 200 + 50 per heads. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Mega Kangaskhan ex"))
    a.active = src
    d = defender(b)
    fx._rapid_fire_combo(ctx(st, a, b, source=src, rng=_SeqCoin([1, 0])))   # 1 head
    check(d.damage == expected_dmg(src.card, d.card, 250), f"Rapid-Fire: 200+50 = 250 (got {d.damage})")

    # --- Terapagos ex: Unified Beatdown — 30 per Benched (yours). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Terapagos ex"))
    a.active = src
    a.bench = [InPlayPokemon(card=DREEPY) for _ in range(3)]
    d = defender(b)
    fx._unified_beatdown(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 90), f"Unified Beatdown: 30×3 = 90 (got {d.damage})")

    # --- Reshiram ex: Scorching Fire — discard an Energy from self (rider). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Reshiram ex"), energy=[FIRE, FIRE])
    a.active = src
    fx._scorching_fire(ctx(st, a, b, source=src))
    check(len(src.energy) == 1 and a.discard.count(FIRE) == 1,
          f"Scorching Fire: discard 1 self Energy (left {len(src.energy)})")

    # --- Volcanion ex: Scorching Cyclone — move an Energy from self to a Benched. ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Volcanion ex"), energy=[FIRE])
    a.active = src
    bench = InPlayPokemon(card=DREEPY)
    a.bench = [bench]
    fx._scorching_cyclone(ctx(st, a, b, source=src))
    check(len(src.energy) == 0 and len(bench.energy) == 1,
          "Scorching Cyclone: move 1 Energy to a benched Pokémon")

    # --- Ethan's Ho-Oh ex: Shining Feathers — heal 50 from each of your Pokémon. ---
    st, a, b = fresh(db)
    a.active = InPlayPokemon(card=DREEPY, damage=60)
    a.bench = [InPlayPokemon(card=DREEPY, damage=30)]
    fx._shining_feathers(ctx(st, a, b))
    check(a.active.damage == 10 and a.bench[0].damage == 0,
          f"Shining Feathers: heal 50 each (active={a.active.damage}, bench={a.bench[0].damage})")

    # --- Tapu Koko ex: Linked Lightning — 60 + 20 per Benched (yours). ---
    st, a, b = fresh(db)
    src = InPlayPokemon(card=db.get("Tapu Koko ex"))
    a.active = src
    a.bench = [InPlayPokemon(card=DREEPY), InPlayPokemon(card=DREEPY)]
    d = defender(b)
    fx._linked_lightning(ctx(st, a, b, source=src))
    check(d.damage == expected_dmg(src.card, d.card, 100), f"Linked Lightning: 60+20×2 = 100 (got {d.damage})")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — feature/more-cards (15 cards) all match card text: Mega Gardevoir line, "
          "Mega Diancie, Iron Crown, Latias (+ can't-attack lock), Lugia, Snorlax, Cyclizar, "
          "Mega Kangaskhan, Terapagos, Reshiram, Volcanion, Ethan's Ho-Oh, Tapu Koko.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
