#!/usr/bin/env python3
"""
futures.py — the FUTURE-PROOF score: how well does a deck survive what's coming?

Three components, in strictly decreasing order of trustworthiness — and the report
never blends them silently:

1. ROTATION RISK (hard data). The yearly rotation removes the oldest regulation mark
   (G left in April 2026; H leaves ~April 2027 on the same cadence). A deck's rotation
   risk is the % of its 60 cards carrying the NEXT-TO-ROTATE mark. This is arithmetic
   on printed card data — zero speculation.

2. TREND RISK (measured, short-baseline). For every archetype whose metagame share
   ROSE between the two most recent meta scans, weight the deck's measured matchup
   deficit (50 − our matrix WR, floored at 0) by the share gain. A deck weak to what's
   growing scores badly. Honest limits: the share baseline is days long, and the
   matchup cells carry the sim's documented biases.

3. SPECULATIVE FLAGS (labeled speculation, never numeric). Hand-maintained notes about
   unreleased/upcoming cards (Japanese sets run months ahead), e.g. Delta Reign's
   Mega Rayquaza ex. These are printed with the report but NEVER folded into the
   score — a number would launder a guess into data.

FUTURE-PROOF SCORE (v0) = 100 − (0.7 × rotation_risk_pct + 0.3 × trend_risk_norm).
The weights are a stated editorial choice, not a measurement; rotation dominates
because it is the one certain event.
"""

from __future__ import annotations

import json
import os

# Rotation cadence: one mark per April. Next out is the oldest still legal.
NEXT_ROTATING_MARK = "H"
ROTATION_DATE = "2027-04 (est., annual cadence)"

# Share deltas between the two most recent scans (pts). Maintained by the meta-scan
# skill; positive = rising. Only RISERS contribute to trend risk.
SHARE_TRENDS = {
    # archetype (registry name): (share_then, share_now) — 2026-08-17 -> 2026-08-20
    # NOT refreshed 2026-09-21: play.limitlesstcg.com and every other live-share source
    # were unreachable this scan (network egress denied the whole session, not just this
    # tool — see docs/META_SCAN_2026-09-21.md). Carrying the 08-20 numbers forward
    # unmodified rather than fabricating a trend; do not read these as current.
    "raging_bolt":        (1.79, 1.97),
    "cynthia_garchomp":   (1.18, 1.20),
    "dragapult":          (12.35, 12.47),   # Dragapult + Dusknoir rows combined
    "alakazam_deck":      (5.16, 5.24),
    "slowking":           (5.26, 5.36),
    "mega_excadrill":     (7.79, 7.84),
    "festival_lead":      (6.75, 6.55),
    "dragapult_blaziken": (5.99, 6.02),
    "grimmsnarl_froslass": (4.66, 4.55),
    "hide_n_sneak":       (4.10, 4.08),
    "toucannon":          (3.40, 3.18),
    "fighting":           (1.77, 1.89),
    "greninja":           (1.70, 1.63),
    "beedrill":           (1.22, 1.16),
}

# Speculative flags: upcoming-set concerns/opportunities per deck. LABELED SPECULATION.
SPECULATIVE_FLAGS = {
    "_global": [
        "Delta Reign (intl. 2026-11-06; JP 'Storm Emeralda' live since 07-31): four new "
        "Megas — Mega Rayquaza ex (280HP BASIC Mega, Storm Emerald 50x per Fire/Lightning "
        "Energy on its whole board, Colorless type, Fighting resistance), Mega Golisopod ex "
        "(Grass, 340 HP, evolves from Wimpod #011/103 — real text confirmed 2026-09-14: "
        "'Finishing Blow' 60 (+160 more, 220 total, if the Defending Pokemon already has "
        "damage counters on it) and 'Quadruple Hold' 160 (Defending Pokemon can't retreat "
        "next turn)), Mega Golurk ex, Mega Malamar ex. Also confirmed: three paired "
        "'Legendary Stadium' cards (Legendary Summit / Legendary Ocean Trench / Legendary "
        "Lava Lake) — no card-level interaction identified yet, full text not yet spoiled.",
        "30th Celebration released on schedule 2026-09-16: reprint/foil/Pikachu-art heavy "
        "(new 'Futuristic Rare' Mew ex / Mewtwo ex). No numbered-card Standard legality or "
        "attack text confirmed yet — still no identified competitive impact.",
    ],
    "mega_excadrill": [
        "Mega Rayquaza ex is Colorless: no Weakness leverage against Metal — neutral "
        "threat, but a 280HP Basic Mega that scales past 300 outraces Metallic Hammer math.",
    ],
    "fighting": [
        "Mega Rayquaza ex resists Fighting (−30) and Basic-Mega speed beats Stage-1 setup: "
        "the current #1 sim deck is the most exposed to the November shake.",
    ],
    "crustle_modern": [
        "Mega Golisopod ex's confirmed text (see _global) is Grass-type AND an ex: "
        "Mysterious Rock Inn would wall its attack damage entirely rather than the other "
        "way around. No direct threat identified from revealed cards; if anything this "
        "one favors the wall plan.",
    ],
    "ogerpon_box": [
        "Made 2026 Worlds Top 8 (1 of 8, real result — see docs/META_SCAN_2026-09-21.md). "
        "Mega Golisopod ex is Grass, same type as this deck's own Teal Mask Ogerpon ex "
        "line, so it neither exploits nor relieves the deck's structural x2 Fire "
        "Weakness. No direct interaction identified from confirmed text.",
    ],
}


