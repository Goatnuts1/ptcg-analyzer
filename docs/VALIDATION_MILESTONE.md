# Validation Milestone — Build Order

Goal: make the two current tournament lists (Dragapult ex; Mega Charizard X/Y ex) **fully
faithful**, then run the MCTS matchup and compare to the published win rate (target within
~5–8%, logged in REVIEW_LOG). Scope is set by `docs/CARD_GAP_REPORT.md`: **35 distinct new
effects + 3 missing pool cards + ~10 engine subsystems.**

Design owner: Claude (handed off). All decisions below are made, not deferred. The §2.9
MEGA/Tera rules are **confirmed** from an authoritative ruling (turn-ends-on-Mega-Evolve;
3-prize MEGA; Tera blocks attack *damage* to the bench but not effect *counters*).

## Guiding rules (inherited, non-negotiable)

- **LLM never in the game loop.** Every effect is hand-written Python composing primitives.
- **Every effect ships with a test** asserting it does exactly what the card text says.
  No test → not trusted → doesn't count toward "done."
- **No silent caps.** If an effect is stubbed or a policy is greedy-only, `log()`/comment it
  and list it in §5. A gap report that hides stubs is the failure mode we're avoiding.
- **vanilla-ok ≠ implemented.** Tracked separately, forever.

---

## §0 — Definition of Done is a TEST, not a vibe (build this FIRST)  ·  ✅ DONE

`tests/test_decklist_coverage.py` is live and is the milestone burndown.

1. ✅ Both 60-card lists registered as fixtures in `src/engine/decks.py`
   (`TOURNAMENT_DRAGAPULT`, `TOURNAMENT_CHARIZARD_XY`, `TOURNAMENT_LISTS`,
   `load_tournament_deck`) — exact card+count from the gap report. *(Chose Python recipes
   over `data/decks/*.json` to match the existing fixture style and avoid a new loader.)*
