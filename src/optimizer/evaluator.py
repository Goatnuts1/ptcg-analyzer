#!/usr/bin/env python3
"""
evaluator.py — Score a candidate deck by playing simulated games.

HONESTY CAVEAT: every number this produces rests on the deterministic engine
in src/engine/. That engine's fidelity has NOT been validated against real
tournament results to within the margin we'd need to trust deck-edge claims
(the Dragapult mirror sim sits ~58% vs a published ~84%). For tractability MCTS
here also runs at a *reduced* iteration budget, so the agent is weaker than the
full search. Treat win-rates as relative signal between candidate decks under a
fixed, imperfect model — NOT as predicted real-world win rates.
"""

import random
from collections import Counter
from typing import List

from ..engine.cards import CardDB, Card
from ..engine.run import play_game
from ..engine.agents import GreedyAgent
from ..engine.legality import validate_deck
from .types import Decklist, EvalResult

# Reduced MCTS budget for optimizer throughput (full default is 160 ≈ 1 game/s).
OPTIMIZER_MCTS_ITERATIONS = 40


def _to_recipe(cards: List[str]) -> List[tuple]:
    """Collapse a 60-entry name list (with multiplicity) into [(name, count), ...]."""
    return list(Counter(cards).items())


def _to_card_list(cards: List[str], db: CardDB) -> List[Card]:
    """Expand a name list into engine Card objects. Raises on unknown names."""
    return [db.get(name) for name in cards]


def _make_agent(use_mcts: bool, rng: random.Random):
    if use_mcts:
        # Imported lazily so a greedy-only run never pays the mcts import cost.
        from ..engine.mcts import MCTSAgent
        return MCTSAgent(iterations=OPTIMIZER_MCTS_ITERATIONS, rollout="greedy", rng=rng)
    return GreedyAgent(rng)


def evaluate_deck(deck: List[str], opponents: List[Decklist], db: CardDB,
                  num_games: int = 200, use_mcts: bool = True) -> EvalResult:
    """
    Play `num_games` (split across the opponent set, seats mirrored) and return
    aggregate win/loss/tie stats for `deck`.

    Illegal candidate decks are NOT silently played: a deck that fails
    validate_deck scores 0% with the errors recorded in metadata, so the
    optimizer's selection pressure pushes toward legal lists.
    """
    legality_errors = validate_deck(db, _to_recipe(deck))
    if legality_errors:
        return EvalResult(
            deck=deck, win_rate=0.0, avg_turns=0.0,
            wins=0, losses=0, ties=0,
            metadata={"illegal": True, "errors": legality_errors[:10]},
        )

    if not opponents:
        raise ValueError("evaluate_deck requires at least one opponent deck")

    cand_cards = _to_card_list(deck, db)
    opp_card_lists = [_to_card_list(o.cards, db) for o in opponents]

    wins = losses = ties = 0
    turns_total = 0
    games_played = 0

    # Spread games evenly over opponents; mirror seats to cancel first-player bias.
    per_opp = max(1, num_games // len(opponents))
    base = random.Random(0xC0FFEE)  # fixed → reproducible scoring across candidates

    for opp_cards in opp_card_lists:
        for g in range(per_opp):
            s = base.randint(0, 2**31 - 1)
            cand_first = (g % 2 == 0)  # alternate which seat the candidate takes
            rng_a, rng_b = random.Random(s), random.Random(s + 1)

            if cand_first:
                a_cards, b_cards = cand_cards, opp_cards
                cand_seat = 0
            else:
                a_cards, b_cards = opp_cards, cand_cards
                cand_seat = 1

            st = play_game(
                a_cards, b_cards,
                _make_agent(use_mcts, rng_a),
                _make_agent(use_mcts, rng_b),
                seed=s, db=db,
            )

            games_played += 1
            turns_total += st.turn_number
            if st.winner is None:
                ties += 1
            elif st.winner == cand_seat:
                wins += 1
            else:
                losses += 1

    win_rate = wins / games_played if games_played else 0.0
    avg_turns = turns_total / games_played if games_played else 0.0
    return EvalResult(
        deck=deck, win_rate=win_rate, avg_turns=avg_turns,
        wins=wins, losses=losses, ties=ties,
        metadata={"games": games_played, "use_mcts": use_mcts,
                  "mcts_iterations": OPTIMIZER_MCTS_ITERATIONS if use_mcts else 0},
    )
