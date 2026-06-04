# Policy Milestone — Piece 3: Search-Owned Target Policies

**From:** design/algorithm side → **integrate:** CC against current `main` (1396741).
**Built against:** the codebase as of the corrected Budew framing (commit 1396741)
and the validated piece-2b engine (R17).

## Why this piece (and not Budew)

The Budew investigation that closed piece 2b proved Grok's original "promote-to-disrupt"
hypothesis wrong. Itchy Pollen is free-cost, the promotion happens, the attack is
legally available — and the agent skips it for a defensible reason: under the current
eval, `retreat → develop → draw → continue the turn` produces a higher-valued
position than `Itchy Pollen → end turn`. 2-ply negamax confirms it. That's a play
style, not a bug. We accept Budew's 0/120 (option D in the joint call), record the
PIMC-with-hidden-hand limit as a known constraint, and pivot piece 3 to where the
actual band lever lives: the v0 target choices that fire 30–90 times per 120 games.

Three v0 helpers in `effects.py` make per-effect target choices that the original
piece-3 brief flagged as "search-owned choices replacing greedy v0 defaults":

| helper (effects.py) | current v0 behavior | what's wrong |
|---|---|---|
| `_boss_orders` (line 924) | `min(opp.bench, key=remaining_hp)` | drags the *low-HP* mon — ignores whether our Active can actually KO it, and ignores weakness flipping the right target |
| `_cursed_blast` call site (line 545) delegating to `_pick_ko_target` (line 533) | `max(koable, key=(prizes, -hp))` | picks the highest-prize KO target but ignores **engine value** (Dudunsparce = the draw engine; Fan Rotom = the search engine). **Scope:** the hook must live in `_cursed_blast`, not in the shared `_pick_ko_target` helper — see Sanity caveats below. |
| `place_counters_on_bench(policy="maximize_ko")` (line 63, called by `_phantom_dive`) | pile-drives the lowest-HP bencher | wastes counters if no single KO is available — should set up multi-target next-turn KO math |

These fire constantly (gust 86–91/120, Cursed Blast 34/120, Phantom Dive 29–36/120),
so even modest improvements compound across the matchup. Importantly, they are
**localized, well-defined functions of board state** — the opposite of Budew's
"value of one turn of lock against the hidden hand" eval ambiguity. Piece 3 is
mechanistic targeting; piece 2c (full ISMCTS with mid-tree re-determinization) and
hidden-hand-aware eval are separate later pieces, deliberately deferred.

## The success criterion (band + mechanism, same as 2b)

- **Win % :** still inside (or moving toward) the Dragapult-favored 68–82% band,
  reported alongside the line-fire table.
