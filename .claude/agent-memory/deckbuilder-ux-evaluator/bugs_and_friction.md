---
name: bugs-and-friction
description: Bugs, data gaps, and UX friction found in PTCGCoach (with repro)
metadata:
  type: project
---

**P0 — Core Standard staples missing from bundled pool.** cards.json lacks Iono, Professor's Research, Nest Ball, Earthen Vessel (Squawkabilly ex too). These are 4-of staples in most real decks. DeckImporter then reports them as "missing / not in Standard pool" and the legality check fails legal decks. Repro: paste any list with "4 Iono"; importer puts it in `missing`. StrategyEngine.consistencyNames even references these names, so data & logic are out of sync. cards.json count=1284.

**P1 — Strategy engine recommends DOWNGRADES on false-legality grounds.** Because of the missing staples, StrategyEngine emits Legality reps like "-4 Professor's Research / +4 Cheren" and "-4 Iono / +4 Cheren" — telling the user to cut the two best draw supporters in the game for a worse one. Repro: run StrategyEngine.build on any deck containing Iono/Prof Research.

**P1 — Two contradictory matchup models, same app, no reconciliation.** Meta tab detail board renders the bundled greedy-pilot `deck.matchups` (MetaDecksView.swift:88). Decks→Simulate runs the on-device prize-race DeckSimulator. They disagree hard: Gardevoir vs Mega Lucario = 38% (published, Gardevoir loses) vs 86% (sim, Gardevoir wins). A user sees opposite advice with no explanation of which to trust.

**P2 — Strategy thin on sub-50% decks.** Stock Gardevoir (sim rates it 43%) gets only ONE rec ("trim 3 energy"). Tech-counter rule requires ≥2 meta decks whose attackerType == your weakness; only 1 Dark deck exists, so it never fires — user gets no help on their actual losing matchups (Dark/Beedrill).

**P2 — Coach Analysis selection/content mismatch.** AUTOREVIEW+AUTOANALYZE: segmented control highlights "Avery (won)" but the body shows Blake's loss analysis ("Result: Loss 1/6"). Verify whether the default-focus=loser logic mis-syncs the segment highlight.

**P2 — "1-cost attacker" mislabel.** Sim energy rec for Mega Gardevoir says "17 Energy heavy for a 1-cost attacker" — attackCost in data looks wrong/low for a Mega.

**UX — content polish:** Meta blurbs truncate ("...beatdo", "...Munkid"); Review "Setup" row shows bare icons (14 / ⚡0 / ☀️0) with no labels.

**UX (by design but notable):** real core flows (paste deck, tap Simulate, read results) can't be driven without DEBUG env hooks — simctl has no tap/type. Signals how hard the happy path is to reach; the app leans on hidden hooks for any demo.
