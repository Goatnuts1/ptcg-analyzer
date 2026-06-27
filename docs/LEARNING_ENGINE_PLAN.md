# Continuous Self-Play Learning Engine — Design & Operational Plan

> Goal: an AI computing engine that gets stronger over time by simulating as many games
> as possible, where **every game played is new training data** and **the rules of the
> game are never violated**. This document specifies the architecture, the data and
> compute budget (with measured numbers from this repo), and the phased operational route.

---

## 1. The core idea (and why rules can never break)

This project already has the one non-negotiable rule: **the learner is never in the game
loop.** A deterministic engine (`src/engine/`) plays the games on CPU, generates the legal
moves, and computes every outcome. We keep that rule and add a *learned policy/value
network* in exactly the seat the hand-written `GreedyAgent`/`EvalAgent` occupy today.

```
            ┌─────────────────────────────────────────────────────────┐
            │  DETERMINISTIC ENGINE  (src/engine/) — the RULES ORACLE   │
            │  legal_actions(state) ·  apply(action) ·  outcome/KO/prize│
            └───────────────▲───────────────────────────┬─────────────┘
                            │ legal actions only         │ next state, reward
              masked prior  │                            ▼
            ┌───────────────┴───────────┐      ┌───────────────────────┐
            │ POLICY/VALUE NET (learned) │      │  ISMCTS / PUCT search │
            │ p(a | legal) ,  v(state)   │◄────►│ (uses determinize())  │
            └───────────────────────────┘      └───────────────────────┘
```

**Rule adherence is structural, not learned.** The net only emits a probability *prior
over the legal actions the engine already produced* (a masked softmax) and a scalar value
estimate. It can never select an illegal move, mis-resolve an effect, or mis-award a prize
— the engine does all of that. The worst a bad net can do is *play badly*, never *play
illegally*. This is the same guarantee the repo enforces today (`CLAUDE.md`: "the LLM is
never in the game loop"), extended from heuristics to a trained model.

Two existing invariants make this safe and trainable:
- **Determinism is a tested invariant** (`tests/test_determinism.py`): same seed → byte-identical
  game, in- and cross-process. Every training sample is therefore reproducible and auditable;
  any nondeterminism would silently poison the dataset, so the test gate protects the data.
- **Effects ship with tests vs card text** (`effects.py` + `tests/`). New cards enter
  self-play **only after** their effect script passes its card-text test — so the rules the
  agent learns against are always the printed rules.

---

## 2. What already exists (Phase 0 — done)

Measured/inspected in this repo today:

| Capability | Where | Status |
|---|---|---|
| Full legal games, CPU-only, zero tokens | `src/engine/run.py`, `game.py` | ✅ |
| `legal_actions(state)` — compact typed `Action` (kind + ≤3 indices) | `game.py:142` | ✅ |
| `GameState.clone()` / `determinize()` (PIMC for hidden info) | `state.py`, `mcts.py:64` | ✅ |
| MCTS (determinized UCT, eval-leaf, multi-turn negamax) | `mcts.py` | ✅ |
| Deterministic, reproducible games (tested) | `tests/test_determinism.py` | ✅ |
| 1,276-card pool; 13 decks; effects tested vs card text | `data/`, `decks.py`, `effects.py` | ✅ |

**Throughput on this machine (10 cores, 24 GB, Apple Silicon), measured:**
- Greedy: **1,000 games in 1.23 s ≈ 813 games/s/process** → ~6,500 games/s with 8 workers.
- MCTS: **60 games in 37 s ≈ 1.6 games/s/process** → ~13 games/s with 8 workers
  ≈ **~1.1 million MCTS-strength self-play games per day on this single Mac.**

The open frontier the validation work identified (`docs/VALIDATION_RESULT.md`) is **agent
strength**: greedy and 1-ply MCTS can't express multi-turn spread+disruption plans, so the
sim reads matchups too evenly. A learned policy/value net is precisely the lever that closes
that gap — this plan is the path to it.

---

## 3. Representation (the only genuinely new engine code)

The state is small and fully structured, so encoding is cheap and the net can be small.

**State encoder** (frozen feature spec → a vector per decision point):
- Card identity → an **embedding table over the 1,276-card vocabulary** (IDs, not one-hots).
- Per-player zones: `active` + up to 5 `bench` Pokémon (HP remaining, attached energy by
  type, tool, status), `hand` (≤ ~10), counts for `deck`/`discard`/`prizes`.
- Turn flags already in `PlayerState`: `energy_attached_this_turn`, `supporter_played_this_turn`,
  `stadium_played_this_turn`, `cant_retreat`, `cant_play_items`, `turns_taken`, KO flags.
- Perspective: encode from the acting player's POV; hidden zones (opp hand, both decks,
  face-down prizes) are **not** revealed — they are sampled by `determinize()` inside search.

**Action head**: `Action` has only `kind ∈ {pass, play_basic, attach_energy, evolve,
play_stadium, play_trainer, use_ability, attach_tool, retreat, attack}` plus small
`hand_index/target_index/attack_index`. That's a **fixed, few-hundred-logit action template
space**; the engine's `legal_actions()` provides the mask each ply. No giant action space.