- **Mechanism :** for each policy, the regression must show the *targeting changed*,
  not just the headline. Concretely, three new metrics in the matchup runner:
  - `gust → KO secured`  (count of games where Boss's Orders dragged up a mon the active then KO'd this turn)
  - `Cursed Blast → engine KO`  (count of games where Cursed Blast KO'd Dudunsparce / Fan Rotom / a TRW or Battle Cage holder)
  - `Phantom Dive → multi-setup`  (count of games where spread left ≥2 benched mons in 1-attack-from-KO range)
- **Budew = 0/120 expected** (accepted under D, not a regression).

A win % point gain without mechanism counts moving is *not* validation, same as
piece 2b. If a policy fires more but doesn't move its named metric, surface that
and stop.

## The three correctness requirements (per policy)

**Each is a function of fully public board facts** — none read the opponent's
hidden hand, deck, or prizes-contents, so PIMC integrity is preserved. None
re-tune eval weights.

**1. gust_target (Boss's Orders / `_boss_orders`)** — must call the same
`_apply_weakness_resistance` the engine uses when deciding whether the active's
best-affordable attack would KO a candidate. *Do not duplicate the damage math*
(every weakness/resistance/Tera nuance there is one place a divergence could
silently inflate or deflate gust value). The policy reuses the helper.

Priority order (each tier exhausted before the next):
- (a) a target the active can KO this turn (apply weakness),
- (b) tie-break: most prizes given, then highest energy attached (denies a turn of charge-up),
- (c) fall back to v0's lowest-HP if no KO is available (no behavior change in the
  no-KO case — never *worse* than v0 by construction).

**2. cursed_blast_target (Dusclops/Dusknoir / `_pick_ko_target`)** — Cursed Blast
is a self-KO; we give up a prize either way, so the target choice is everything.
Among KO-able candidates:
- (a) most prizes given (unchanged from v0 — correct),
- (b) **NEW:** tie-break on engine value, scoring board-fact terms only:
    - is this mon a non-replaceable draw/search engine? (an *evolved* draw mon
      like Dudunsparce — losing it forces re-evolving from a Basic, multi-turn
      setback) → +3
    - is this mon currently the Tool holder for Battle Cage? → +2 (denies spread-denial)
    - is this mon currently the Stadium-anchor or has TRW-relevant active ability? → +1
- (c) fall back to lowest-HP (v0).

Operationalizing "engine value": board-only. We don't ask "is this in their deck"
— we ask "is this mon, right now, the in-play engine piece" by literal type:
specific card-name allowlist + presence-of-attached-tool checks. Faithful and
testable; not heuristic-shaped. The allowlist is short (the meta's engine pieces),
maintained as a constant near the policy, sourced from the tournament lists. Any
expansion to a new archetype adds names there, with a test.

**3. phantom_dive_spread (`place_counters_on_bench`)** — currently pile-drives.
Replace with: distribute the 6 counters to **maximize benched-mons-in-1HKO-range
of the active's expected next-turn attack**. Concretely:
- For each benched candidate, compute `dmg_to_KO = remaining_hp` (after current
  damage), apply weakness via the engine helper if applicable to the *attacker's
  expected next-turn attack* (we already know what attack we just used / will
  use again; for Phantom Dive's Dragapult, the attacker is itself).
- Solve a small knapsack: assign counters in 1-counter (10-dmg) increments to
  the benched mon with the smallest `dmg_to_KO - already_assigned` while keeping
  every assignee's running total < dmg_to_KO (don't over-fill — wasted).
- If no distribution sets up ≥2 next-turn KOs (e.g., 1 small bencher and one
  huge one), fall back to v0's pile-on-lowest-HP. Never worse than v0 by construction.

The policy is *intentionally* one-turn-of-lookahead, not full search — that's
piece 2c's job. The point here is to stop pile-driving when distribution
secures more KO math.

## Where the policies plug in (clean hook)

The policies are owned by the **agent**, not the engine, per the architecture
rules. Minimal API surface:

```python
# new file: src/engine/policies.py
class TargetingPolicy:
    """Search-owned target choices. Pure functions of public board state.
    The engine's v0 helpers consult `state.targeting_policy` if set, else fall back."""
    def gust_target(self, state, me, opp, attacker) -> InPlayPokemon: ...
    def cursed_blast_target(self, state, me, opp, dmg) -> InPlayPokemon: ...
    def phantom_dive_spread(self, state, me, opp, counters) -> list[tuple[InPlayPokemon, int]]: ...

class V0Policy(TargetingPolicy):
    """The current behavior — kept verbatim so no-policy path is unchanged."""
```

`GameState` gets one optional attribute `targeting_policy: TargetingPolicy | None`
(default `None`). The three affected helpers in `effects.py` become:

```python
def _boss_orders(ctx):
    pol = getattr(ctx.state, "targeting_policy", None)
    victim = pol.gust_target(...) if pol else min(ctx.opp.bench, key=lambda m: m.remaining_hp)
    ...
```

`MCTSAgent` sets `state.targeting_policy = SearchPolicy()` at the top of `choose`.
**As-built lifecycle correction (CC integration):** the doc originally said
"clears it on return [from `choose`]" — but in this engine the chosen action is
applied to the real state by `play_one_turn` *after* `choose` returns, and the
target is picked *inside* the effect at apply-time (not encoded in the Action).
Clearing on return would make the actually-played effect run under v0. Conversely,
leaving it attached would leak the policy into the opponent's turn (effects share
one `GameState`), silently changing Greedy/Random. **Resolution:** attach at the
top of `choose` (no clear-on-return), and clear at the turn boundary in
`start_turn` — alongside the other per-turn resets. This bounds the policy to the
acting player's turn: it shapes search lines (`clone()` propagates it), the real
played action, and is gone before the opponent acts. `RandomAgent`/`GreedyAgent`
never attach, so they stay v0. **No `evaluation.py` / eval-weight diff.**

## The five targeted edits (full files in the package)

1. **`src/engine/policies.py`** *(new)* — `TargetingPolicy`, `V0Policy`,
   `SearchPolicy` (the three new policies). Pure functions of state; no eval imports.
2. **`src/engine/effects.py`** — three call sites changed from inline targeting to
   `state.targeting_policy or v0_default`. ≤15 lines edited; v0 behavior preserved
   when no policy is attached (regression-safe for greedy/random agents).
3. **`src/engine/state.py`** — one optional attribute on `GameState`:
   `targeting_policy: Optional[object] = None`.
4. **`src/engine/mcts.py`** — `MCTSAgent.choose` attaches a shared `SearchPolicy()`
   at entry (cleared at the turn boundary by `start_turn`, not on return — see the
   as-built correction above).
   **`src/engine/game.py`** — `start_turn` clears `state.targeting_policy` (one
   line, the per-turn-scratch reset that makes the policy leak-free by construction).
5. **`src/engine/matchup.py`** — three new `LINE_MARKERS` for the mechanism
   metrics (KO-after-gust, engine-KO-on-Cursed-Blast, multi-setup spread). Each
   is a log substring the engine already emits (or trivially can — small `emit`
   addition in the three helpers).

The two correctness requirements (PIMC-safe, no-eval-tuning) hold by construction
because the policies are public-info pure functions and `evaluation.py` is not touched.

## Gate tests (RED on main, GREEN after policy land)

Three tests, each pinning the policy decision in a hand-crafted scenario with
synthetic Cards (no full-game simulation — these are pure-targeting unit tests,
fast and unambiguous). Each is **RED on current main** (calls the v0 helper which
gives the wrong answer) and goes **GREEN after `src/engine/policies.py` lands and
the call site reads `state.targeting_policy`**.

- **`tests/test_piece3_gust_target.py`** — weakness flips the right target. Active
  is a Lightning attacker that deals 50 base. Bench A = 80 HP with Lightning
  weakness ×2 (effective KO at 100 dmg). Bench B = 60 HP, no weakness, takes 50
  (no KO). v0 picks B (lower HP, no KO secured); correct picks A (the KO via
  weakness). The test passes its `_apply_weakness_resistance` through the engine
  helper to confirm the math matches — not a duplicate.
- **`tests/test_piece3_cursed_blast_target.py`** — engine-disable beats raw HP.
  Two KO-able benched targets, same prizes given. One is an evolved draw engine
  (named in the engine-piece allowlist); the other is a vanilla 1-prize basic of
  lower HP. v0 picks the basic (lowest HP tiebreaker); correct picks the engine.
- **`tests/test_piece3_phantom_dive_spread.py`** — distribute over pile-drive.
  Bench has three mons whose `remaining_hp` is {30, 35, 80}. 6 counters (60 dmg).
  v0 pile-drives: 30→KO with 3 counters, then 30 onto the 35 (1 short of KO),
  leaving 80 untouched. 1 KO + 1 damaged. Correct: 3 on the 30 (KO), 4 on the 35
  (KO), 0 on the 80 = **2 KOs**. The test asserts the correct distribution count
  and the count of KO'd benched targets.

Each test runs in milliseconds, no `--fast` flag needed. They will be added to
`tests/test_decklist_coverage.py`'s manifest of known suites.

## Regression protocol (after policy land)

Same shape as piece 2b's:

1. **Gate tests green** (the three above) — must precede any matchup re-run.
2. **`python3 -m src.engine.matchup --agent mcts-eval --games 60 --plies 2 --iters 100 --seed 0`** — single seed (replaces 2b's two-seed chunking now that we've validated the engine is stable; if the run truly exceeds the shell cap, chunk and document).
3. Report: win % + the existing line-fire table + the three new mechanism metrics
   (KO-after-gust, engine-KO-on-Cursed-Blast, multi-setup spread). Compare against
   the piece-2b numbers (60.8% / 91 gust / 34 Cursed Blast / 29 Phantom Dive / 0 Budew).
4. **Budew still 0/120 is expected and accepted under D.** Note it explicitly in the report.
5. No REVIEW_LOG verdict written until user/Grok ratifies.

## Out of scope (deliberately)

- **Mid-tree re-determinization (full ISMCTS)** — piece 2c. Not required to move
  the named target metrics, which are decided at the moment of effect resolution
  on the *current* board.
- **Hidden-hand-aware eval (the Budew/item-lock limitation)** — known limit;
  separate piece.
- **Promote-to-disrupt at setup** — not what the Budew gap is. Don't add it.
- **Eval re-tuning** — `evaluation.py` is not touched.

## Sanity caveats CC should watch on integration

- The `cursed_blast_target` engine-piece allowlist is **explicit card names** (e.g.,
  `{"Dudunsparce", "Fan Rotom"}` for the Charizard list's draw/search engine).
  Adding a new archetype later means adding to the list, with a test pinning the
  pick. Don't make it heuristic ("has a draw ability") — that's a different,
  larger refactor and would silently expand.
- `place_counters_on_bench` is also called by *other* effects than Phantom Dive
  (grep `policy="maximize_ko"` / default arg). Verify the policy-aware path is
  opted into ONLY by Phantom Dive's call site, and the others keep v0 behavior
  unless we explicitly enable them.
- `MCTSAgent.choose` is called many times per game; setting/clearing
  `state.targeting_policy` must be exception-safe (try/finally). Otherwise a
  raised exception in a rollout could leak the policy into greedy reference
  agents and silently change their behavior between runs.
- The three new `LINE_MARKERS` must use substrings the engine *actually emits* —
  add the `emit` lines first, run the matchup once, confirm the log strings exist
  before declaring the new metrics wired.
- **The `_cursed_blast` policy hook lives at the `_cursed_blast` call site
  (effects.py:545), NOT inside `_pick_ko_target`.** `_pick_ko_target` is shared
  by `_cruel_arrow` (line 582), the 280-dmg discard attack (line 592), and
  `_adrena_brain` (line 563). Baking engine-value preference into the shared
  helper silently re-targets those three unrelated attacks — the same
  silent-expansion failure the caveat above flags for `place_counters_on_bench`.
  Keep `_pick_ko_target` v0; `_cursed_blast` consults `state.targeting_policy`
  itself and falls back to `_pick_ko_target` when the policy is unset or returns
  `None`. (`can_play` predicates at effects.py:806/808 only check `is not None`
  on `_pick_ko_target`'s result, so they're tie-break-agnostic and safe.)
- **Gate tests use a self-contained stub policy** (`_StubGustPolicy` /
  `_StubCursedBlastPolicy` / `_StubPhantomDivePolicy` inline in each test) — they
  do NOT import `SearchPolicy`, so they don't depend on `src/engine/policies.py`
  existing. Each test attaches its stub via `state.targeting_policy = stub`, then
  asserts the stub was consulted AND its pick honored. RED on current main
  because the three call sites don't read `state.targeting_policy` yet; GREEN
  after integration. Policy *correctness* tests are a separate follow-up CC adds
  when implementing `SearchPolicy` — the gates intentionally test the seam, not
  the policy's content.

Good handoff point.
