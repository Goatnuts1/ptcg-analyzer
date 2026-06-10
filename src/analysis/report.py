#!/usr/bin/env python3
"""
report.py — presentation helpers for round-robin / matchup results.

  - matrix_to_csv  : the win-rate matrix as CSV (spreadsheet-friendly)
  - matrix_to_html : a standalone, color-coded heatmap + Elo leaderboard (open in a browser)
  - who_would_win  : a plain-language, kid-friendly single-matchup summary

All pure functions — they take already-computed numbers and return strings, so they're
trivially testable and have no engine dependency.
"""

from __future__ import annotations

import html as _html


def matrix_to_csv(decks: list[str], matrix: dict, overall: dict, elo: dict) -> str:
    """The win-rate matrix as CSV: a row per deck, a column per opponent, + overall + Elo."""
    out = ["deck," + ",".join(decks) + ",overall,elo"]
    for a in decks:
        cells = ["" if a == b else f"{matrix[a][b]:.0f}" for b in decks]
        out.append(",".join([a] + cells + [f"{overall[a]:.1f}", f"{elo[a]}"]))
    return "\n".join(out) + "\n"


def _cell_color(p):
    """Heatmap color for a win % (red ~0, yellow ~50, green ~100); grey for the diagonal."""
    if p is None:
        return "#dddddd"
    p = max(0.0, min(100.0, p))
    if p <= 50:
        t = p / 50.0
        r, g, b = 220, int(70 + (200 - 70) * t), 70
    else:
        t = (p - 50) / 50.0
        r, g, b = int(220 - (220 - 60) * t), 200, 70
    return f"rgb({r},{g},{b})"


def matrix_to_html(decks: list[str], matrix: dict, overall: dict, elo: dict,
                   title: str = "Deck meta matrix") -> str:
    """A standalone HTML page: color-coded win-rate heatmap + an Elo-ranked leaderboard."""
    esc = _html.escape
    th = "".join(f"<th>{esc(d)}</th>" for d in decks)
    rows = []
    for a in decks:
        tds = []
        for b in decks:
            p = matrix[a][b] if a != b else None
            txt = "—" if a == b else f"{p:.0f}%"
            tds.append(f'<td style="background:{_cell_color(p)}">{txt}</td>')
        rows.append(f"<tr><th>{esc(a)}</th>{''.join(tds)}"
                    f"<td class='ov'>{overall[a]:.1f}%</td><td class='ov'>{elo[a]}</td></tr>")
    board = "".join(
        f"<li><b>{esc(d)}</b> — Elo {elo[d]} · {overall[d]:.1f}% overall</li>"
        for d in sorted(decks, key=lambda d: -elo[d]))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>
 body{{font-family:system-ui,Arial,sans-serif;margin:2rem;color:#222}}
 table{{border-collapse:collapse;margin:1rem 0}}
 th,td{{border:1px solid #bbb;padding:.4rem .6rem;text-align:center;font-size:.9rem}}
 th{{background:#f3f3f3}} td.ov{{background:#f8f8f8;font-weight:600}}
 caption{{caption-side:top;font-weight:600;margin-bottom:.5rem}}
 ol{{line-height:1.6}}
</style></head><body>
<h1>{esc(title)}</h1>
<p>Cell = row deck's win % vs column deck. Green = favored, red = unfavored.</p>
<table><caption>Win-rate matrix</caption>
<tr><th></th>{th}<th class='ov'>overall</th><th class='ov'>elo</th></tr>
{''.join(rows)}
</table>
<h2>Tier ranking (by Elo)</h2>
<ol>{board}</ol>
</body></html>
"""


def who_would_win(deck1: str, deck2: str, w1: int, w2: int, ties: int, games: int) -> str:
    """A friendly, jargon-free single-matchup summary (the 'Linus-friendly' mode)."""
    total = w1 + w2
    p1 = 100 * w1 / total if total else 50.0
    fav, fav_pct = (deck1, p1) if p1 >= 50 else (deck2, 100 - p1)
    out_of_10 = round(fav_pct / 10)
    margin = abs(p1 - 50)
    if margin >= 35:
        flavor = "a total blowout! 💥"
    elif margin >= 15:
        flavor = "a clear winner. 🏆"
    elif margin >= 5:
        flavor = "a close one! 😅"
    else:
        flavor = "basically a coin flip! 🪙"
    tie_note = f"   ·   ties {ties}" if ties else ""
    return "\n".join([
        f"🥊  {deck1}  vs  {deck2}",
        f"    (played {games} games)",
        "",
        f"🏆  {fav} wins about {out_of_10} out of 10 games — {flavor}",
        f"    {deck1}: {p1:.0f}%   ·   {deck2}: {100 - p1:.0f}%{tie_note}",
    ])
