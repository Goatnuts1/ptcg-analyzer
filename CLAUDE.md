# CLAUDE.md — ptcg-analyzer

Context for Claude Code sessions in this project.

## What this is
A Pokémon TCG deck analyzer. End goal: a deterministic simulator that crunches
game scenarios all day to tune decks and surface edges. Token-cheap by design.

## The non-negotiable architectural rule
**The LLM is never in the game loop.** Games are played by a deterministic
engine (CPU only, zero tokens). The model's jobs are bounded:
1. author card scripts from card text,
2. self-heal: patch a card script when the engine throws on an interaction,
3. synthesize: read aggregate stats and propose deck changes,
4. escalate genuinely hard reasoning to a frontier model via API on a schedule.
Every model output is validated against the engine before it's trusted.

## Current state
- Data layer: done + tested. `data/standard_pool.json` = **1,399 cards** as of the
  2026-09-03 meta-scan (marks H/I/J; 33 in the tracked `data/manual_cards.json`
  supplement — Meowth ex, Mega Charizard Y ex, Poké Pad, Mega Slowbro ex, Mega
  Excadrill ex, Drilbur, Drilbur (TEF), Rocky Fighting Energy, Telepathic Psychic
  Energy, Alakazam, Staryu, Metagross (CRI), the Pitch Black Ghost prints Shuppet
  (PBL) / Banette (PBL) / Dhelmise (PBL) / Poltchageist (PBL) / Sinistcha (PBL) /
  Patrat (CRI) / Dunsparce (JTG), the Gwynn Supporter, and the Pitch Black
  Toucannon line Pikipek / Trumbeak / Toucannon + Hoothoot (SCR), Azumarill ex
  (ASC 84), and the Perfect Order Aegislash line Honedge / Doublade / Aegislash
  (ME03 56/57/58) — merged by the fetch script and deduped by name). The card
  count moves every scan as upstream ships more of "Mega Evolution" (me1-me5);
  don't treat the number itself as a tracked invariant, only the count-in-report.
- `is_standard_legal()` (fetch_standard_pool.py) checks ONLY the printed
  regulation mark now (meta-scan 2026-09-03 fix). It used to also require the
  upstream dump's own `legalities.standard == "Legal"` as a belt-and-suspenders
  ban-catcher — dropped because that field lags real tournament legality by
  set (as of this scan it flagged 112 of me3 "Perfect Order"'s 124 mark-J cards
  "Not Legal", including Mega Starmie ex and Telepathic Psychic Energy, both
  real tournament Standard cards) and because the format currently has ZERO
  individually banned cards (2026 rotation removes by regulation mark only) —
  so the check had no real bans left to catch and was pure false-negative risk.
  A genuine future ban needs explicit handling; this schema has no "Banned"
  value to key off, only "Legal"/"Not Legal".
- PRINT COLLISIONS: when a deck needs a DIFFERENT print of an already-pooled card,
  the new print is added as `"Name (SETCODE)"` and the pool's bare entry is left
  alone (Metagross (CRI), Shuppet (PBL), Dunsparce (JTG), ...). Registry keys use
  the exact suffixed name — that is the whole point, two prints, two behaviors. The
  ONE place the suffix must be ignored is the evolution-name match, because a card's
  `evolvesFrom` names the PRINTED card: `effects.print_base_name()` strips it and
  `game.evolves_onto()` / Rare Candy use that, so a suffixed PRE-evolution
  ("Dunsparce (JTG)") still evolves into its Stage 1.
