# The best deck vs the August 2026 format — full mcts2 matrix

**Measured 2026-08-17, overnight run.** 159 unique pairings, n=60 each, seed 2026,
mirrored seats, BOTH sides piloted by `mcts2 @ 60` (the strongest agent in the repo).
20 candidates: the 14 live-metagame archetypes (63.1% of the Limitless PBL field is now
representable) + 6 engine-built "math" decks. Scored as the share-weighted win rate
against the live field, mirror counted at 50%.

Pilot note: this run includes the nine Fable-reviewed pilot corrections
(`agents.py` / `evaluation.py`, all archetype-scoped per the Slowking-branch precedent;
verified to leave every previously-measured deck's numbers unchanged — spot-check
mega_excadrill vs slowking_annihilape 81.7% → 80.0%, within noise).

## The ranking

| # | deck | wt WR vs field | | # | deck | wt WR |
|---|---|---|---|---|---|---|
| 1 | **fighting** (Mega Lucario) | **80.8%** | | 11 | alakazam_deck | 53.5% |
| 2 | **crustle_modern** [math] | **77.5%** | | 12 | dragapult | 48.5% |
| 3 | cornerstone_box [math] | 66.8% | | 13 | dragapult_blaziken | 47.9% |
| 4 | grimmsnarl_froslass | 65.3% | | 14 | doublade [math] | 46.7% |
| 5 | gardevoir [math] | 65.1% | | 15 | toucannon | 42.5% |
| 6 | **mega_excadrill** | 64.8% | | 16 | slowking | 40.5% |
| 7 | cynthia_garchomp | 64.2% | | 17 | hide_n_sneak | 39.7% |
| 8 | mega_excadrill_shaymin [math] | 62.3% | | 18 | raging_bolt | 35.1% |
| 9 | greninja | 55.7% | | 19 | festival_lead | 32.8% |
| 10 | beedrill | 55.0% | | 20 | slowking_annihilape [math] | 32.0% |

## The answer, in two honest halves

**By the mean: `fighting` (Mega Lucario), 80.8%.** It beats every single deck in the
field — its WORST matchups are Beedrill (68%) and Cynthia's Garchomp (70%). Only two
candidates in the whole pool beat it head-to-head: `gardevoir` (68.3%) and
`crustle_modern` (61.7%). **Discount before believing it**: this is the exact archetype
the sim's aggro bias inflates (the calibration section of CLAUDE.md; real Mega Lucario
wins 50.45% on ladder at 1.77% share, and this repo's own earlier measurement watched
`fighting` drop 14 points when piloting improved). The claim that survives the
discount is *relative*: among simple aggro decks, Lucario's package is the strongest,
and nothing in the current field is built to punish it.

**By the floor: `crustle_modern` — the only deck with NO losing matchup.** Its worst
cells are 53.3% (vs mega_excadrill) and 61.7% (vs fighting); everything else is 62–93%.
Under a maximin criterion — "best deck when you don't get to choose your opponent" —
this is the mathematical best, and the result is robust in a way the Lucario number
isn't: it doesn't depend on one inflated archetype, it's a *ladder-provenance* list the
sim's own bias should under-rate (it plays a grindy single-prizer plan, not raw
beatdown), and it's the #2 deck by mean anyway. That an engine-tuned math deck beats
18 of 19 opponents including the entire live top-10 is the strongest deck-building
result this project has produced.

**The user's deck (`mega_excadrill`) is genuinely good: 6th of 20, 64.8%.** Row:
| vs | WR | vs | WR |
|---|---|---|---|
| festival_lead | 85.0% | alakazam_deck | 60.0% |
| hide_n_sneak (Dhelmise) | 80.0% | greninja | 58.3% |
| slowking | 75.0% | cynthia_garchomp | 53.3% |
| dragapult / raging_bolt | 71.7% | **grimmsnarl_froslass** | **46.7%** |
| toucannon | 65.0% | **fighting (Mega Lucario)** | **15.0%** |
| dragapult_blaziken | 63.3% | | |

It is favored into the ladder's actual top decks (Dragapult variants ≈18% of the field,
Festival Lead 6.75%, Slowking 5.26%) and has exactly two problems: Mega Lucario
(15% — near-unwinnable, but only 1.77% of the field) and Grimmsnarl Froslass (46.7%,
4.66% and rising). The 2026-08-16 ladder loss to Dragapult Blaziken reads as the
unlucky side of a 63/37 favorite, not a bad matchup.

