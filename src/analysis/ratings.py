#!/usr/bin/env python3
"""
ratings.py — turn a round-robin win-rate matrix into a single strength number per deck.

We fit Elo ratings (the Bradley-Terry model on the Elo scale) by deterministic
gradient ascent on the pairwise log-likelihood: for every deck pair we nudge the two
ratings toward the observed win rate, repeat until they stop moving, then mean-center
on `base` (1500). Deterministic — the same matrix always gives the same ratings.

Why Elo on top of raw win% : "overall win %" treats every opponent equally, so beating
a weak deck counts the same as beating a strong one. Elo weights *who* you beat — a deck
that beats the top decks scores higher than one that only farms the bottom.
"""

from __future__ import annotations


def compute_elo(decks: list[str], matrix: dict, base: float = 1500.0,
                k: float = 8.0, passes: int = 600) -> dict:
    """Elo rating per deck from `matrix[a][b]` = a's win % vs b (0..100, None on diagonal)."""
    R = {d: float(base) for d in decks}
    pairs = [(a, b) for i, a in enumerate(decks) for b in decks[i + 1:]
             if matrix.get(a, {}).get(b) is not None]
    for _ in range(passes):
        delta = {d: 0.0 for d in decks}
        for a, b in pairs:
            pa = matrix[a][b] / 100.0                       # a's observed score vs b
            ea = 1.0 / (1.0 + 10 ** ((R[b] - R[a]) / 400.0))  # a's expected score
            g = k * (pa - ea)
            delta[a] += g
            delta[b] -= g
        for d in decks:
            R[d] += delta[d]
    mean = sum(R.values()) / len(R) if R else base
    return {d: round(R[d] - mean + base) for d in decks}
