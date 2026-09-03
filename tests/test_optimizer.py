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

import json
import os
import random
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
    # Old flags stay; August starters are required.
    for required in ("dragapult", "charizard", "mega_excadrill",
                     "dragapult_blaziken", "crustle_modern"):
        assert required in decks, required
    for key, deck in decks.items():
        assert len(deck.cards) == 60, f"{key}: {len(deck.cards)} cards"
        assert is_deck_legal(db, _recipe(deck.cards)), f"{key} is not legal"
    print(f"ok  sample decks are legal 60s ({len(decks)} starters)")


def test_mutator_keeps_decks_mostly_legal():
    db = CardDB.from_pool()
    mut = DeckMutator(db)
    base = get_sample_decks()["dragapult"].cards
    pool = set(mut.all_cards)
    legal = 0
    n = 40
    for _ in range(n):
        d = mut.mutate_deck(base[:])
        assert len(d) == 60
        extra = set(d) - pool
        assert not extra, f"mutator introduced unimplemented cards: {sorted(extra)[:8]}"
        if is_deck_legal(db, _recipe(d)):
            legal += 1
    # Repair pass should keep the vast majority legal (mark/copy/ace caps).
    assert legal >= int(0.9 * n), f"only {legal}/{n} mutated decks legal"
    print(f"ok  mutator: {legal}/{n} mutations legal, pool={len(pool)}")


def test_mutator_tech_pool_is_subtype_based():
    """The ex/MEGA pool is selected by SUBTYPE. The old filter substring-matched
    names against ["ex", "V", "ex ", "MEGA"], which swept in every capital-V name
    (a rotated mechanic) and every name containing the letters "ex"."""
    db = CardDB.from_pool()
    mut = DeckMutator(db)
    assert mut._tech_pool, "tech pool is empty"
    for name in mut._tech_pool:
        subtypes = set(db._by_name[name].subtypes)
        assert {"ex", "MEGA"} & subtypes, f"{name} is not an ex/MEGA card: {subtypes}"
    # And nothing eligible is missed.
    expected = {n for n in mut.all_cards
                if {"ex", "MEGA"} & set(db._by_name[n].subtypes)}
    assert set(mut._tech_pool) == expected
    print(f"ok  tech pool: {len(mut._tech_pool)} ex/MEGA cards by subtype")


def test_mutator_counts_move_both_directions():
    """_adjust_counts must be able to TRIM a line, not just add copies —
    otherwise counts only ever ratchet up and thinning a list is unreachable."""
    db = CardDB.from_pool()
    mut = DeckMutator(db)
    base = get_sample_decks()["mega_excadrill"].cards
    random.seed(7)
    up = down = 0
    for _ in range(300):
        before = Counter(base)
        after = Counter(mut._adjust_counts(base[:]))
        for name in set(before) | set(after):
            if after[name] > before[name]:
                up += 1
            elif after[name] < before[name]:
                down += 1
    assert up > 0, "_adjust_counts never increased a count"
    assert down > 0, "_adjust_counts never decreased a count"
    print(f"ok  adjust_counts moves both ways ({up} up / {down} down)")


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

        # Baseline: generation 1 re-scores the unmutated base deck, so every run
        # carries the starting list's win rate and the loop can only go up.
        assert report.base_win_rate is not None
        assert report.win_rate >= report.base_win_rate, (
            f"final {report.win_rate} below baseline {report.base_win_rate}")
        assert abs(report.improvement - (report.win_rate - report.base_win_rate)) < 1e-9

        # A change list that matches the two decklists it claims to diff.
        base_counts, final_counts = Counter(base.cards), Counter(report.final_deck)
        for name, before, after in report.changes():
            assert (before, after) == (base_counts[name], final_counts[name])
            assert before != after
        if not report.changes():
            assert final_counts == base_counts

        written = [f for f in os.listdir(out) if f.endswith(".json")]
        assert written, "no result JSON written"
        with open(os.path.join(out, written[0])) as fh:
            payload = json.load(fh)
        for key in ("base_win_rate", "win_rate", "improvement", "changes", "caveat"):
            assert key in payload, f"result JSON missing {key!r}"
    print(f"ok  end-to-end: {report.base_win_rate:.0%} -> {report.win_rate:.0%} "
          f"({report.improvement:+.0%}), {report.generations} gens, "
          f"{len(report.changes())} card(s) changed")


def test_optimize_rejects_degenerate_settings():
    db = CardDB.from_pool()
    target = get_current_meta_targets()[-1]
    base = get_sample_decks()["dragapult"]
    opt = DeckOptimizer(db)
    for kwargs in ({"generations": 0}, {"population_size": 0}):
        try:
            opt.optimize(base, target, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"optimize() accepted {kwargs}")
    print("ok  optimize() rejects 0 generations / 0 population")


if __name__ == "__main__":
    test_sample_decks_are_legal()
    test_mutator_keeps_decks_mostly_legal()
    test_mutator_tech_pool_is_subtype_based()
    test_mutator_counts_move_both_directions()
    test_evaluator_runs_and_scores()
    test_evaluator_rejects_illegal_deck()
    test_optimize_end_to_end_tiny()
    test_optimize_rejects_degenerate_settings()
    print("\nALL OPTIMIZER SMOKE TESTS PASSED")