2. ✅ Test A — **loads:** every card resolves; each deck totals exactly 60.
3. ✅ Test B — **coverage SNAPSHOT (green-when-correct):** classifies every card as
   `vanilla-ok` / `implemented` / `needs-effect` and asserts the live state matches a recorded
   manifest (`EXPECTED_NEEDS_EFFECT` + `IMPLEMENTED_BY`). It is **green when the code matches the
   documented gap** and red ONLY on real drift — a regression (an implemented card falls back to
   vanilla), unrecorded progress (an effect landed but the manifest wasn't updated), or
   `implemented`-without-a-named-test. *(Reshaped from an earlier red-by-design version — a
   perpetually-red test poisons the "all green = trustworthy" invariant. The anti-flattery value
   is preserved: drift in either direction fails loudly, and a card can't be counted done unless
   a named test mentions it.)*

Current reading (green): **7 implemented+tested · 30 needs-effect distinct cards · 5 vanilla-ok.**
Burn down by moving a card from `EXPECTED_NEEDS_EFFECT` into `IMPLEMENTED_BY` (with its test) as
each effect lands; when `EXPECTED_NEEDS_EFFECT` is empty, both lists are fully faithful.

---

## §1 — Data layer (unblocks loading)  ·  ✅ DONE

- [x] Added 3 cards (pool 1273 → **1276**): **Meowth ex** (`me3-121`, mark J, 170 HP,
      Last-Ditch Catch), **Mega Charizard Y ex** (`asc-22`, mark I, 360 HP, Explosion Y,
      3-prize MEGA rule), **Poké Pad** (`por-81`, mark I, Item). Schema mirrors the existing
      Mega Charizard X ex entry; `test_pool.py` invariants pass.
- [x] **Made durable (the artifact is gitignored):** the 3 cards live in tracked
      `data/manual_cards.json` (un-ignored via `.gitignore` exception) and
      `fetch_standard_pool.py` now merges them, deduped by name (upstream wins if it ever
      ships them → then delete from the supplement). A re-fetch reproduces 1276
      deterministically; without this, `python3 src/fetch_standard_pool.py` would silently
      drop them and break the fixtures.
- [x] Two deck fixtures added (§0.1); both expand to 60, all cards resolve.
- [x] Test A green. (`test_pool.py` size-comment re-baselined to 1276.)

---

## §1.5 — Format / rotation framework  ·  ✅ DONE

So we only ever work on currently-legal cards and can rotate cleanly later.
`src/engine/legality.py` is the **single source of truth** for the format:
- [x] `STANDARD_LEGAL_MARKS = frozenset({"H","I","J"})` — the one place rotation lives.
      `fetch_standard_pool.py` now **imports** it (was a buried duplicate), so the build-time
      pool filter and runtime checks can't drift. **Rotation = edit this set, re-fetch, re-test.**
- [x] **Manual supplement respects rotation** — `fetch` now drops a `manual_cards.json` card
      whose mark isn't legal (was a latent bug: rotated manual cards would have lingered).
- [x] `validate_deck(db, recipe, legal_marks=…)` checks: legal marks (the rotation check),
      the 4-copy rule (Basic Energy exempt), the 1-ACE-SPEC rule, and 60-card size — returning
      the exact violations. `is_deck_legal()` / `DECK_SIZE` / `MAX_COPIES` alongside.
- [x] `tests/test_legality.py`: both tournament lists are legal NOW (a future rotation that
      breaks one fails loudly and names the cards), each construction rule is caught, and a
      **simulated rotation** (shrinking legal marks to `{H}`) flags the I/J cards — proving the
      framework detects rotation rather than silently passing illegal decks.
- *Card-text source for §3:* Bulbapedia's Gen-IX index is the per-card gateway; only
  currently-legal (mark H/I/J) cards are in scope. See memory `reference_ptcg_card_text`.

---

## §2 — Engine subsystems (infra), ordered by leverage × matchup-impact

> **THE BUILD ORDER IS SUBSYSTEMS-FIRST (R8 review).** Don't think of this milestone as
> "grind 35 registry functions" — think of it as **~8 engine subsystems, after which the
> effects fall out cheaply** (most become a few-line registry entry). The critical path runs
> through the subsystems, not the effect count, because the two namesake cards and the single
> most matchup-relevant card (Battle Cage) all sit behind infra. Several subsystems are
> non-trivial in their own right (Stadium framework ✅, Special Conditions, an
> ability-suppression layer, Special Energy). Sequence:
> **Battle Cage/Stadiums ✅ → Tera + MEGA ✅ → Special Conditions → draw/search engine →
> the long tail of Trainers/Tools/coin-flips/Special-Energy.** (✅ = done in R8.)

Each subsystem is its own PR with its own tests. **Build infra before the effects that need
it** — an effect written against missing infra is the "half-implemented, inert" trap.

### 2.1 Primitive: generalized deck search  ·  **highest leverage**
Unblocks (current lists): Poké Pad, Ultra Ball, Hilda, Dawn, Nest Ball*, Crispin, Fan Call.
- [ ] `search_deck(ctx, predicate, dest, count, reveal=True, shuffle=True, policy=...)` →
      to hand or bench. Reuse the value-heuristic from `dig_and_pick` as the default policy;
      expose a hook so MCTS can later own the choice (same pattern as `place_counters_on_bench`).
- [ ] Cost wrappers: Ultra Ball discards 2 first (legality gate `can_play`).
- *Note:* Buddy-Buddy Poffin (done) and Rare Candy (done) already cover their own searches.

### 2.2 Primitive: discard-pile retrieval
Unblocks: Night Stretcher (done-ish? no — needs entry), Energy Retrieval, Powerglass (attach
from discard), Super Rod*.
- [ ] `recover_from_discard(ctx, predicate, dest, count)`.

### 2.3 Primitive: hand reset / shuffle-draw
Unblocks: Lillie's Determination, Judge, Unfair Stamp; per-player variants.
- [ ] `shuffle_hand_into_deck(ctx, who)` + `draw`. Lillie's conditional (8 at exactly 6
      prizes); Judge hits both players; Unfair Stamp gated on "a Pokémon KO'd last turn"
      (needs the KO-last-turn flag from 2.7).

### 2.4 Coin flips
Unblocks: Crushing Hammer, Dunsparce Dig.
- [ ] `flip(ctx)` / `flip_until_tails(ctx)` off `ctx.rng` (determinism-safe — clone/determinize
      must preserve rng seeding; add a `test_mcts` assertion that flips are reproducible).

### 2.5 Stadium framework + the TWO bench chokepoints  ·  **matchup-critical**  ·  ✅ DONE
Unblocks: **Battle Cage** (×3 in Charizard list — now `implemented`), Team Rocket's Watchtower
(playable via the zone; its passive effect is still §3), plus the conditionals Chi-Yu Ground
Melter / Fan Rotom Assault Landing (they read `current_stadium_name`).
- [x] `GameState.stadium` + `stadium_owner` slot (cloned); `play_stadium` action with
      play/replace/discard + "same-name can't replace" + once-per-turn
      (`stadium_played_this_turn`). Wired into `legal_actions`/`apply_action`.