**Net**: card-embedding + small board/seq encoder → (policy logits over action templates,
scalar value in [-1, 1]). A few-million-parameter net is ample given the compact state; it
trains and runs fast on Apple-Silicon MPS or any small GPU.

---

## 4. How much data — the budget

### 4.1 Per-game data volume
A game runs ~30 turns (`saved_games/demo_battle.json`: 30 turns / 168 log lines). Decision
points ≈ **40–60 per game**. Each training record = encoded state (card IDs + small int
features) + MCTS **visit-count policy target** over legal actions + final game value.

- Raw: ~1.5–2 KB/record × ~50 records ≈ **~75–100 KB/game**.
- Compressed (IDs + sparse policy): **~30–60 KB/game**.

### 4.2 Games to reach each capability tier
Imperfect-information card games of this size reach strong play in roughly 10⁵–10⁷ self-play
games (cf. AlphaZero-style work scaled down from Go to card/board games). Concrete targets,
with wall-clock at the **measured** throughput above:

| Tier | Games | Data (rolling window) | Wall-clock — 1 Mac | Purpose |
|---|---:|---:|---|---|
| **Bootstrap** (greedy/MCTS games, no net) | 1 × 10⁶ | ~50 GB | **~2.5 min** (greedy 6.5k/s) | warm-start the value net; calibrate |
| **Iter-1 policy** (net-guided self-play) | 1 × 10⁵ | ~10 GB | **~2 hours** | first net that plans > 1 turn |
| **Competent** | 1 × 10⁶ | ~50–100 GB window | **~21 hours** | beats greedy/1-ply MCTS clearly |
| **Strong / deck-general** | 1 × 10⁷ | ~100 GB window (full archive ~1 TB) | **~9 days** (1 Mac) · **~1 day** (10× cloud cores) | robust across the deck space |
| **Continuous** | ∞ cumulative | **bounded** (see below) | ongoing | "smarter over time" |

Headline: **a single 10-core Mac produces ~1.1 M MCTS-strength self-play games/day**, so the
*Competent* tier is roughly an overnight run and *Strong* is ~a week (or ~a day on modest
cloud fan-out). Greedy bootstrap data is effectively free (millions of games in minutes).

### 4.3 Storage does **not** grow without bound
Continuous learning ≠ infinite disk. Use a **rolling replay window** (AlphaZero keeps a
moving buffer of the most recent ~10⁵–10⁶ positions). Steady-state storage is therefore
**bounded at tens of GB** regardless of cumulative games, plus small periodic net checkpoints
(a few MB each). If you also want a permanent, reproducible archive of every game, that's
~1 TB per 10⁷ games on cheap object storage — optional, since determinism means a game is
fully recreatable from `(deck1, deck2, seed, net-checkpoint)` — i.e. **~50 bytes can stand in
for a whole game** for audit/replay.

---

## 5. The continuous learning loop (operational route)

```
   ┌──► self-play workers ──► (state, policy, value) records ──► rolling replay buffer ──┐
   │      (best net + ISMCTS,                                                            │
   │       engine enforces rules)                                                        ▼
   │                                                                            trainer (MPS/GPU)
   │                                                                          updates candidate net
   │                                                                                     │
   └──────────── promote if candidate passes the GATE ◄──────────── arena + rules CI ◄───┘
```

**The promotion gate (this is what keeps it honest and rule-true):** a new candidate net is
adopted as "best" only if it **(a)** beats the current best in a mirrored arena by a margin
(e.g. ≥ 55% over K games, both seats, multiple decks), **and (b)** the full effect/rules test
suite is green (no card resolves against the printed text wrongly), **and (c)** the determinism
test still passes. Fail any → discard the candidate. This makes "getting smarter" monotone and
makes a rules regression un-promotable by construction.

**Each deck/game adds data** because every self-play game is written to the buffer, and the
buffer is a moving window — so the agent continuously refits to recent play, new decks, and
(after their effect tests pass) new cards. Rotation/new sets are handled the existing way:
`STANDARD_LEGAL_MARKS` + a re-fetch + effect tests, *then* the cards enter self-play.

---

## 6. Phased route forward

- **Phase 1 — Data pipeline.** Freeze the state-encoder feature spec; add a self-play harness
  that writes `(state, π, z)` records + a sharded, compressed rolling buffer with schema +
  versioning. Seed it with cheap greedy/MCTS games (minutes of compute). *Deliverable:* a
  reproducible dataset and a loader.
- **Phase 2 — Net + bootstrap.** Implement the card-embedding policy/value net; train on
  bootstrap data; verify value calibration (predicted vs actual win) and that the policy head
  imitates MCTS visit counts. *Deliverable:* a net that matches greedy strength from data alone.
