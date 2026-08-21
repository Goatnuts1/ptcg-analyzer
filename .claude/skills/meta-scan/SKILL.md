---
name: meta-scan
description: Weekly Pokémon TCG meta scan for ptcg-analyzer — pull the live Limitless Standard table and upcoming-set news, diff against the deck registry and the recorded matchup matrix, build any newly meta-relevant archetype (cards + effects + deck + tests), and report the current threats and their best stoppers. Use when the user asks for a meta scan, meta update, "what's the meta doing", or on the weekly schedule.
---

# Meta scan — weekly procedure

You are in the ptcg-analyzer repo. Read CLAUDE.md first; the calibration and
provenance rules there override any instinct to present sim numbers as truth.

## 1. Pull the live meta (network)

- WebFetch `https://play.limitlesstcg.com/decks?format=standard&rotation=2026&set=PBL`
  (bump `rotation`/`set` after a rotation) — top ~25 archetypes with share % and
  real win rate %.
- WebSearch for upcoming set releases and notable tournament results since the last
  scan (last scan date = newest `docs/META_SCAN_*.md`).

## 2. Diff against what we have

- Map each archetype ≥1% share to a registry deck (the proxy table lives in the
  newest META_SCAN doc; carry it forward). Compute representable share.
- Note risers/fallers vs the previous scan (>0.5pt share move or >1pt WR move).
- List archetypes with NO registry deck. **Build bar: ≥2% share, or <2% but rising
  two scans in a row, or it beat `Goatest1` on ladder (check docs/LADDER_LOG.md).**

## 3. Build what crossed the bar (the expensive step — follow repo standards exactly)

For each new archetype: fetch a real decklist from limitlesstcg (prefer the best
recent finish; record player/event/placement as provenance in the deck comment).
Then the established pipeline:
- Cards missing from the pool → `data/manual_cards.json` with REAL text fetched from
  limitlesstcg card pages (never memory), respecting print-collision suffix rules.
- Effects in `src/engine/effects.py` (§-dated section), registered + asserted against
  card text in a new `tests/test_*.py`. New action kinds need `mcts._semantic_key`
  + a clone field + start_turn reset (see the Spikemuth Gym checklist in CLAUDE.md).
- Register the deck in `src/engine/decks.py` with a provenance comment.
- Full suite green (run every tests/test_*.py as standalone scripts) + determinism.
- If greedy mispilots the new deck (<20% vs mega_excadrill is the smell), consider
  narrowly-scoped pilot branches per the Slowking precedent — but NEVER unscoped
  changes, and never silently move recorded numbers.

## 4. Measure

- New decks only: run them into the existing matrix protocol (`mcts2 @ 60`, n=60,
  seed 2026, mirrored) vs the covered field; append cells to
  `docs/matrix_2026-08_mcts2.json`-style dated matrix files rather than overwriting.
- If the meta DRIFTED >2pt total share among covered decks, recompute the
  share-weighted table with fresh shares (cheap — no new games needed).

## 5. Report: threats and stoppers

Write `docs/META_SCAN_<date>.md`:
- Meta drift table; coverage %; horizon (set releases with dates + expected impact).
- Threats = archetypes with the highest REAL win rates (not sim) weighted by share.
- Stoppers = for each threat, the 3 best registry decks by matrix cell — computed
  from the matrix JSON, never from memory.
- ALWAYS carry the calibration caveats: ~13pt aggro bias, pilot-floor decks
  (festival_lead, slowking toolbox lines) named explicitly.
- End with: what changed for the user's own deck (`mega_excadrill` unless the ladder
  log says otherwise) — new bad matchups rising? Tech implications? Cite the ladder
  log where real games corroborate or contradict the sim.

## 6. Hygiene

- Commit as `meta-scan: <date>` if the user has authorized commits for scan runs;
  otherwise leave staged-nothing and report.
- Keep each scan self-contained: next week's scan reads this week's doc as its
  baseline.

## 7. Futures (Japanese sets + rotation horizon)

- Run `python3 cli.py --futures` and include its table in the scan report.
- Update `src/analysis/futures.py`:
  - `SHARE_TRENDS`: roll the two-scan share window forward (this scan vs previous).
  - `SPECULATIVE_FLAGS`: refresh from the week's reveals. Japanese sets run ~3 months
    ahead of international (current: Storm Emeralda = Delta Reign, intl. 2026-11-06);
    search JP City League results for archetypes using the newest JP set — they are
    the best preview of the post-release meta. Fetch REAL card text for anything
    flagged (Bulbapedia card pages / limitlesstcg).
  - After a rotation announcement, update `NEXT_ROTATING_MARK` / `ROTATION_DATE`.
- The rule that keeps this honest: rotation % and trend risk are DATA and go into the
  score; upcoming-card opinions are FLAGS and never do. If a JP-set card can be built
  faithfully (full text revealed) and a JP archetype around it clears ~2% of JP
  results, it may be built as a `future_` deck (provenance: JP-PREVIEW, its own class —
  win rates against it are previews, not measurements).