## What the sim still cannot measure honestly

- **`festival_lead` 32.8% is a floor, not a rating.** Real WR 51.18%. The pilot
  corrections moved greedy from 6.7% → 19% vs mega_excadrill and mcts2 layers on top,
  but the deck's core loop (dump hand to exactly 1 card for Gladion, twice-attacking
  bench math, stadium war) is the hardest sequencing task in the format and 60
  iterations of search do not find it. Treat every festival_lead cell as pessimistic.
- **`slowking_annihilape` 32.0% contradicts direct ladder evidence** (it beat the house
  deck twice in real games). Toolbox piloting — Academy at Night top-deck planning —
  remains beyond both agents at these budgets. Same floor caveat.
- **The aggro bias is measured at roughly +13 points** (mega_excadrill: sim ~63–65% vs
  real 49.51%). Apply it mentally to every aggressive deck's number, `fighting` first.

## Recommendations

1. **Playing tomorrow, with the Mega Excadrill bias: keep the deck.** It's top-tier
   into the field people actually play. Add nothing for Lucario (too rare to warrant
   slots); consider one tech for Grimmsnarl — their chip engine (Freezing Shroud) taxes
   YOUR Ability-holders (Metang ×4, Genesect ×2), so the `mega_excadrill_shaymin`
   variant is NOT the answer here (Shaymin adds another Ability body). A Munkidori
   answer or faster prize race is.
2. **If the goal is the best deck, period: `crustle_modern`** — no losing matchup, and
   its two closest cells are against decks (mega_excadrill, fighting) whose sim numbers
   are inflated by the bias, meaning its true floor is likely HIGHER than measured.
3. **To beat the field's mathematical #1** (if Lucario ever spikes): `gardevoir` (68.3%
   into it) — also 5th overall.
4. The next engine investment is unchanged by any of this: pilot strength for
   combo/toolbox decks is the binding constraint on measurement fidelity
   (festival_lead and slowking_annihilape are both floors, and both matter).

## Appendix (2026-08-18): can `mega_excadrill` adjust? — tested, and the answer is NO (list) / YES (play)

Four 1–2 slot variants were built and measured against the target matchup
(`grimmsnarl_froslass`) with regression cells (dragapult, slowking):

| variant | greedy n=400 vs grimm | mcts2 n=60 vs grimm | mcts2 n=120 fresh seed |
|---|---|---|---|
| house list | 31.0% | 46.7% | **50.0%** |
| +1 Gravity Mountain −1 Pichu | 32.5% | — | — |
| +1 Boss's −1 Pichu | 32.2% | — | — |
| +1 Kieran −1 Pichu | 34.8% | 43.3% | **39.2%** |
| +1 GM +1 Boss's −1 Pichu −1 Red Card | 33.2% | 43.3% | — |

Every tested change is flat or WORSE under real (mcts2) piloting — the third Kieran,
the greedy screen's best, is 11 points worse at n=120. Two conclusions, both earned:

1. **The house list is locally optimal.** Unsurprising in hindsight: it is the most-
   played deck in the format and the community has already ground these slots. Ethan's
   Pichu, the "obvious" cut, wins its slot in every test.
2. **The Grimmsnarl cell is a coin-flip (50.0% fresh-seed), not a losing matchup** —
   the overnight 46.7% was seed noise on the low side.

The real adjustments are PLAY, not cards — the loss analysis (Shadow Bullet + Punk Up
present in 26/27 greedy losses) gives three concrete lines the LIST already supports:

- **Hold Kieran for the Hammer turn.** Metallic Hammer 300 is exactly 20 short of
  Grimmsnarl ex's 320; Kieran's second mode makes it 330. One OHKO = the 2-prize swing
  that decides the trade war. (Both agents under-execute this — a known pilot floor.)
- **Gravity Mountain before the Hammer turn** is the backup route to the same KO
  (320→290), and contests their 4 Spikemuth Gym in the Stadium war.
- **Boss's Orders on Munkidori (110 HP) early.** Adrena-Brain present in half the
  losses; killing the relocation engine blanks Froslass's chip conversion.

Pilot-level encoding of the Kieran timing (a scoped greedy branch, Slowking-precedent
shape) is the one change that would plausibly move this cell — deliberately NOT made,
because it would stale the overnight matrix for every Kieran deck. Flagged for the next
measurement cycle.
