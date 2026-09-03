#!/usr/bin/env python3
"""
deck_generator.py — Mutation strategies for creating new deck variations
"""

import random
from collections import Counter
from typing import List
from ..engine.cards import CardDB
from ..engine.decks import DECKS
from ..engine.legality import is_mark_legal, MAX_COPIES
from .types import Decklist


def _implemented_card_names(db: CardDB) -> list:
    """Names the engine can actually play: union of every DECKS recipe, plus
    basic energy. The Standard pool is an order of magnitude wider than the set
    of cards with a registered effect, and an unimplemented card is a blank in
    the sim — so mutating toward the raw pool just fills lists with vanilla
    bodies and scores that as a deck change.
    """
    names = set()
    for recipe in DECKS.values():
        for name, _count in recipe:
            card = db._by_name.get(name)
            if card is not None and is_mark_legal(card):
                names.add(name)
    for n, c in db._by_name.items():
        if c.is_basic_energy:
            names.add(n)
    return sorted(names)


class DeckMutator:
    """Handles creating mutated versions of decks for optimization."""

    def __init__(self, db: CardDB):
        self.db = db
        self.all_cards = _implemented_card_names(db)
        if not self.all_cards:
            raise RuntimeError("mutator card pool is empty — DECKS/registry failed to load")
        self._basic_energy = {n for n, c in db._by_name.items() if c.is_basic_energy}
        self._ace_spec = {n for n, c in db._by_name.items() if "ACE SPEC" in c.subtypes}
        # Big attackers, by SUBTYPE — not by substring. The old filter matched
        # any name containing "ex"/"V"/"MEGA" as text, which both missed cards
        # and swept in unrelated ones; "V" in particular is a rotated mechanic
        # that matches every capital-V name in the pool.
        self._tech_pool = [n for n in self.all_cards
                           if {"ex", "MEGA"} & set(db._by_name[n].subtypes)]

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
        """Swap one slot for an ex / MEGA attacker."""
        if not self._tech_pool or not deck:
            return deck
        tech = random.choice(self._tech_pool)
        if deck.count(tech) < MAX_COPIES:
            idx = random.randrange(len(deck))
            deck[idx] = tech
        return deck

    def _adjust_counts(self, deck: List[str]) -> List[str]:
        """Increase OR decrease the count of one card by 1.

        Both directions matter: a mutator that only ever adds copies can raise a
        line's count but never trim it, so counts ratchet upward and thinning a
        clogged list is unreachable.
        """
        if len(deck) < 2:
            return deck
        card = random.choice(deck)
        up = random.random() < 0.5
        if up and deck.count(card) < MAX_COPIES:
            deck[random.randrange(len(deck))] = card
        elif not up and deck.count(card) > 1:
            deck[deck.index(card)] = random.choice(self.all_cards)
        return deck

    def _swap_two_cards(self, deck: List[str]) -> List[str]:
        """Replace one card with an implemented card the deck does not play.
        (A positional swap is a no-op on a multiplicity list.)"""
        present = set(deck)
        newcomers = [c for c in self.all_cards if c not in present]
        if not newcomers:
            return self._replace_random_card(deck)
        idx = random.randrange(len(deck))
        deck[idx] = random.choice(newcomers)
        return deck
