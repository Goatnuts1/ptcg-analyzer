# `mega_excadrill` vs the live metagame — August 2026

**Measured 2026-08-17.** Deck under test: `mega_excadrill` (the house list, confirmed as
the one actually piloted on ladder — see `docs/LADDER_LOG.md`).

Sim protocol: `--agent mcts2 --iters 60`, n=60, seed 2026, mirrored seats, **both sides
piloted by the same agent**. A greedy pass at n=400 was run first and is quoted where the
two disagree.

Real-world reference: the live Limitless PBL-Standard metagame table
([play.limitlesstcg.com](https://play.limitlesstcg.com/decks?format=standard&rotation=2026&set=PBL)),
which reports both metagame share and actual win rate over thousands of recorded games.

## The headline, stated first because it's uncomfortable

> **The simulator says this deck beats the field ~63%. Reality says it wins 49.51%.**

`Mega Excadrill` is the **most-played deck in the format** (7.79% share) and its real win
rate is **just below parity**. Our sim rates it as a dominant tier-0 deck. That gap — about
**13 points** — is the single most important number in this document, and it is a
statement about *our simulator*, not about the deck.

This is the known aggro over-rating documented in `CLAUDE.md`, now measured against
external ground truth for the first time. Search closes part of it: over the 9 matchups run
under both agents, greedy averages **73.6%** and mcts2 **65.7%**, so better piloting removes
~8 points of the illusion. Reality needs ~16 more.

## The gauntlet

| meta archetype | share | real WR | our proxy | sim WR (mcts2) |
|---|---|---|---|---|
| Mega Excadrill | 7.79% | 49.51% | *mirror* | — |
| Dragapult | 6.95% | 54.09% | `dragapult` | 65.0% |
| **Festival Lead** | **6.75%** | 51.18% | **— missing —** | — |
| **Dragapult Blaziken** | **5.99%** | 52.79% | **— missing —** | — |
| Dragapult Dusknoir | 5.40% | 50.00% | `dragapult` | 65.0% |
| Slowking | 5.26% | 52.34% | `slowking` | 75.0% |
| Alakazam Dudunsparce | 5.16% | 53.57% | `alakazam_deck` | **45.0%** |
| N's Zoroark | 5.16% | 48.14% | `decks/imported/n_zoroark.json` | *93.3% — see below* |
| **Grimmsnarl Froslass** | **4.66%** | 51.32% | **— missing —** | — |
| Dhelmise | 4.10% | 47.84% | `hide_n_sneak` *(approx)* | 91.7% |
| Toucannon | 3.40% | 47.30% | `toucannon` | 65.0% |
| Raging Bolt Ogerpon | 1.79% | 53.45% | `raging_bolt` | 71.7% |
| Mega Lucario | 1.77% | 50.45% | `fighting` | **33.3%** |
| Mega Greninja | 1.70% | 41.87% | `greninja` | 66.7% |
| Beedrill | 1.22% | 48.84% | `beedrill` | 73.3% |
| Cynthia's Garchomp | 1.18% | 52.23% | `cynthia_garchomp` | 58.3% |

Non-meta decks in the registry, same protocol, for reference: `slowking_annihilape` 81.7%,
`doublade` 76.7%, `toucannon` 65.0%, `clefairy_stock` 60.0%, `charizard_xy` 50.0%,
`gardevoir_real` 50.0%, `cornerstone_box` 50.0%, `ogerpon_box` 53.3%,
`crustle_modern` 43.3%.

**Share-weighted sim win rate over the covered field: 62.9%** (45.7% of the metagame,
mirror included at 50%).

## What to actually believe from this

**The two matchups the sim says we lose are the ones worth trusting most**, because they
run *against* the deck's aggro bias rather than with it:

- **Mega Lucario (`fighting`) — 33.3%.** The sim's worst result by a wide margin, and it
  survived the switch from greedy to mcts2. Real Mega Lucario is a 50.45% deck at 1.77%
  share, so this is a genuine bad matchup rather than a weak opponent.
- **Alakazam Dudunsparce — 45.0%.** 5.16% of the field with a 53.57% real win rate: a
  strong, popular deck that our own sim says beats us. Worth treating as a real problem.

**Three numbers are not credible:**

- **N's Zoroark 93.3%.** Real N's Zoroark wins 48.14% across the format. A 93% read is the
  documented combo-deck mispiloting failure — the agent cannot execute the Zoroark engine,
  so it reads as a free win. Excluded from the weighted average.
- **Dhelmise 91.7%.** `hide_n_sneak` merely *contains* Dhelmise (PBL); it is not the
  Dhelmise archetype. A placeholder, not a measurement.
- **Slowking 75.0%.** Our own ladder record has a Slowking toolbox beating this exact deck
  **twice** (which is why `slowking_annihilape` exists), and the real archetype wins 52.34%.
  The sim has this backwards.

## The gap in coverage: 17.4% of the metagame is unmeasurable

Three top-10 archetypes have no deck in the registry:

| missing | share | why it matters |
|---|---|---|
| Festival Lead | 6.75% | 3rd most-played deck in the format |
| Dragapult Blaziken | 5.99% | **the deck that beat us on 2026-08-16** — Fire vs an all-Fire-weak board |
| Grimmsnarl Froslass | 4.66% | 9th |

**The good news is that this is an effects problem, not a data problem.** Checking the pool
for the cards these decks need: 33 of 35 probed cards are already in
`data/standard_pool.json` — Blaziken ex, Torchic, Combusken, Festival Grounds, Dipplin,
Applin, Thwackey, Grookey, Seaking, Lilligant, Grimmsnarl, Impidimp, Morgrem, Froslass,
Snorunt, Rare Candy, Unfair Stamp, Crispin, Dawn, Lisia's Appeal all present. Only
**Grimmsnarl ex** and **Mega Darkrai ex** are missing, both consistent with the set-coverage
hole in `docs/TCGLIVE_LOG_FIDELITY.md` (Finding 1).

What is *not* present is any of the archetype-defining behaviour: none of Blaziken ex,
Dipplin, Froslass, Festival Grounds, Toxtricity or Pecharunt ex has an entry in the attack,
ability or trainer registries. Building these three decks is roughly 15–20 card scripts
plus three decklists — ordinary work of exactly the kind `effects.py` is designed for.

## Recommended order

1. **Build `dragapult_blaziken` first.** It is 5.99% of the field, it beat us in a real
   game, and the loss mechanism (Fire Weakness against an all-Metal board, with a 3-prize
   Mega as the main attacker) is a structural claim the sim can either confirm or refute.
   That is the highest-value single measurement available right now.
2. **Then Festival Lead and Grimmsnarl Froslass**, to close the top-10 coverage gap.
3. **Treat the whole table as provisional until the pool fetch is fixed.** Two meta-relevant
   cards are simply absent, and archetypes we can't see may be hiding behind the same gap.
4. **Do not quote the 62.9% anywhere.** The honest summary of this deck's standing is the
   Limitless number: most-played in the format, winning 49.51%. Our sim does not yet
   reproduce that, and until it does, the gauntlet is a tool for finding bad matchups
   (Lucario, Alakazam) rather than for ranking decks.
