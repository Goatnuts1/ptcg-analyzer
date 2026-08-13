#!/usr/bin/env python3
"""
test_area_zero_underdepths.py — Area Zero Underdepths (SCR 131, Stadium), asserted
against its exact printed text:

  "Each player who has any Tera Pokémon in play can have up to 8 Pokémon on their
   Bench. If a player no longer has any Tera Pokémon in play, that player discards
   Pokémon from their Bench until they have 5. When this card leaves play, both
   players discard Pokémon from their Bench until they have 5, and the player who
   played this card discards first."

This used to be a recorded NOT-modeled limitation (the Bench cap was the fixed
constant PlayerState.MAX_BENCH = 5, asserted as such in
tests/test_slowking_ogerpon_trainers.py §9b). It is now a real engine hook:
`effects.bench_limit(state, player)` is consulted at every Bench-placement site and
`effects.enforce_bench_limits(state, first_index)` runs both shrink clauses.

WHAT IS AND IS NOT COVERED — stated precisely:
  - COVERED: the +3 cap is PER PLAYER and SYMMETRIC (either player gets it from the
    one Stadium, gated on that player's OWN Tera Pokémon in play); it applies to
    manual benching AND to every search/recover effect that puts Pokémon on the
    Bench; both shrink clauses fire, and the discard-first ordering is honored.
  - NOT COVERED: nothing in this card. The v0 CHOICE POLICY for "discards Pokémon
    from their Bench" is to drop the newest (last-benched) Pokémon first — the card
    lets the player choose, and this engine does not model that choice.

Run: python3 tests/test_area_zero_underdepths.py
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


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5
    return st, a, b


def ctx_for(st, me, opp, source=None, kind="trainer"):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source, db=st.db,
                            rng=st.rng, effect_kind=kind)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")
    area_zero = db.get("Area Zero Underdepths")
    tera = db.get("Teal Mask Ogerpon ex")          # Tera
    plain = db.get("Latias ex")                     # ex, NOT Tera
    filler = db.get("Pikipek")

    check("Stadium" in area_zero.subtypes, "Area Zero Underdepths must be a Stadium")
    check("Tera" in tera.subtypes, "setup: Teal Mask Ogerpon ex must be Tera-typed")
    check("Tera" not in plain.subtypes, "setup: Latias ex must NOT be Tera-typed")
    check("Area Zero Underdepths" in fx.STADIUM_IMPLEMENTED,
          "Area Zero Underdepths must now be recorded as an implemented Stadium")

    # ----------------------------------------------------------------- #
    # 1. bench_limit — the cap itself.
    # ----------------------------------------------------------------- #
    # 1a. no Stadium at all -> the default 5, Tera or not.
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=tera)
    check(fx.bench_limit(st, a) == 5,
          f"with no Stadium in play the cap is 5 even with a Tera Pokémon, got "
          f"{fx.bench_limit(st, a)}")

    # 1b. Area Zero in play + a Tera Pokémon -> 8, for BOTH players independently.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    a.active = InPlayPokemon(card=tera)
    b.active = InPlayPokemon(card=plain)
    check(fx.bench_limit(st, a) == 8,
          f"the player WITH a Tera Pokémon gets 8, got {fx.bench_limit(st, a)}")
    check(fx.bench_limit(st, b) == 5,
          f"the player WITHOUT a Tera Pokémon stays at 5, got {fx.bench_limit(st, b)}")

    # 1c. SYMMETRIC: the opponent gets it too, even though player 0 played the card.
    b.bench = [InPlayPokemon(card=tera)]
    check(fx.bench_limit(st, b) == 8,
          "Area Zero Underdepths says EACH player — the opponent gets 8 as soon as they "
          "have a Tera Pokémon in play, regardless of who played the Stadium")

    # 1d. a Tera on the BENCH counts as "in play" just like an Active one.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    a.active = InPlayPokemon(card=plain)
    a.bench = [InPlayPokemon(card=tera)]
    check(fx.bench_limit(st, a) == 8, "a Benched Tera Pokémon is 'in play'")

    # 1e. NEGATIVE: a DIFFERENT Stadium does nothing.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = db.get("Nighttime Mine"), 0
    a.active = InPlayPokemon(card=tera)
    check(fx.bench_limit(st, a) == 5,
          "only Area Zero Underdepths raises the Bench cap")

    # 1f. the constant itself is untouched — it is now only the DEFAULT.
    check(PlayerState.MAX_BENCH == 5,
          "PlayerState.MAX_BENCH stays 5; the per-player rule lives in fx.bench_limit")

    # ----------------------------------------------------------------- #
    # 2. The cap is honored where Pokémon actually reach the Bench.
    # ----------------------------------------------------------------- #
    # 2a. legal_actions offers a 6th manual bench play under Area Zero + Tera.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    st.active_index = 0
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(5)]
    a.hand = [filler]
    b.active = InPlayPokemon(card=plain)
    kinds = [act.kind for act in game.legal_actions(st)]
    check("play_basic" in kinds,
          "with Area Zero + a Tera Pokémon, a 6th Basic must still be benchable")

    # 2b. NEGATIVE: same board WITHOUT the Tera Pokémon -> the 6th is not offered.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    st.active_index = 0
    a.active = InPlayPokemon(card=plain)               # no Tera anywhere
    a.bench = [InPlayPokemon(card=filler) for _ in range(5)]
    a.hand = [filler]
    b.active = InPlayPokemon(card=plain)
    kinds = [act.kind for act in game.legal_actions(st)]
    check("play_basic" not in kinds,
          "without a Tera Pokémon the cap is 5 — no 6th bench play may be offered")

    # 2c. search-to-Bench effects respect the raised cap (this is the case the old
    #     recorded limitation asserted could NOT happen).
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(5)]
    a.deck = [db.get("Hoothoot (SCR)")]
    found = fx.search_deck(ctx_for(st, a, b), [fx.p_basic_pokemon], dest="bench")
    check(found == 1 and len(a.bench) == 6,
          f"a Bench search must be able to fill slot 6 under Area Zero + Tera, got "
          f"found={found} bench={len(a.bench)}")

    # 2d. and it still stops at 8, not 9.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(8)]
    a.deck = [db.get("Hoothoot (SCR)")]
    found = fx.search_deck(ctx_for(st, a, b), [fx.p_basic_pokemon], dest="bench")
    check(found == 0 and len(a.bench) == 8,
          f"8 is the cap — a 9th must never be placed, got found={found} "
          f"bench={len(a.bench)}")

    # ----------------------------------------------------------------- #
    # 3. Shrink clause 1: "If a player no longer has any Tera Pokémon in play, that
    #    player discards Pokémon from their Bench until they have 5."
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(8)]
    b.active = InPlayPokemon(card=plain)
    fx.enforce_bench_limits(st)
    check(len(a.bench) == 8, "while the Tera Pokémon is in play the 8 Bench stays")

    # the Tera Pokémon is Knocked Out -> the sweep shrinks the Bench to 5.
    a.active.damage = 999
    game_before = len(a.discard)
    fx.process_knockouts(st)
    check(len(a.bench) == 5,
          f"once the last Tera Pokémon leaves play the Bench must shrink to 5, got "
          f"{len(a.bench)}")
    check(len(a.discard) > game_before,
          "the discarded Bench Pokémon must actually go to the discard pile")

    # 3b. the discard is NOT a Knock Out: no prizes change hands for it. (A fresh
    #     board, shrunk by removing the Tera by hand rather than by KO.)
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(8)]
    b.prizes = [filler] * 6
    a.active = InPlayPokemon(card=plain)   # the Tera Pokémon is simply gone
    fx.enforce_bench_limits(st)
    check(len(a.bench) == 5, f"Bench must shrink to 5, got {len(a.bench)}")
    check(len(b.prizes) == 6,
          f"discarding Bench Pokémon to a Stadium clause is NOT a KO — the opponent "
          f"must take 0 prizes, got {6 - len(b.prizes)} taken")

    # 3c. everything attached leaves with it.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    a.active = InPlayPokemon(card=plain)                       # no Tera -> cap 5
    doomed = InPlayPokemon(card=db.get("Trumbeak"),
                           energy=[db.get("Basic Grass Energy")],
                           evolved_from=[db.get("Pikipek")])
    doomed.tool = db.get("Air Balloon")
    a.bench = [InPlayPokemon(card=filler) for _ in range(5)] + [doomed]
    fx.enforce_bench_limits(st)
    names = [c.name for c in a.discard]
    check(len(a.bench) == 5, "the 6th Bench Pokémon must be discarded")
    for expected in ("Trumbeak", "Pikipek", "Basic Grass Energy", "Air Balloon"):
        check(expected in names,
              f"{expected} must go to the discard with the Bench Pokémon, got {names}")

    # ----------------------------------------------------------------- #
    # 4. Shrink clause 2: "When this card leaves play, both players discard Pokémon
    #    from their Bench until they have 5, and the player who played this card
    #    discards first."
    # ----------------------------------------------------------------- #
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 0
    st.active_index = 1
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(8)]
    b.active = InPlayPokemon(card=tera)
    b.bench = [InPlayPokemon(card=filler) for _ in range(7)]
    b.hand = [db.get("Nighttime Mine")]
    game.apply_action(st, Action("play_stadium", hand_index=0))
    check(st.stadium.name == "Nighttime Mine",
          "the replacement Stadium must be installed")
    check(len(a.bench) == 5 and len(b.bench) == 5,
          f"when Area Zero leaves play BOTH benches shrink to 5, got A={len(a.bench)} "
          f"B={len(b.bench)}")
    # "the player who played this card discards first" — player 0 played Area Zero, so
    # their discard lines must precede player 1's.
    shrink_lines = [ln for ln in st.log if "Area Zero Underdepths:" in ln]
    check(len(shrink_lines) == 5,
          f"expected 5 Bench discards logged (3 from A, 2 from B), got "
          f"{len(shrink_lines)}: {shrink_lines}")
    check(shrink_lines and "Area Zero Underdepths: A " in shrink_lines[0],
          f"player 0 played Area Zero, so player 0 must discard FIRST; first log line "
          f"was {shrink_lines[0] if shrink_lines else None!r}")

    # 4b. the same, with the OTHER player as the Stadium's owner -> they go first.
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = area_zero, 1
    st.active_index = 0
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(8)]
    b.active = InPlayPokemon(card=tera)
    b.bench = [InPlayPokemon(card=filler) for _ in range(8)]
    a.hand = [db.get("Nighttime Mine")]
    game.apply_action(st, Action("play_stadium", hand_index=0))
    shrink_lines = [ln for ln in st.log if "Area Zero Underdepths:" in ln]
    check(shrink_lines and "Area Zero Underdepths: B " in shrink_lines[0],
          f"player 1 played Area Zero, so player 1 must discard FIRST; first log line "
          f"was {shrink_lines[0] if shrink_lines else None!r}")
    check(len(a.bench) == 5 and len(b.bench) == 5,
          f"both benches must end at 5, got A={len(a.bench)} B={len(b.bench)}")

    # 4c. NEGATIVE: replacing a NON-Area-Zero Stadium shrinks nothing (nobody was
    #     ever over 5, and no spurious discards may be logged).
    st, a, b = fresh_state(db)
    st.stadium, st.stadium_owner = db.get("Nighttime Mine"), 0
    st.active_index = 0
    a.active = InPlayPokemon(card=tera)
    a.bench = [InPlayPokemon(card=filler) for _ in range(5)]
    b.active = InPlayPokemon(card=plain)
    a.hand = [area_zero]
    game.apply_action(st, Action("play_stadium", hand_index=0))
    check(len(a.bench) == 5 and not any("Area Zero Underdepths:" in ln for ln in st.log),
          "playing Area Zero must never discard anything by itself")
    check(fx.bench_limit(st, a) == 8,
          "and once it is in play the cap is immediately 8 for the Tera player")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_area_zero_underdepths.py: all checks passed — the per-player 8-Bench "
          "cap, both shrink clauses, and the discards-first ordering all match the text")


if __name__ == "__main__":
    main()