- PRINT_OVERRIDES (fetch_standard_pool.py, meta-scan 2026-09-03): the general
  "if upstream ships this name, upstream wins and the manual entry is dropped"
  rule assumes upstream shipping a name is the SAME card gaining upstream
  coverage. That breaks when upstream starts shipping a bare name that used to
  be manual-only, under a genuinely DIFFERENT print, processed earlier in
  `list_set_codes()` order — "Drilbur" (manual = Pitch Black pbl-46, Call for
  Family; upstream now also ships Temporal Forces sv5-85, Dig Dig Dig, processed
  first) and "Alakazam" (manual = me1-56, Powerful Hand; upstream now also ships
  sv6-82, Strange Hacking, processed first) are both this shape. "Rocky Fighting
  Energy" / "Telepathic Psychic Energy" are the same fix for a different reason:
  upstream's Energy-supertype JSON never carries a `types` field (what a Special
  Energy provides lives only in free-text `rules`), so upstream's copy would
  silently zero out `InPlayPokemon.provided_types()`. "Staryu" is a same-print
  data fixup (empty `evolvesTo`, cosmetic — `game.evolves_onto()` doesn't read
  it). Names in `PRINT_OVERRIDES` keep their manual entry even after upstream
  starts shipping the same bare name; `Drilbur (TEF)` is a second, independently
  reachable manual entry for the Dig Dig Dig print, not an override.
- Engine: done + tested. `src/engine/` plays full legal games, zero tokens. Core
  rules faithful incl. evolution timing, Stadiums + the two bench chokepoints
  (Battle Cage counters / Tera attack-damage), Special Conditions, Tools, Special
  Energy, MEGA 3-prize rule, self-KO prize awards, ability suppression (Team
  Rocket's Watchtower + Flutter Mane's Midnight Fluttering). Stadiums come in two
  shapes: PASSIVE ones live at the chokepoints (Battle Cage, Gravity Mountain, Area
  Zero Underdepths, Jamming Tower's `effects.tools_disabled` — which blanks EVERY site
  that reads an attached Tool: retreat_cost, refresh_hp_modifiers, apply_attack_damage,
  end_of_turn_tools), ACTIVATED ones are real engine actions with their own
  once-per-turn budget on PlayerState (Surfing Beach's `stadium_switch`, Prism Tower's
  `stadium_draw`, Grand Tree's `stadium_evolve` deck-search evolution chain, Mystery
  Garden's `stadium_garden` discard-an-Energy refill, Team Rocket's Factory's
  `stadium_factory` draw-2 — the only one with a CONDITION, tracked separately from its
  budget as `PlayerState.team_rocket_supporter_played_this_turn`, set in
  `apply_action`'s play_trainer branch and reset by `start_turn` — and Academy at
  Night's `stadium_academy` put-a-hand-card-on-top-of-deck, enumerated PER hand card
  like attach_tool so the agent picks which; it exists to feed Slowking's Seek
  Inspiration top-deck discard). Bench damage-prevention chokepoint has a third
  resident besides Tera and Battle Cage: Shaymin (DRI)'s Flower Curtain (opponent's
  attack damage only, owner's benched non-Rule-Box only, no self-exception on this
  print — added as a manual-supplement print collision, `"Shaymin (DRI)"`). A new action kind must also get
  a `mcts._semantic_key` case or it silently vanishes from search —
  `tests/test_mcts_keys.py` guards that.
- **Deterministic — a tested invariant.** Same seed = byte-identical game,
  in-process (greedy + MCTS) AND cross-process (hash-seed-independent). Guarded by
  `tests/test_determinism.py`. If this breaks, every win rate is worthless.
