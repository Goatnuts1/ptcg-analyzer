#!/usr/bin/env python3
"""
deck_generator.py — Mutation strategies for creating new deck variations
"""

import random
from collections import Counter
from typing import List
from ..engine.cards import CardDB
from ..engine.legality import is_mark_legal, MAX_COPIES
from .types import Decklist


class DeckMutator:
    """Handles creating mutated versions of decks for optimization."""

    def __init__(self, db: CardDB):
        self.db = db
        # Only mutate toward cards that are legal in the current format, so the
        # mark-legality rule is satisfied by construction. (from_pool is already
        # standard-only, but we filter explicitly in case a wider db is passed.)
        self.all_cards = [n for n, c in db._by_name.items() if is_mark_legal(c)]
        self._basic_energy = {n for n, c in db._by_name.items() if c.is_basic_energy}
        self._ace_spec = {n for n, c in db._by_name.items() if "ACE SPEC" in c.subtypes}

    def generate_population(self, base_deck: List[str], size: int = 12) -> List[List[str]]:
        """Generate a population of varied decks."""
        population = [base_deck[:] for _ in range(size)]

        for i in range(1, size):  # keep index 0 as original
            population[i] = self.mutate_deck(population[i])

        return population

    def mutate_deck(self, deck: List[str]) -> List[str]:
        """Apply 1–4 random mutations to a deck."""
        new_deck = deck[:]
        num_mutations = random.randint(1, 4)

        for _ in range(num_mutations):
            roll = random.random()
            if roll < 0.35:
                new_deck = self._replace_random_card(new_deck)
            elif roll < 0.65:
                new_deck = self._add_tech_card(new_deck)
            elif roll < 0.85:
                new_deck = self._adjust_counts(new_deck)
            else:
                new_deck = self._swap_two_cards(new_deck)

        new_deck = self._repair_legality(new_deck)

        # Enforce exactly 60 cards
        while len(new_deck) > 60:
            new_deck.pop(random.randrange(len(new_deck)))
        while len(new_deck) < 60:
            new_deck.append(random.choice(self.all_cards))

        return new_deck

    def _repair_legality(self, deck: List[str]) -> List[str]:
        """Cap copies at MAX_COPIES (except basic energy) and ACE SPEC at 1,
        replacing excess with random legal cards. Keeps mutated decks legal so
        the optimizer doesn't burn generations on 0%-scoring illegal lists."""
        counts: Counter = Counter()
        ace_used = 0
        repaired: List[str] = []
        for name in deck:
            is_ace = name in self._ace_spec
            cap = float("inf") if name in self._basic_energy else MAX_COPIES
            if is_ace and ace_used >= 1:
                repaired.append(random.choice(self.all_cards))
                continue
            if counts[name] >= cap:
                repaired.append(random.choice(self.all_cards))
                continue
            counts[name] += 1
            if is_ace:
                ace_used += 1
            repaired.append(name)
        return repaired

    def _replace_random_card(self, deck: List[str]) -> List[str]:
        """Replace one card with a random different card."""
        if not deck:
            return deck
        idx = random.randrange(len(deck))
        new_card = random.choice(self.all_cards)
        deck[idx] = new_card
        return deck

    def _add_tech_card(self, deck: List[str]) -> List[str]:
        """Add a popular tech card (ex, V, etc.)."""
        tech_pool = [c for c in self.all_cards if any(x in c for x in ["ex", "V", "ex ", "MEGA"])]
        if tech_pool:
            tech = random.choice(tech_pool)
            if deck.count(tech) < 4:
                idx = random.randrange(len(deck))
                deck[idx] = tech
        return deck

    def _adjust_counts(self, deck: List[str]) -> List[str]:
        """Slightly increase or decrease count of a card."""
        if len(deck) < 2:
            return deck
        card = random.choice(deck)
        if deck.count(card) >= 4:
            return deck  # already maxed
        # Simple: replace a random card with this one
        idx = random.randrange(len(deck))
        deck[idx] = card
        return deck

    def _swap_two_cards(self, deck: List[str]) -> List[str]:
        """Swap positions of two cards."""
        if len(deck) < 2:
            return deck
        a, b = random.sample(range(len(deck)), 2)
        deck[a], deck[b] = deck[b], deck[a]
        return deck