- **Phase 3 — Net-guided ISMCTS self-play + gate.** Wire the net as PUCT priors/leaf-value in
  `mcts.py` (reuse `determinize()`); run the self-play→train→arena→promote loop in overnight
  cycles on the Mac. *Deliverable:* a net that beats greedy/1-ply MCTS and plans multi-turn.
- **Phase 4 — Scale + continuous schedule.** Fan self-play out to cloud CPU workers with a
  batched GPU inference/trainer; widen the deck pool; run on a schedule (cron / the existing
  bridge). Periodically re-run validation vs published Limitless matchups to track real-world
  fidelity. *Deliverable:* a continuously improving best-net with tracked strength.
- **Phase 5 — Ship to the app.** Export the trained net as the "strong sim" for **PTCG Coach**
  (`~/dev/PTCGCoach`): either a distilled lightweight policy embedded on-device (replacing the
  current heuristic prize-race estimator) or a thin inference endpoint the app calls.

---

## 7. Risks & guardrails

| Risk | Guardrail |
|---|---|
| Net causes an illegal/mis-scored move | Impossible by design — net only re-ranks `legal_actions()`; engine resolves outcomes. |
| Rules regression sneaks in | Promotion gate requires the full effect-vs-card-text suite green. |
| Nondeterminism poisons data | `test_determinism.py` stays a hard gate; records carry seed + net checkpoint. |
| Hidden-info leakage (training on perfect info) | Encode from acting-player POV; sample hidden zones via `determinize()` (ISMCTS), never reveal. |
| Overfit to a narrow deck set | Rotate decks, mirror seats, sample diverse archetypes; the meta is the curriculum. |
| Self-play MCTS is the compute bottleneck | Use the net to cut sims/move; batch inference; parallelize workers; greedy data for cheap warm-up. |

---

## 7a. Hardware & storage layout (this rig)

Measured on the actual machine + the attached drive:

- **Compute: Apple M5, 10 cores, 24 GB (Mac17,4 — MacBook Air, *fanless*).** The throughput
  figures in §2/§4 are **burst** numbers on this M5. Because the Air is passively cooled, a
  multi-day all-core self-play run **thermal-throttles** — sustained rate settles below burst.
  - Use ~**8 workers, not 10** (leave headroom; an Air often sustains *more* aggregate work
    when it isn't pinned to the throttle point). Keep it **plugged in**, elevated, cool room.
  - The Air is ideal for the overnight **10⁵–10⁶** tiers. For the **10⁷** marathon or 24/7
    continuous self-play, a fan-cooled Mac (Mini/Studio) or cloud CPU fan-out is better suited.
- **RAM 24 GB:** size the **hot rolling replay buffer to ~8–12 GB** so it stays in page cache —
  training then reads minibatches from RAM, not disk. The net is small; leave room for OS + MPS.
- **Attached SSD: Samsung T7, 500 GB, APFS, ~444 GB free (`/Volumes/OLLAMASSD`).** APFS is the
  right filesystem (atomic temp+rename, no exFAT small-file/rename hazards). **But it is currently
  on a ~40 MB/s link (USB 2.0), not the T7's ~1,000 MB/s** — fix with a USB-C 3.2 Gen2 cable
  straight into the Air's port (not through a hub) for a ~25× free speedup.

**Hot/cold split — the recommended layout:**

| Data | Where | Why |
|---|---|---|
| **Cold archive**: sealed self-play game shards (compressed), checkpoint history | **External T7** `/Volumes/OLLAMASSD/ptcg/archive/` | Bulk lives here; keeps the internal drive clean. Even at 40 MB/s the link has ~60× headroom vs the ~0.65 MB/s *average* data rate (≈55 GB/day at 1.1 M games × ~50 KB). |
| **Hot rolling replay buffer** + active net checkpoint | **Internal SSD** (`~/dev/ptcg-analyzer/.selfplay/`) or RAM | Training does random minibatch reads; internal is ~150× faster and the buffer is small enough to cache. **Never** put the live buffer on a removable USB drive. |

Disk throughput is **not** the bottleneck for *writing* training data (data rate ≪ link speed);
CPU/thermals are. So the SSD is well-suited for bulk **as-is** — just keep the live buffer
internal and flush sealed shards out to the T7 with atomic writes (the USB drive can disconnect,
so the trainer must tolerate the archive being briefly unavailable).

## 8. Bottom line

- **Feasible now, on one machine:** ~1.1 M strong self-play games/day on this Mac → a
  *competent* multi-turn agent in ~an overnight run, *strong* in ~a week (≈ a day on modest
  cloud fan-out). Greedy bootstrap data is essentially free.
- **Data required:** ~10⁵ games for a first competent net, ~10⁶ for clearly-beats-heuristics,
  ~10⁷ for deck-space-general — at ~30–100 KB/game, with a **bounded rolling buffer** so disk
  stays at tens of GB no matter how many cumulative games are played.
- **Rules are guaranteed forever** because the deterministic engine — already tested against
  printed card text and for determinism — stays the sole authority on legality and outcomes;
  the learner only chooses among moves the engine has already certified legal, and is only
  promoted when the rules tests stay green.