- Effect system: done + tested. `effects.py` = primitives + registries for attacks,
  abilities, Trainers, Tools, Special Energy. **~176 distinct cards implemented**,
  each asserted against its card text. Includes the namesake archetype lines, a
  draw/search/recovery staple suite, and the Mega Gardevoir / Colorless / Fire /
  Fighting / Dark / Metal / Water attacker sets, plus the Pitch Black-era Metal
  line (`mega_excadrill`: Mega Excadrill ex / Metagross / Genesect ex + the Team
  Rocket search Trainers) and the Mega-era Fighting line (`cynthia_garchomp`:
  Cynthia's Garchomp ex / Gabite / Gible / Roserade / Spiritomb + Surfer, Fighting
  Gong, Premium Power Pro, Cynthia's Power Weight, Rocky Fighting Energy,
  Neo Upper Energy), and the Pitch Black Ghost line (`hide_n_sneak`: the Hide 'n'
  Sneak effect-prevention Ability + its two discard-pile payoffs, Patrat's
  Watchful Eye counter-move lock, Flutter Mane's Midnight Fluttering Ability lock,
  Gwynn, Prism Tower, Legacy Energy), and the Pitch Black Toucannon line
  (`toucannon`: Feather Rondo's both-Benches damage scaling, Aerial Draw,
  Pikipek/Trumbeak's coin-flip attacks + Fly's one-turn shield, Hoothoot (SCR)'s
  Triple Stab, Noctowl's Tera-gated on-evolve Jewel Seeker, Iron Leaves ex's
  Rapid Vernier + Prism Edge, and Area Zero Underdepths), and the real-list Mega
  Gardevoir support (`gardevoir_real`: Marill's Ball Roll, Azumarill ex's repeatable
  Bubble Gathering + Energized Balloon, Zacian's prize-gated Limit Break, Mega Diancie
  ex's Diamond Coat passive, Wally's Compassion, and the Grand Tree / Jamming Tower /
  Mystery Garden Stadiums), and the Perfect Order Aegislash line (`doublade`: Doublade's
  Weaponized Swords, Aegislash's + Steven's Metang's Metal Slash one-turn attack lock,
  Steven's Metagross ex's X-Boot, and Team Rocket's Factory).
  REVEAL IS NOT A COST — a vocabulary first for this engine. Doublade's Weaponized
  Swords does 60 per Honedge/Doublade/Aegislash **revealed from hand**, and revealing
  moves nothing: `_weaponized_swords` must never mutate `ctx.me.hand` (it asserts this
  itself), so one hand of swords keeps paying full damage every turn, forever. Every
  other scaling attack here PAYS by moving cards (Inferno X / Metallic Hammer / Garland
  Ray discard). Don't "fix" it into a discard.
  NOTE: Diamond Coat was a real gap on an already-pooled card — implementing it moves
  the BUILT `gardevoir` archetype (which plays 2 Mega Diancie ex) from ~53% to ~62% vs
  `dragapult` under greedy (n=200). That is a fidelity fix, not a tuning change.
- MULTI-UNIT / WILDCARD Special Energy: `InPlayPokemon.provided_types()` emits one
  token per Energy PROVIDED (not per card), and `"Any"` is a wildcard that
  `game.can_pay_cost` spends against any single typed symbol. Prism Energy on a
  Basic = one `"Any"`; Neo Upper Energy on a Stage 2 = two (so a lone copy pays
  Cynthia's Garchomp ex's `[F][F]` Draconic Buster); Legacy Energy = one `"Any"`
  unconditionally (no stage clause). Scope is ATTACK COSTS only —
  `energy_count()` still counts CARDS, so retreat cost and "Energy attached" counts
  do NOT see the 2-at-a-time amount. Don't claim otherwise.
- HP-CHANGING effects: `InPlayPokemon.max_hp` = printed HP + `hp_modifier`, and
  `hp_modifier` is DERIVED — `effects.refresh_hp_modifiers()` recomputes it from the
  Stadium in play (`STADIUM_HP_MODIFIERS`; Gravity Mountain = −30 HP per Stage 2) PLUS
  the attached Tool (`TOOL_HP_MODIFIERS`; Cynthia's Power Weight = +70 HP for a
  Cynthia's Pokémon). It runs at the top of `process_knockouts` and after
  play_stadium/attach_tool/evolve, so a Pokémon
  whose max HP drops to its damage total is Knocked Out immediately. Never accumulate
  into `hp_modifier` — always let the refresh own it.
- BENCH SIZE is per-player and DYNAMIC, not the constant. `PlayerState.MAX_BENCH = 5`
  is only the DEFAULT; the live cap is `effects.bench_limit(state, player)`, which
  returns 8 for a player who has a Tera Pokémon in play while Area Zero Underdepths is
  the Stadium. EVERY Bench-placement site reads it (game.legal_actions, search_deck,
  Poffin, Precious Trolley, Call for Family, Come and Get You, ...) — never read
  MAX_BENCH directly again. `effects.enforce_bench_limits(state, first_index)` runs the
  card's two shrink clauses (last Tera leaves play; the Stadium leaves play, its owner
  discarding first) and is called from process_knockouts, apply_action's play_stadium
  branch, and Snow Sink. A Bench discard is NOT a Knock Out — no prizes are awarded.
- Decks (`decks.py`): seven faithful tournament lists (`dragapult`, `charizard_xy`,
  `mega_excadrill`, `cynthia_garchomp`, `hide_n_sneak`, `toucannon`,
  `gardevoir_real` — Anar Guliyev's Regional Utrecht Mega Gardevoir list, WEAK
  provenance at 310th place, registered alongside the built `gardevoir` archetype
  which stays the tuned baseline), plus two LADDER-provenance lists (a fourth
  provenance class — reconstructed from logged TCG Live games, no tournament
  finish): `slowking_annihilape` (the Seek Inspiration toolbox that beat the
  house `mega_excadrill` twice on ladder, 2026-08 — adds Annihilape's Destined
  Fight both-Actives effect-KO, Smoochum's Delightful Kiss, and the REAL Academy
  at Night top-deck -> Seek Inspiration combo, all livefire-verified) and
  `mega_excadrill_shaymin` (the anti-Slowking counter-build: +2 Shaymin (DRI)
  Flower Curtain bench protection, +1 Gravity Mountain for the Stadium war)
  plus ten built archetypes (`raging_bolt`, `gardevoir`, `colorless`, `fire`,
  `fighting`, `dark`, `metal`, `water`, `greninja`, `beedrill`), in the `DECKS` registry;
  `load_deck(db, name)`. `doublade` is a third provenance class — a DECK-GUIDE build for
  the new Perfect Order Aegislash line, with no tournament finish behind it at all; its
  deck comment says so and its win rates should be read that way.
- Agents (`agents.py`): RandomAgent, GreedyAgent (hand-written priorities + general
  Item/Supporter fallbacks so no implemented Trainer is ever inert), EvalAgent
  (1-ply over `position_value`). MCTS in `mcts.py` (see below).
  GreedyAgent carries four NARROW Slowking/Shaymin pilot branches (each observed
  necessary in livefire, each scoped so no other archetype's play changes):
  Academy at Night plants the hand's best seek-value toolbox mon only when the
  Active is Slowking (>= 130 refuses to bury a Slowpoke); Seek Inspiration is
  valued at the top card's seek_value ONLY when this player planted it this turn
  (player-legal info), else its printed 0; energy routes to a Slowking short of
  [P][C] before the default attach-to-Active; retreat promotes a benched
  fueled Slowking; and Shaymin (DRI) outranks the random bench pick (Flower
  Curtain only works from the Bench). `effects.SEEK_VALUE_OVERRIDES` is the
  shared rank table (Destined Fight 400 / Trifrost 250) for attacks whose whole
  payoff is a 0-printed-damage registered effect.
- Validated: greedy beats random ~99%; MCTS beats greedy ~61%; effects fire in
  real games. Matchup-fidelity findings in `docs/VALIDATION_RESULT.md`.

## Effect system (`src/engine/effects.py`)
Hybrid: primitives + registries. Attack/ability registries keyed by
(card_name, move_name); Trainer registry keyed by card_name with a parallel
can_play predicate. Engine hooks: `_resolve_attack`, use_ability branch,
play_trainer branch. KO logic shared in `process_knockouts` (scans bench).
IMPORTANT: in play_trainer the card is popped from hand BEFORE the effect runs,
because effects mutate the hand (learned bug — index shift).

- MCTS agents: done + tested. `src/engine/mcts.py` holds TWO, and they are
  independent on purpose.
  `MCTSAgent` (`--agent mcts`) = GameState.clone() + determinize() (PIMC, hidden
  info) + UCT, with a `position_value` leaf (`rollout="eval"`) and a multi-turn
  negamax tree across the turn boundary (`search_plies=N`). Beats greedy ~61%
  (single-turn, greedy rollout). **Its defaults are frozen** — every recorded
  gauntlet number was measured with them.
  `ISMCTSAgent` (`--agent mcts2`) = cross-turn Single-Observer Information Set
  MCTS (see the MCTS notes below).
  `tests/test_mcts*.py` + `tests/test_ismcts.py` check clone/determinize
  correctness, negamax sign handling, information-set bookkeeping, and strength.

## MCTS notes (`src/engine/mcts.py`)
- clone() shares immutable Card refs, copies mutable wrappers — keep it that way.
- determinize() conserves the exact card multiset and preserves the acting
  player's known info (own hand, public board/discard); reshuffles hidden zones.
- `MCTSAgent`'s tree spans `search_plies` turn-segments (default 1 = single turn,
  the CLI uses 2); the rest is rolled out or evaluated. Re-determinizing per
  iteration into ONE shared tree is PIMC-with-a-shared-tree, not ISMCTS.
- `ISMCTSAgent` is the information-set version. A node is an INFORMATION SET of
  the player acting there, so successive iterations arrive under determinizations
  with DIFFERENT LEGAL ACTION SETS. Only actions legal in the current
  determinization are considered, and each child carries an AVAILABILITY count —
  UCB normalises by `log(avail)`, not `log(parent.visits)`. Without that, an
  action legal in 1 world out of 10 looks permanently under-explored and gets
  chased as if always available: strategy fusion, i.e. the search learning lines
  that presuppose knowledge of the opponent's hidden hand.
  `max_turn_hops` = turn-segments of tree (default 3), `position_value` at the
  leaf, `leaf_finish_turn` (default on) finishes the current turn greedily first —
  QUIESCENCE, not a rollout, because a leaf taken mid-turn scores a board whose
  attack has not landed yet. HONEST LIMIT: single-observer. Opponent nodes are
  indexed by the ROOT player's determinization, so the opponent is modelled as
  seeing that world, not its own information set. MO-ISMCTS is not built.
- Tree reuse (`reuse_tree`) retains the chosen child's subtree for the next
  decision and credits its visits against the budget. Scoped to ONE TURN: across a
  turn boundary the opponent moves an unknown number of times, so descending our
  key-indexed subtree would graft statistics onto a position that never occurred.
  Default OFF for `MCTSAgent` (it would move the recorded numbers), ON for
  `ISMCTSAgent`. Measured on `MCTSAgent`: ~7% faster per decision (104 vs 117
  iters/decision) — but NOT faster in games/sec, because better play makes games
  longer.
- Actions are de-duplicated by semantic key (same card from different hand slots,
  same energy type to same target) so the iteration budget isn't wasted. Both
  agents use it; UCB and final-move ties break on key order, so nothing depends on
  dict/set iteration luck (`tests/test_determinism.py` covers mcts2 cross-process).
- MEASURED, n=60/cell, seed 2026, mirrored seats, deck under test piloted by each
  agent against the SAME greedy-piloted opponent (this is the strength read; a
  both-sides matchup % is not one). mcts2 is at 45–60 iters so its wall clock is
  at or below mcts@120's:
  ```
  deck under test (greedy opponent)   greedy    mcts@120       mcts2
  cornerstone_box  (crustle_modern)    31.7%   26.7% 13.1s   31.7% 10.7s
  crustle_modern   (cornerstone_box)   75.0%   31.7% 26.2s   73.3% 13.2s
  clefairy_stock   (mega_excadrill)    15.0%   18.3% 31.6s   33.3% 21.5s
  mega_excadrill   (clefairy_stock)    76.7%   66.7% 16.8s   70.0% 16.8s
  raging_bolt      (dragapult)         16.7%   31.7% 18.7s   35.0% 15.1s
  cornerstone_box  (clefairy_stock)    86.7%   70.0% 20.9s   91.7% 15.0s
  mean                                 50.3%   40.9% 127.3s  55.8% 92.3s
  ```
  mcts2 beat mcts in all six contexts using 27% less total wall clock. Note the
  uncomfortable half of the same table: `mcts` averages BELOW greedy here, and
  mcts2 only clears greedy by ~5pt. Search is not yet a free upgrade over the
  hand-written pilot on aggro decks.

## Using it — the CLI (`cli.py`) or the web UI
The "crunch all day" entry point. Decks are referenced by name from `DECKS`. There's
also a zero-dependency local web UI (`src/web/server.py`) — `python3 cli.py --serve`
opens http://127.0.0.1:8000 with click-to-run matchup / who-would-win / meta-matrix
pages. End-user instructions live in `USAGE.md`.
```
python3 cli.py --serve                                          # local web UI (browser)
python3 cli.py --list                                           # available decks
python3 cli.py --deck1 dragapult --deck2 charizard_xy --games 5000   # win rates
python3 cli.py --round-robin --games 200                        # matrix + Elo tier ranking
python3 cli.py --round-robin --export meta.html                 # CSV/HTML heatmap export
python3 cli.py --who-would-win gardevoir fire                   # fun plain-language readout
python3 cli.py --deck1 dragapult --deck2 raging_bolt --seed 42 --save-game myrun
python3 cli.py --replay saved_games/myrun.json                  # step-by-step replay
python3 cli.py --import-deck --name mydeck                      # paste a TCG Live export (stdin)
```
Battle-log import (`src/importers/tcglive_log.py`): the sibling that imports a GAME, not
a deck — the in-app battle log as pasted text -> an event tree (`parse_log`) plus a
fidelity report (`analyse` / `format_coverage`). Measured on 53 real ladder games:
**99.9% of lines parse**, the residue being human chat pasted alongside. It PARSES ONLY —
it does not drive `GameState`; a replay harness is the next piece. Two things it must keep
doing: anchoring possessive splits on a discovered player handle (card names contain "'s"
— "N's Zoroark ex"), and keeping `draw_named` vs `draw_hidden` distinct, because a log is
SINGLE-OBSERVER (`GameLog.observer` = the seat it was copied from). What the corpus found
is in `docs/TCGLIVE_LOG_FIDELITY.md`: the automated pool fetch has ZERO coverage of
PBL / ASC / ME05 / CRI — every card the project owns from those sets is one of the 26
hand-added `data/manual_cards.json` entries — and bare log names can't identify a print
(the log writes "Metagross", never "Metagross (CRI)"), so the import path needs a
print-resolution step keyed on the move actually used.

Deck import (`src/importers/tcglive.py`): paste a Pokémon TCG Live deck export and it
parses qty+name (stripping set codes like `MEG 50`), matches against the pool
(accent/case-insensitive, energy normalised), reports matched/missing + legality, and
writes the engine-format recipe to `decks/imported/<name>.json`.
Matchups mirror seats (cancels the going-first edge) and are deterministic by
`--seed`. `--agent` is `greedy` (default, ~900–1000 games/sec), `random`, `mcts`
(far slower), or `mcts2` (cross-turn ISMCTS; ~mcts speed at `--iters 60`). Save files store the reproducible recipe + full step log; replay
re-simulates from the seed and verifies the log matches byte-for-byte.
`--agent2` (+ `--iters2`) pilots deck2 with a DIFFERENT agent at its own iteration
count — the way to compare two pilots on one deck at equal wall clock. Omit it and
`run()` behaves exactly as before, single-pilot.
`src/engine/run.py` is the lower-level batch loop; `src/engine/matchup.py` is the
instrumented validation runner (win% + right-lines evidence).

## Meta-2026-08 build (the three missing top-10 archetypes — now IN)
`dragapult_blaziken` (Jon Webb NAIC 6th — TOURNAMENT provenance), `festival_lead`
(online-event 12-0-1 list, "Dreamjew"), `grimmsnarl_froslass` (Andrew Choi NAIC 128th —
WEAK provenance) are registered, effects in the §META-2026-08 section of effects.py,
tested in `tests/test_meta_2026_08_lines.py`. Engine mechanics this build added — each
lives at a chokepoint, know they exist:
- **Festival Lead attack-twice** (`game._resolve_attack` tail): Dipplin / Goldeen /
  Seaking (PRE) repeat their attack when Festival Grounds is the Stadium; the repeat
  targets whatever is Active AFTER process_knockouts (that's the card's clause), costs
  nothing, and is gated on `fx.has_festival_lead` (reads the card's ability list, not a
  name table). Confusion is checked once per declaration.
- **Pokémon Checkup window** (`fx.pokemon_checkup`, called from `game.end_turn`):
  currently hosts Froslass's Freezing Shroud (1 counter per un-suppressed Froslass on
  every Ability-holder except Froslass, both sides — checkup counters are NOT attack
  effects, so Battle Cage/Rocky walls don't apply). New between-turns residents go here.
- **Spikemuth Gym** = seventh ACTIVATED Stadium (`stadium_spikemuth`, own budget field,
  reset in start_turn, cloned in state.py, `mcts._semantic_key` case). Its action is
  enumerated per distinct Marnie's NAME (sorted) — deck ORDER is hidden info and must
  not leak into the action encoding.
- **Gladion's Final Battle** = `PlayerState.bonus_damage_nonrulebox` (turn-scoped, like
  Kieran's flag) applied in `apply_attack_damage`'s bonus block; can_play is hand==1
  (evaluated PRE-pop, so the hand holds exactly the card itself).
- **Rabsca "Spherical Shield"** joined the bench-prevention chokepoints (damage half in
  apply_attack_damage — NO Rule-Box clause, unlike Flower Curtain — and the
  effects-of-attacks half in place_counters, effect_kind=="attack" only).
- **Forest of Vitality** waives only the played-this-turn clause for Grass-into-Grass
  in legal_actions' evolve block. **Festival Grounds** condition-immunity =
  `fx.can_be_conditioned`, guarded at both confused=True sites.
- Manual-supplement additions (real text from limitlesstcg): `Seaking (PRE)` (Festival
  Lead + Rapid Draw — print collision, TWM print differs), `Applin (SCR)`,
  `Gladion's Final Battle`. Pool is now 1,305.
- HONEST LIMIT: `festival_lead` under pure greedy reads ~7% vs mega_excadrill — that is
  PILOTING, not the deck (real WR 51.18%). Greedy has no Gladion hand-management and no
  bench-width preference; treat greedy numbers for this archetype as a floor.


## The overnight matrix (2026-08-17) — the current strength read
`docs/BEST_DECK_2026-08.md` + raw cells in `docs/matrix_2026-08_mcts2.json`: 159
pairings, both sides mcts2@60, n=60, seed 2026 — 20 candidates vs the 14-archetype live
field (63.1% of the Limitless meta representable). Headline: `fighting` tops the mean
(80.8%, aggro-bias caveat applies in full) but **`crustle_modern` is the only deck with
no losing matchup** (floor 53.3%) — the maximin best. `mega_excadrill` is 6th (64.8%)
with exactly two bad cells: fighting 15%, grimmsnarl_froslass 46.7%. festival_lead
(32.8%) and slowking_annihilape (32.0%) are PILOT FLOORS, not ratings — both
contradict external evidence (51.18% real WR; two direct ladder wins). Greedy pilot
corrections from the Fable review live in agents.py (nine scoped branches: Festival
promotion/fuel/bench-to-5/Gladion-hold/Bangle-targeting/Wave-valuation, Grimmsnarl
promotion, Blaziken lock-pivot, Munkidori/Dragapult signature energy routing) and one
evaluation.py term (Do the Wave leaf value). All scoped so previously-recorded numbers
do not move; verified by spot-check.

## Real-world calibration (2026-08-17) — READ BEFORE QUOTING ANY WIN RATE
`docs/META_GAUNTLET_2026-08.md` measures the house `mega_excadrill` against the LIVE
Limitless PBL-Standard metagame. The result is a calibration failure, and it is the most
important number we have: **the sim rates the deck at ~63% share-weighted vs the field;
its real win rate is 49.51%** on thousands of recorded games, where it is the format's
MOST-PLAYED deck (7.79%). Search helps but doesn't close it — greedy 73.6% -> mcts2 65.7%
over the same 9 matchups. Treat the gauntlet as a tool for FINDING BAD MATCHUPS
(`fighting` 33.3%, `alakazam_deck` 45.0% — both run against the aggro bias, so both are
credible), never as a power ranking. Three sim numbers are known-bogus and flagged there
(N's Zoroark 93.3% = combo mispiloting; Dhelmise 91.7% = wrong proxy deck; Slowking 75.0%
is contradicted by our own ladder record). 17.4% of the live field has NO deck in the
registry — Festival Lead (6.75%), Dragapult Blaziken (5.99%, the deck that beat us), and
Grimmsnarl Froslass (4.66%); the cards are almost all in the pool already, but none of the
archetype-defining effects are implemented. Real ladder matches are recorded in
`docs/LADDER_LOG.md`.

## Validation status (see `docs/VALIDATION_RESULT.md`)
Card-implementation milestone is COMPLETE (both tournament lists fully faithful).
The matchup number, however, reads more EVEN than reality: sim rates Dragapult vs
Mega Charizard ~53–59%, published Limitless ~84%. This is NOT a card/engine-fidelity
failure — it's **agent/policy strength**: greedy and single-turn eval-MCTS don't yet
express Dragapult's multi-turn spread+disruption plan. The strength lever (deeper
MCTS / better target policies) is the open frontier, deliberately deprioritized in
favor of a solid, usable, trustworthy core.