- [x] **Two distinct chokepoints, NOT merged** (in `effects.py`, identity-based via `_on_bench`):
  - `place_counters(ctx, target, n, owner)` — effect counters; consults **Battle Cage**
    (prevented on a benched Pokémon when the source is the opposing player; symmetric).
    `place_counters_on_bench` now routes through it.
  - `apply_attack_damage(ctx, target, amount, owner, source)` — attack damage; applies W/R to
    the Active and **Tera** bench-immunity to a benched target. `damage_active_with_weakness`
    and `_resolve_attack`'s direct hit now route through it.
- [x] Phantom Dive verified: 200 to Active lands through `apply_attack_damage`; its 6 counters
      go through `place_counters` and are shut off by Battle Cage. Covered by
      `tests/test_stadium.py` (Battle Cage prevention, own-bench exemption, Tera bench vs
      Active, orthogonality). **Caught + fixed a latent bug:** `mon in bench` used dataclass
      value-equality and mis-located identical Pokémon — now identity (`is`) everywhere.

### 2.6 Special Conditions framework
Unblocks: Munkidori Mind Bend (Confusion), Dusknoir Shadow Bind (can't-retreat),
Budew Itchy Pollen (can't-play-Items), Dunsparce Dig (prevent damage/effects).
- [ ] Status flags on `InPlayPokemon` (confused, cant_retreat) + per-player turn flags
      (cant_play_items). Hook checks at: retreat legality, item-play legality, attack
      resolution (Confusion self-hit), damage application (Dig prevention). Clear at correct
      timing (between turns / on switch).

### 2.7 KO-on-own-board + KO-last-turn tracking
Unblocks: Dusclops/Dusknoir **Cursed Blast** (self-KO awards opponent prizes), and the
"a Pokémon was KO'd last turn" gate for Fezandipiti **Flip the Script** + Unfair Stamp.
- [ ] Generalize `process_knockouts` so KOs on the **acting player's own** board award prizes
      to the **opponent** (Cursed Blast is a cost). Verify bench-scan already handles it.
- [ ] Record `koed_last_turn` per player at end of turn.
- *Scope win:* the old Feb list's **Psyduck (Damp)** ability-suppression layer is **out of
  scope** — Psyduck isn't in the current X/Y list. Cursed Blast no longer needs a counter.

### 2.8 Pokémon Tool framework
Unblocks: Air Balloon (passive retreat −2), Powerglass (end-of-turn trigger).
- [ ] Tool slot on `InPlayPokemon`; attach legality (1/Pokémon); passive modifier hook
      (retreat cost); end-of-turn trigger hook. (TM:Evolution's grant-attack is *not* in the
      current lists — defer.)

### 2.9 MEGA + Tera Pokémon rules  ·  **fidelity of the namesake cards** (verified vs OFFICIAL rulebook)
Source of truth: the official 2026 *Pokémon TCG Web Rulebook* (saved locally), Appendix 1 (p23),
Appendix 6 (p27), glossary (p43). **Verifying against the primary source overturned a wrong rule
we'd taken from a web summary — see the MEGA note.**
- [x] ✅ **Tera** (Dragapult ex) — done in §2.5, CONFIRMED by rulebook p27: *"Tera Pokémon ex
      have … a new effect that prevents all attack DAMAGE done to them while they're on your
      Bench. This effect applies to all attacks, both yours and your opponent's."* So it's attack
      **damage** (handled in `apply_attack_damage`), not effect counters (`place_counters` still
      lands — Phantom Dive's spread is unaffected; only Battle Cage stops it). "Both yours and
      your opponent's" → the chokepoint prevents bench attack damage regardless of source. ✅.
      Tera ex give up 2 prizes (regular ex) — matches `gives_up_prizes`. Covered by
      `tests/test_stadium.py`.
- [x] ✅ **MEGA** (Mega Charizard X ex / Y ex) — DONE, but the rule is the OPPOSITE of what a web
      summary told us. **Current "Mega Evolution Pokémon ex" (lowercase ex) have NO turn-ending
      rule.** Rulebook p23: *"Unlike the older Mega Evolution Pokémon-EX from the XY Series, there
      are no special rules when it comes to playing Mega Evolution Pokémon ex."* The
      "your-turn-ends-when-you-Mega-Evolve" rule belongs to the **rotated XY-era uppercase
      `Mega Evolution Pokémon-EX`** (p39/p43) — NOT these cards.
  - ✅ The only drawback is the **3-prize KO** (`gives_up_prizes = 3`, already in `cards.py`;
    confirmed p23/p43). Normal Evolution rules otherwise (direct evolve or Rare Candy).
  - ⛔️ **Reverted** the turn-end hook I had added to the `evolve` branch and `_rare_candy` — it
    was modeling the wrong (rotated) card class. `tests/test_mega.py` now asserts Mega-Evolving
    does NOT end the turn (both paths) + 3 prizes. Mega Charizard X ex stays `implemented`.
    **infra-blocked = 0.** *(Lesson logged: for rules, go to the official rulebook, not search
    summaries — a "Mega Evolution Pokémon ex" vs "Pokémon-EX" casing difference flipped the rule.)*

### 2.10 Special Energy framework
Unblocks: Enriching Energy (provides Colorless; draw 4 on attach-from-hand; ACE SPEC).
- [ ] Energy cards carry a `provides` type set + optional on-attach trigger; loader stops
      assuming basic-only. Enforce the **ACE SPEC one-per-deck** rule in deck validation
      (also covers Unfair Stamp, and Battle Cage is *not* ACE SPEC — don't over-restrict).

---

## §3 — The 35 effects, grouped by the subsystem they ride on

Write each as registry entry + test, immediately after its subsystem is green. (✓ = already
done; listed for the matchup's sake.)

**Search/draw engine (2.1–2.3):** Poké Pad · Ultra Ball · Hilda · Dawn · Crispin ·
Lillie's Determination · Judge · Dudunsparce Run Away Draw · Fan Rotom Fan Call ·
Night Stretcher · Energy Retrieval · Unfair Stamp · Meowth ex Last-Ditch Catch.

**Energy acceleration:** Oricorio ex Excited Turbo · Crispin (also accel) · Powerglass ·
✓Teal Dance-style pattern reused.

**Damage / KO manipulation (2.5–2.7):** ✓Phantom Dive (rewire through 2.5) · Munkidori
Adrena-Brain · Munkidori Mind Bend · Dusclops Cursed Blast(5) · Dusknoir Cursed Blast(13) ·
Dusknoir Shadow Bind · Fezandipiti Cruel Arrow · Fezandipiti Flip the Script ·
Moltres Fighting Wings · Mega Charizard Y ex Explosion Y · Chi-Yu Allure/Ground Melter ·
Fan Rotom Assault Landing · Dunsparce Dig.

**Stadiums/Tools/board (2.5/2.8):** Battle Cage · Team Rocket's Watchtower · Air Balloon ·
Switch · Boss's Orders ✓.

**Status/lock (2.6):** Budew Itchy Pollen · (Confusion/can't-retreat covered above).

**Pokémon passives:** Charmander Agile (retreat modifier via 2.8 layer) ·
Duskull Come and Get You.

**Special Energy (2.10):** Enriching Energy.

---

## §4 — Priority tiers (recommended order within the effect work)

Tier by win-rate impact, so the first validation run is meaningful even if the long tail
isn't finished. **If a P2 is stubbed for the first run, log it (§5) — never silently.**

- **P0 — matchup is wrong without it:** Battle Cage + bench-damage chokepoint · MEGA 3-prize ·
  Tera bench-immunity · core draw/search (Lillie's, Dawn, Poké Pad, Ultra Ball, Judge,
  Dudunsparce) · energy accel (Oricorio Excited Turbo, Crispin) · Cursed Blast (Dusknoir
  line is the Dragapult variant's KO engine) · Munkidori Adrena-Brain · Fezandipiti Flip the
  Script · Mega Charizard Y ex Explosion Y.
- **P1 — meaningful:** Night Stretcher · Energy Retrieval · Switch · Hilda · Powerglass ·
  Air Balloon · Crushing Hammer · Unfair Stamp · Meowth ex · Fan Rotom Fan Call · Moltres ·
  Enriching Energy · Cruel Arrow · Munkidori Mind Bend (Confusion).
- **P2 — rarely fires / marginal:** Dunsparce Dig · Charmander Agile · Duskull Come and Get
  You · Budew Itchy Pollen · Dusclops Cursed Blast(5) · Chi-Yu Allure/Ground Melter ·
  Fan Rotom Assault Landing · Shadow Bind.

---

## §5 — Stub / deviation log (keep current; empty = nothing hidden)

**First validation target = load-bearing subset** (R8 review decision). The matchup-critical
cards are made faithful; a small tail is honestly stubbed and listed here. The first number is
reported WITH this list so nothing is hidden. Re-examine each before trusting the number.

**Promoted to FAITHFUL on matchup-impact re-examination (were going to be stubbed):**
- **Budew (Itchy Pollen, Item-lock):** not fringe — a turn-1 Item-lock against two Item-reliant
  decks is real tempo denial. Nearly free once Special Conditions exists (being built). → build it.
- **Team Rocket's Watchtower:** its real text is *"Colorless Pokémon in play (both players) have
  no Abilities"* — that shuts off the Charizard deck's **Dudunsparce (Run Away Draw) draw engine**
  and Fan Rotom, AND as a Stadium it bumps the opponent's Battle Cage (stadium war). Central to
  the matchup. → build it (needs a Colorless-ability-suppression hook; the stadium-bump already works).

**Stubbed for the first validation pass (low matchup impact — justified):**
| Card | # | Why it's safe to stub first |
|------|---|------------------------------|
| Moltres (Fighting Wings) | 1 | 1-of tech attacker; marginal, rarely the line. |
| Dunsparce (Dig) | 3 | Dudunsparce evolution fodder; almost never attacks (coin-flip damage-prevent on a fodder mon). |
| Charmander (Agile) | 3 | Passive free-retreat when no Energy; minor convenience, low swing. |
| Duskull (Come and Get You) | 2 | Niche Duskull-recursion; the line evolves up, rarely recurs. |
| Air Balloon | 1 | Retreat-cost Tool; consistency nicety, low matchup swing. |
| Powerglass | 1 | End-of-turn Energy-from-discard Tool; minor accel. |
| Unfair Stamp | 1 | 1-of ACE SPEC comeback (hand reset after a KO); situational. **Highest-impact stub — revisit first if the number is off.** |

**Agent / policy deviations (not card stubs):**
- **Greedy Stadium policy (v0):** plays any offered Stadium (first one). Establishes Battle Cage /
  bumps opponent Stadiums so the Stadium war isn't inert. *(Fixed the silent-inert bug found in
  R8 review.)*
- **Greedy Trainer policy (v0, §2.1):** generalized so the consistency engine fires — plays
  consistency Items (Poké Pad/Ultra Ball/Night Stretcher/Energy Retrieval) and one Supporter/turn
  (draw when hand low, else search). **Boss's Orders (gust) sits LAST** — greedy can't judge the
  KO a gust sets up, so it under-plays it; **MCTS owns gust timing.** Guarded by `test_agents.py`.
- **Observed (watch, not a blocker):** greedy mirror over-churns → ~16% of games deck-out. Partly
  greedy over-draw, partly the decks can't yet close by prizes (KO-engine effects not built). Expect
  this to drop as Cursed Blast / Munkidori / Explosion Y land; MCTS avoids suicidal draw regardless.
- Several effects keep a greedy v0 target policy (e.g. `place_counters_on_bench` maximize_ko,
  search pick-best, Switch/Run-Away promote-healthiest); a hook for MCTS to own them exists.

---

## §6 — Validation run (the actual point)

- [ ] Both decks pass test B (coverage) with zero `needs-effect`, zero misclassifications.
- [ ] Run MCTS mirror-seat matchup Dragapult vs Charizard X/Y at the standard iteration
      budget; record win rate both seats.
- [ ] Compare to the published Limitless matchup win rate; **target within ~5–8%**.
- [ ] Log result + any divergence hypothesis in REVIEW_LOG. If outside tolerance, the suspect
      list is: the P0 effects, the bench-damage chokepoint, and the MCTS policy hooks left
      greedy (§5) — not the engine core (already validated).

---

## Critical path (one line)

§0 coverage test → §1 data → **2.5 Stadium+bench chokepoint** & **2.9 MEGA/Tera** (P0 fidelity)
→ 2.1–2.4 draw/search/discard/flip → 2.6–2.8 status/KO/tools → 2.10 special energy →
§3 effects in P0→P1→P2 order → §6 matchup compare.
