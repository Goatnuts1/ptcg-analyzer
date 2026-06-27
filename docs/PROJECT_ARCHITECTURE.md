# Project architecture — three projects, one pipeline

As of this PR the work spans **three distinct projects** with a clear dependency
direction. The self-play learning engine is no longer "part of the analyzer" — it is its
own project whose job is to run **background processes that make the app smarter over
time.** This doc records that separation, the boundaries, and the plan to keep them clean.

```
   ┌──────────────────────┐   imports engine internals    ┌────────────────────────┐
   │  ptcg-analyzer        │◄──────────────────────────────│  THE TRAINER ("Brain") │
   │  (deterministic       │   (GameState, legal_actions,  │  src/learn/  → its own  │
   │   engine = rules       │    agents, mcts, determinize) │  project; background    │
   │   oracle + simulator)  │                               │  self-play → models     │
   └──────────┬─────────────┘                               └───────────┬─────────────┘
              │ static data                                             │ trained model
              │ (cards.json, meta_decks.json,                           │ artifact
              │  precomputed offline)                                   │ (versioned, gated)
              ▼                                                         ▼
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │  PTCG Coach  (iOS app, ~/dev/PTCGCoach)                                         │
   │  consumes static data from the engine AND the trained model from the Trainer   │
   └──────────────────────────────────────────────────────────────────────────────┘
```

## The three projects

1. **ptcg-analyzer** — the deterministic engine (rules oracle) + offline simulator/CLI.
   The predecessor and the foundation. Stable, tested, the source of truth for legality,
   outcomes, and the static data the app bundles.
2. **The Trainer / "Brain"** (this PR, `src/learn/`) — background self-play that turns CPU
   time into a stronger policy/value model. Depends on the engine's *internals*. Its output
   is a **versioned, gated model artifact**, not a running game.
3. **PTCG Coach** (`~/dev/PTCGCoach`, separate, not yet under git) — the iOS app. Consumes
   the engine's static data today and the Trainer's model tomorrow (Phase 5).

**Dependency rule:** engine ← trainer → app, and engine → app (data). The engine never
depends on the trainer or the app; the app never depends on the trainer's *internals*, only
on a published model artifact.

## Why the Trainer lives in the analyzer repo *for now*

It imports engine internals that are **not a stable public API** (`GameState`, `legal_actions`,
`agents`, `mcts`, `determinize`). Splitting it into its own repo today would mean either
vendoring those internals or freezing an API before we know its shape — premature. So:

- **Now:** the Trainer lives in `ptcg-analyzer/src/learn/` as a clearly-bounded subsystem, so
  it can co-evolve with the engine internals it reads. Its own docs, tests, and roadmap.
- **Extraction trigger (target Phase 3–4):** once the engine exposes a *stable, versioned*
  "policy-environment" API (encode state, list legal actions, step, terminal value), the
  Trainer extracts cleanly into its own repo that depends on `ptcg-analyzer` as a package.
  Nothing in `src/learn/` reaches into engine internals except through that future API — keep
  it that way so the cut is mechanical when the time comes.

## The background-process model ("smarter over time")

The Trainer is meant to run **unattended in the background** (overnight on the M5; later a
fan-cooled box / cloud — see LEARNING_ENGINE_PLAN.md §7a). The continuous loop:

1. **Self-play workers** (8) generate games with the current best model + ISMCTS; the engine
   enforces the rules. → records into the rolling buffer (hot internal SSD).
2. **Flush** sealed shards to the external T7 archive (bulk; USB-tolerant).
3. **Trainer** updates a candidate model from the buffer.
4. **Promotion gate** — adopt the candidate as "best" only if it (a) beats current best in a
   mirrored arena by a margin, (b) the effect/rules test suite is green, (c) determinism holds.
5. Repeat. Operationally this is a scheduled/daemonized job (cron or a supervisor), with
   checkpoints, so it survives reboots and accumulates strength across days.

## The model-handoff interface to the app

This is the contract that makes the app smarter without coupling it to the Trainer:

- The Trainer publishes a **model artifact** = `{weights, FEATURE_VERSION, ACTION_VERSION,
  arena-strength, git-sha}`. Versioned; immutable once published.
- **Phase 5 delivery options** (decide later): (a) **distill** the model into a small on-device
  policy bundled with the app (replaces the current heuristic prize-race estimator in
  `~/dev/PTCGCoach/PTCGCoach/Models/DeckSimulator.swift`); or (b) a thin **inference endpoint**
  the app calls. Either way the app pins a model version and the encoder/action versions must
  match — that's why those are stamped on every record and artifact today.

## Naming

Working name **"the Trainer"** / **"Brain"**. When extracted, a repo name like
`ptcg-trainer` or `ptcg-coach-brain` fits the role: the background brain that trains on
simulated games to make PTCG Coach play smarter. (Final name TBD by the owner.)