## Known limitations (be honest about these)
- **Greedy mispilots complex decks.** It ranks attacks by printed damage and can't
  sequence multi-step plans, so e.g. `raging_bolt` (discard-energy-for-damage,
  2-type cost) underperforms (~16–28% vs dragapult) and games frequently end by
  self-deck-out rather than prizes. The CARDS are correct (unit-tested); the
  *piloting* is weak. Use `--agent mcts` for stronger (slower) play, or read win
  rates as greedy-piloted, not optimal.
- **The greedy `--round-robin` matrix over-rates aggro.** Greedy plays a simple
  beatdown near-optimally but butchers combo/setup decks, so the matrix inflates
  aggressive decks and deflates combo decks. Measured: `fighting` (Mega Lucario)
  reads 86.8% under greedy but ~73% under MCTS-both (−14pt); its 64% edge vs
  `gardevoir` flips to a 43% loss when both sides are piloted well. Treat the matrix
  as a fast first read, not a power ranking; confirm standouts with
  `cli.py --round-robin --agent mcts` (uses 50 iters / 24 games per pair by default).
- Cross-turn ISMCTS IS now built (`--agent mcts2`, see MCTS notes) — but it is
  SINGLE-observer, and hidden-hand-aware *evaluation* is still not built.
  `docs/VALIDATION_RESULT.md` predates mcts2; its "not built" wording is stale,
  its verdict is not.
- **The two documented divergence matchups do NOT converge under mcts2.** Both
  sides piloted by the same agent, n=60, seed 2026:
  ```
                                     greedy    mcts@120      mcts2@60
  cornerstone_box vs crustle_modern   31.7%   55.0% 47.6s   35.0% 27.6s
  clefairy_stock  vs mega_excadrill   15.0%   50.0% 53.6s   40.0% 56.0s
  ```
  mcts2 lands BETWEEN greedy and mcts, closer to greedy. A deeper, better-founded
  search moving the number back toward greedy's read is a real finding, not a
  regression to explain away: it says `mcts`'s 55%/50% were not simply "what a
  strong pilot sees". Do not quote any of the three as the true matchup number.

## Card legality
The Mega ex mechanic is current (mark I). Old SV-base ex (Charizard ex, Gardevoir
ex, mark G) rotated OUT — always check the pool, never card-name memory. Rotation
lives in one place: `STANDARD_LEGAL_MARKS` in `src/engine/legality.py`.
