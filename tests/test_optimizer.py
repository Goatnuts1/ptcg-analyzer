#!/usr/bin/env python3
"""
test_optimizer.py — smoke + integration tests for the deck-optimizer package.

These are fast structural/wiring tests. They do NOT validate that win-rates mean
anything about real Pokemon (the engine isn't tournament-validated) — they only
prove the optimizer loop binds correctly to the engine API and produces legal,
sensible artifacts. MCTS is kept off (use_mcts=False) and game counts tiny so the
suite stays in CI-time.

Run from project root:  python3 tests/test_optimizer.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.legality import is_deck_legal
from collections import Counter

from src.optimizer.decklists import get_sample_decks
from src.optimizer.meta import get_current_meta_targets
from src.optimizer.deck_generator import DeckMutator
from src.optimizer.evaluator import evaluate_deck
from src.optimizer.core import DeckOptimizer
from src.optimizer.report import OptimizerReport


def _recipe(cards):
    return list(Counter(cards).items())


def test_sample_decks_are_legal():
    db = CardDB.from_pool()
    decks = get_sample_decks()
    assert set(decks) == {"dragapult", "charizard"}
    for key, deck in decks.items():
        assert len(deck.cards) == 60, f"{key}: {len(deck.cards)} cards"
        assert is_deck_legal(db, _recipe(deck.cards)), f"{key} is not legal"
    print("ok  sample decks are legal 60s")


def test_mutator_keeps_decks_mostly_legal():
    db = CardDB.from_pool()
    mut = DeckMutator(db)
    base = get_sample_decks()["dragapult"].cards
    legal = 0
    n = 40
    for _ in range(n):
        d = mut.mutate_deck(base[:])
        assert len(d) == 60
        if is_deck_legal(db, _recipe(d)):
            legal += 1
    # Repair pass should keep the vast majority legal (mark/copy/ace caps).
    assert legal >= int(0.9 * n), f"only {legal}/{n} mutated decks legal"
    print(f"ok  mutator: {legal}/{n} mutations legal")


def test_evaluator_runs_and_scores():
    db = CardDB.from_pool()
    decks = get_sample_decks()
    cand = decks["dragapult"].cards
    res = evaluate_deck(cand, [decks["charizard"]], db, num_games=4, use_mcts=False)
    assert 0.0 <= res.win_rate <= 1.0
    assert res.wins + res.losses + res.ties == res.metadata["games"]
    assert res.metadata["games"] >= 1
    print(f"ok  evaluator: {res.win_rate:.0%} over {res.metadata['games']} games")


def test_evaluator_rejects_illegal_deck():
    db = CardDB.from_pool()
    decks = get_sample_decks()
    illegal = ["Rare Candy"] * 60  # >4 copies, wrong composition
    res = evaluate_deck(illegal, [decks["charizard"]], db, num_games=2, use_mcts=False)
    assert res.win_rate == 0.0 and res.metadata.get("illegal") is True
    print("ok  evaluator: illegal deck scored 0% with errors")


def test_optimize_end_to_end_tiny():
    db = CardDB.from_pool()
    target = get_current_meta_targets()[-1]  # Wild Card = greedy
    target.num_games_per_matchup = 4
    base = get_sample_decks()["dragapult"]
    opt = DeckOptimizer(db)
    with tempfile.TemporaryDirectory() as out:
        report = opt.optimize(base, target, generations=2, population_size=3, output_dir=out)
        assert isinstance(report, OptimizerReport)
        assert 0.0 <= report.win_rate <= 1.0
        assert len(report.final_deck) == 60
        assert os.path.isdir(out)
    print(f"ok  end-to-end: final {report.win_rate:.0%}, {report.generations} gens")


if __name__ == "__main__":
    test_sample_decks_are_legal()
    test_mutator_keeps_decks_mostly_legal()
    test_evaluator_runs_and_scores()
    test_evaluator_rejects_illegal_deck()
    test_optimize_end_to_end_tiny()
    print("\nALL OPTIMIZER SMOKE TESTS PASSED")
