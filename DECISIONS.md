# DECISIONS

Running log of engineering decisions. Format: decision · alternatives · why · risk · date.

## 2026-11-04 — main health fixes (`fix/main-health`)

1. **`cli.py --list` crash: drop the function-local `from src.engine.decks import DECKS`
   inside the `--futures` branch.** The local import made `DECKS` a local name for all of
   `main()`, so every non-futures path that read `DECKS` raised `UnboundLocalError`.
   *Alternatives:* `global DECKS`; rename the local. *Why:* the module already imports
   `DECKS` at top level; the local import was redundant. Same fix as on
   `feature/multihop-mcts`. *Risk:* none found.
2. **`test_toucannon_deck.py`: widen the liveness seed window 40 → 120.** The rare
   Area Zero Underdepths Bench-shrink line stopped firing in the first 40 greedy games
   after a pool rebuild; the clause is unit-tested elsewhere. *Alternatives:* force the
   line with a constructed state. *Why:* matches the branch fix (73e0382), keeps the
   test a liveness check. *Risk:* liveness tests depend on the pool, which is built
   from upstream data at build time, so any future rebuild can shift trajectories again.
3. **torch-dependent tests (`test_arena.py`, `test_train.py`) skip cleanly when
   torch/numpy are absent** — `pytest.importorskip` under pytest, `SKIP` + exit 0 as a
   script (the suite is script-style, not pytest). *Why:* the core engine is stdlib-only;
   the learning stack is optional. *Risk:* a CI without torch never exercises those tests;
   run them from the Trainer venv.
4. **Added `tests/run_all.py`**, a stdlib runner reporting PASS/SKIP/FAIL. *Why:* no
   single command ran the suite. *Risk:* none.

## 2026-11-04 — Phase 1: Crustle field (`phase1/crustle-field`)

5. **Branch off `feature/multihop-mcts`, not main; draft PR targets that branch.** main is
   far behind the engine (the MCTS/effects work lives on the feature branch), so a PR to
   main would carry hundreds of unrelated commits. main's 5 weekly docs commits were
   merged in so nothing on main is lost. *Alternatives:* PR to main; rebase. *Why:* a
   reviewable diff; no history rewrite. *Risk:* the feature branch still has to reach
   main eventually; this PR stacks on it.
6. **Step-A fixes ported by cherry-pick** (cli `--list`, toucannon window, torch skip,
   `tests/run_all.py`). *Risk:* duplicate commits once both branches merge (same content,
   trivial conflict at most).
7. **Turn order is chosen BEFORE the deal.** `setup_game` draws the coin flip first;
   an explicit `first_player` still consumes the same RNG draw so seeded games stay
   aligned whether or not the caller fixes the order. *Alternatives:* flip after
   mulligans (old). *Why:* rulebook order; the old code let the flip see mulligan RNG.
   *Risk:* every seeded trajectory moved (see 11).
8. **Mulligan draws are paid** — each player draws 1 per opponent mulligan, always taken.
   *Alternatives:* agent hook for the "may". *Why:* declining is almost never right.
9. **Going first: no Supporter on turn 1** (attack lock already existed); **retreat once
   per turn** (`retreated_this_turn`). Both were missing.
10. **Cards added** (exact printed text; Lumiose City logic cross-checked against
    twinleafgg, MIT, credited inline): Dwebble Ascension, Growing Grass Energy (POR 86),
    Lumiose City (POR 77), Festival Grounds (recover-from-conditions half + registration),
    Xerosic's Machinations, Pokémon Center Lady, Snow Sink (registration), plus Basic Box
    pieces (Coordinated Throwing, Cobalt Command, Glass Trumpet). Policies where the card
    gives a choice: Xerosic — opponent keeps its 3 best by `_search_value`; PCL — biggest
    gain (heal + 30/condition), ties to the Active; Glass Trumpet — fewest-Energy Benched
    Colorless first; Lumiose City — only offered when the Bench has room, greedy takes it
    only instead of passing (it ends the turn). Growing Grass Energy's HP bonus is
    refreshed on attach/retreat/KO check. *Risk:* choice policies are heuristics, not
    searched; POR 86/77 are hand-entered in `data/manual_cards.json` (pool rebuild adds
    exactly these 2 cards, 1338 total).
11. **Seeded liveness tests widened** (toucannon 240, doublade 120, gardevoir/hide-n-sneak
    24, mcts_keys 48 games). The rules fixes shift every greedy trajectory; these tests
    assert "the line fires at least once", so a wider window keeps them meaningful.
    *Risk:* a genuinely dead line takes longer to notice; the unit tests cover clauses.
