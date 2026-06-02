#!/usr/bin/env python3
"""
test_mcts.py — clone/determinize correctness (fast) + MCTS strength vs greedy.

Run from project root:
    python3 tests/test_mcts.py
    python3 tests/test_mcts.py --fast   # skip the slow strength check

The strength check plays real games (≈30-40s); the correctness checks are instant.
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import load_test_decks
from src.engine.agents import GreedyAgent
from src.engine.mcts import MCTSAgent, determinize
from src.engine.run import play_game, setup_game
from src.engine.game import start_turn


def correctness_checks(db):
    fails = []

    def check(c, m):
        if not c:
            fails.append(m)

    deck_a, deck_b = load_test_decks(db)
    st = setup_game(deck_a, deck_b, seed=7, db=db)
    start_turn(st)

    # --- clone independence: mutating a clone must not touch the original ---
    snap = st.clone()
    orig_hand = len(st.current.hand)
    snap.current.hand.append(snap.current.deck.pop(0))      # mutate the clone
    if snap.current.active:
        snap.current.active.damage += 50
    check(len(st.current.hand) == orig_hand, "clone shares hand list with original")
    check(st.current.active is None or st.current.active.damage == 0,
          "clone shares InPlayPokemon with original")

    # --- clone shares immutable Card refs (cheap copy, not deepcopy) ---
    if st.current.active:
        check(st.clone().current.active.card is st.current.active.card,
              "clone should SHARE Card objects, not duplicate them")

    # --- determinization conserves cards and preserves known info ---
    me = st.active_index
    before_counts = _card_multiset(st)
    d = determinize(st, me, random.Random(1))
    after_counts = _card_multiset(d)
    check(before_counts == after_counts,
          "determinize must conserve the exact multiset of cards in play")
    # the root player's hand is KNOWN -> must be unchanged
    check(sorted(c.name for c in d.players[me].hand)
          == sorted(c.name for c in st.players[me].hand),
          "determinize must not alter the acting player's own hand")
    # public zones unchanged: both discards and in-play
    for i in (0, 1):
        check(len(d.players[i].discard) == len(st.players[i].discard),
              f"determinize changed P{i} discard size")
        check(len(d.players[i].prizes) == len(st.players[i].prizes),
              f"determinize changed P{i} prize count")
        check(len(d.players[i].hand) == len(st.players[i].hand),
              f"determinize changed P{i} hand size")

    # --- zone integrity (the real invariant from R6 review): public zones must
    #     be byte-identical, and resampled cards must come only from each
    #     player's OWN pool (no card teleporting between players). Prizes ARE
    #     allowed to resample (their contents are hidden); pinning them would
    #     leak hidden info, so we do NOT assert prize identity. ---
    for i in (0, 1):
        # discard identical (same cards, same order — it's public, untouched)
        check([c.name for c in d.players[i].discard] == [c.name for c in st.players[i].discard],
              f"determinize must not touch P{i} discard contents")
        # in-play identical: same Pokémon, same attached energy
        for m_d, m_s in zip(d.players[i].all_in_play(), st.players[i].all_in_play()):
            check(m_d.card.name == m_s.card.name,
                  f"determinize changed P{i} in-play Pokémon")
            check(sorted(e.name for e in m_d.energy) == sorted(e.name for e in m_s.energy),
                  f"determinize changed P{i} attached energy")
        # per-player conservation: the multiset of THAT player's cards is identical
        check(_player_multiset(d.players[i]) == _player_multiset(st.players[i]),
              f"determinize must conserve P{i}'s own card pool (no cross-player leak)")
    return fails


def _card_multiset(state):
    """Every card across all of one game's zones, both players, as a sorted list."""
    names = []
    for p in state.players:
        for z in (p.deck, p.hand, p.discard, p.prizes):
            names += [c.name for c in z]
        for m in p.all_in_play():
            names.append(m.card.name)
            names += [e.name for e in m.energy]
            names += [c.name for c in m.evolved_from]
    return sorted(names)


def _player_multiset(p):
    """Every card belonging to one player, across all their zones."""
    names = []
    for z in (p.deck, p.hand, p.discard, p.prizes):
        names += [c.name for c in z]
    for m in p.all_in_play():
        names.append(m.card.name)
        names += [e.name for e in m.energy]
        names += [c.name for c in m.evolved_from]
    return sorted(names)


def strength_check(db):
    """MCTS must beat greedy across mirrored seats. Deterministic (fixed seeds).
    Measured at 61% combined; threshold set conservatively below that."""
    deck_a, deck_b = load_test_decks(db)
    N, ITER = 18, 110
    wins = 0
    for s in range(N):
        st = play_game(deck_a, deck_b,
                       MCTSAgent(iterations=ITER, rollout="greedy", rng=random.Random(s)),
                       GreedyAgent(random.Random(s + 5000)), seed=s, db=db)
        if st.winner == 0:
            wins += 1
        st = play_game(deck_a, deck_b,
                       GreedyAgent(random.Random(s + 5000)),
                       MCTSAgent(iterations=ITER, rollout="greedy", rng=random.Random(s)),
                       seed=s, db=db)
        if st.winner == 1:
            wins += 1
    rate = wins / (2 * N)
    return rate


def main():
    fast = "--fast" in sys.argv
    db = CardDB.from_pool("data/standard_pool.json")

    fails = correctness_checks(db)
    if fails:
        print(f"FAIL — clone/determinize ({len(fails)}):")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("OK — clone & determinize correctness holds.")

    if fast:
        print("(skipped strength check)")
        return

    rate = strength_check(db)
    if rate <= 0.55:
        print(f"FAIL — MCTS beat greedy only {rate:.0%} (expected >55%)")
        sys.exit(1)
    print(f"OK — MCTS beats greedy {rate:.0%} across mirrored seats.")


if __name__ == "__main__":
    main()