def _load_pool(pool_path: str):
    with open(pool_path) as f:
        return {c["name"]: c for c in json.load(f)}


def rotation_risk(recipe, pool_by_name) -> tuple[float, list]:
    """(% of the deck's copies that rotate with NEXT_ROTATING_MARK, [(card, qty), ...]).
    Basic Energy carries no mark and never rotates."""
    total = sum(q for _, q in recipe)
    rotating = []
    for name, qty in recipe:
        card = pool_by_name.get(name)
        if card is None:
            continue
        if card.get("regulationMark") == NEXT_ROTATING_MARK:
            rotating.append((name, qty))
    lost = sum(q for _, q in rotating)
    return (100.0 * lost / total if total else 0.0), sorted(rotating, key=lambda x: -x[1])


def trend_risk(deck: str, matrix: dict) -> tuple[float, list]:
    """Sum over RISING archetypes of share_gain × max(0, 50 − WR(deck vs riser)).
    Returns (raw score, [(riser, gain, wr), ...] contributors)."""
    def wr(c, f):
        r = matrix.get("|".join(sorted([c, f])))
        if not r:
            return None
        t = r["d1_wins"] + r["d2_wins"]
        if not t:
            return None
        w = r["d1_wins"] if r["d1"] == c else r["d2_wins"]
        return 100.0 * w / t
    score, contributors = 0.0, []
    for riser, (then, now) in SHARE_TRENDS.items():
        gain = now - then
        if gain <= 0 or riser == deck:
            continue
        v = wr(deck, riser)
        if v is None:
            continue
        deficit = max(0.0, 50.0 - v)
        if deficit > 0:
            score += gain * deficit
            contributors.append((riser, round(gain, 2), round(v, 1)))
    return score, contributors


def futures_report(decks: dict, pool_path: str, matrix_path: str) -> str:
    pool = _load_pool(pool_path)
    matrix = json.load(open(matrix_path)) if os.path.exists(matrix_path) else {}
    rows = []
    for name, recipe in decks.items():
        rot, rot_cards = rotation_risk(recipe, pool)
        tr, contrib = trend_risk(name, matrix)
        rows.append((name, rot, rot_cards, tr, contrib))
    max_tr = max((r[3] for r in rows), default=0.0) or 1.0
    out = [f"FUTURE-PROOF report — next rotation: mark {NEXT_ROTATING_MARK} out {ROTATION_DATE}",
           "score = 100 − (0.7×rotation% + 0.3×trend_norm); flags are SPECULATION, never scored",
           "",
           f"{'deck':24} {'score':>6} {'rot%':>6} {'trend':>6}  worst rising matchup"]
    scored = []
    for name, rot, rot_cards, tr, contrib in rows:
        tr_norm = 100.0 * tr / max_tr
        score = 100.0 - (0.7 * rot + 0.3 * tr_norm)
        worst = min(contrib, key=lambda c: c[2]) if contrib else None
        scored.append((score, name, rot, tr_norm, worst, rot_cards))
    for score, name, rot, tr_norm, worst, rot_cards in sorted(scored, reverse=True):
        w = f"{worst[0]} ({worst[2]}%)" if worst else "-"
        out.append(f"{name:24} {score:6.1f} {rot:5.1f}% {tr_norm:6.1f}  {w}")
    out.append("")
    out.append("Largest mark-%s exposures (cards lost at rotation):" % NEXT_ROTATING_MARK)
    for score, name, rot, tr_norm, worst, rot_cards in sorted(scored, key=lambda r: -r[2])[:5]:
        tops = ", ".join(f"{n} x{q}" for n, q in rot_cards[:4])
        out.append(f"  {name:24} {rot:4.1f}%  {tops}")
    out.append("")
    out.append("SPECULATIVE FLAGS (upcoming sets; opinions, not measurements):")
    for note in SPECULATIVE_FLAGS["_global"]:
        out.append(f"  * {note}")
    for name in decks:
        for note in SPECULATIVE_FLAGS.get(name, []):
            out.append(f"  * [{name}] {note}")
    return "\n".join(out)