12. **Parallel runner (`cli.py --parallel N --seat-order both|deck1|deck2|coin --out`).**
    Game *i* uses seed `seed+i`; agents get `s` and `s+1_000_000`; `both` alternates who
    goes first (deck1 always seat 0) and reports each seat order separately with Wilson
    CIs. Results are identical for any worker count (only the timing column differs —
    tested). Partial CSV/JSON are rewritten atomically every 200 games so long MCTS runs
    can be read mid-flight. *Finding:* the legacy `cli.run(mirror=True)` swaps SEATS, not
    who goes first (setup flips a coin), so its "mirror" halves are not seat-order
    controls — documented, left as is.
13. **Greedy-bias fixes (B6)** — see the diagnosis below. All read public information
    only and are deterministic (no lookahead):
    - wall-aware attack value / lethal check (Rock Inn, Cornerstone Stance, Sparkling
      Scales, Dig's shield; bypass attacks Superb Scissors/Demolish/Nebula Beam/Shred
      exempt); Phantom Dive keeps a 60 Bench-spread value into a wall;
    - walled-Active pivot: route Energy to a Benched attacker that hits through, retreat
      into it when payable; also retreat when the Active has no legal attack at all;
    - Boss's Orders ahead of draw Supporters when walled; gust target skips walls
      (`_gust_victim`, also Prime Catcher) — engine-side, so MCTS gets it too;
    - promotion after KO prefers a Pokémon that can already pay a damaging,
      non-walled attack (v0: highest HP) — engine-side, both agents;
    - Ultra Ball never pitches the last Energy in hand; Night Stretcher takes a Basic
      Energy when the hand has none and nothing was attached.
    *Alternatives:* simulate each attack on a clone (rejected: peeks at coin flips and
    deck order); leave greedy alone and use MCTS only (rejected: greedy is the 10k-game
    workhorse). *Risk:* changes every deck's greedy play, not only Crustle's matchups; the
    full suite stays green, but historical greedy numbers in docs are not comparable.

### Greedy Crustle bias — diagnosis (2026-11-04)
Calibration (real results, Limitless): Crustle vs Dragapult 62.4% at Gdańsk
(59-29-14, n=102) and 62.4% online (POR, n=202); vs Basic Box 78.9% at Gdańsk (n=30)
and 65.5% online (n=55). Sim greedy before fixes: 93.4% / 93.6%.
Measured over 300–400 logged games per matchup (`scripts/diag_greedy_bias.py`,
`scripts/diag_greedy_passes.py`):
1. **Ex attackers swing into Rock Inn for 0.** 54% of Dragapult's Dragapult ex attacks
   did 0; greedy valued attacks at printed damage and never pivoted. Fixed (13): Jet
   Headbutt into the wall fell from 62% of its uses to 23% (Phantom Dive into the wall
   is now deliberate, for the Bench spread), but the win rate barely moved.
2. **Opponent pilots can't execute the anti-Crustle plans.** Basic Box passed 1,746
   times vs 781 attacks in 300 games — 3-Energy attackers, rainbow typed costs, Energy
   spread across the board; Dragapult's #1 pass reason was "no Energy in hand" (9-Energy
   list, Energy pitched to Ultra Ball). The real anti-Crustle lines (Phantom Dive /
   Munkidori counters on Dwebbles before they evolve, gusting the Bench, item lock, Energy
   concentration) need planning greedy doesn't have.
3. **Crustle's own plan is linear** (Dwebble → Ascension → attach → Superb Scissors,
   heal with Jumbo Ice Cream), which a 1-ply greedy executes nearly perfectly.
Conclusion: (1) was a cheap bot bug and is fixed; (2)–(3) are structural — greedy
rewards linear decks. Greedy Crustle numbers are a relative signal with a large,
known pro-Crustle skew; MCTS (≈79% vs Dragapult before fixes) is closer but still
skewed. Next lever: search-based play for the opponent (MCTS everywhere), not more
greedy special-casing.

## RISKS
- `data/standard_pool.json` is gitignored and rebuilt from upstream data; test results
  and sim trajectories are reproducible only for the same pool build.
- Sim win rates are **relative bot-vs-bot signals** under this engine and these
  pilots, never Live/tournament predictions. Greedy has a measured pro-Crustle skew of
  roughly +25–30 points vs Dragapult and +10–25 vs Basic Box (diagnosis above).
- The rules fixes and bot fixes changed every seeded trajectory; numbers in older docs
  are not comparable to Phase-1 numbers.
- Engine-side choice policies (promotion, gust target, Ultra Ball discard, Night
  Stretcher) are shared by both agents; MCTS doesn't search them.
- The legacy `cli.run(mirror=True)` "mirror" doesn't control who goes first; use
  `--parallel --seat-order both` for seat-order results.
- Remote pushes go through the GitHub connector (the local `gh` token is read-only),
  which pushes file contents, not commits: the remote branch's history won't match the
  local commit graph (main's docs commits arrive as content, not as a merge).
