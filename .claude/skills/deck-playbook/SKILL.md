---
name: deck-playbook
description: Take a built Pokémon TCG decklist from the user (TCG Live paste, card list, or an existing DECKS entry), simulate it in ptcg-analyzer against a reference gauntlet, and produce a rigorous play-by-play strategy PDF matching the No Vacancy playbook's standard — full decklist, phase-by-phase strategy grounded in real card text and real sim behavior, a bad-draw recovery section, a matchup grade table, and honest greedy+MCTS win-rate numbers. Use whenever the user hands over a deck and asks for a playbook, strategy guide, or PDF "with the rigor of the no-vacancy pdf".
---

# Deck → simulated play-by-play PDF

This codifies the exact pipeline used to build the No Vacancy playbook, so
future decks get the same rigor without re-deriving the design system or
re-discovering the print bugs from scratch. Follow every step — the value of
this skill is that it does NOT skip the sim or the live-fire verification and
does NOT ship a decorative page with invented strategy.

## 0. Inputs this accepts

- A TCG Live export paste (qty + name lines, set codes like `MEG 50`)
- A plain card list with counts
- The name of an existing entry in `DECKS` (`python3 cli.py --list`)

If the user attaches a screenshot of a decklist instead of pasting text,
transcribe it card-by-card before proceeding — don't guess counts.

## 1. Import and validate legality

Fastest path — the local web UI now does steps 1-4 interactively:
`python3 cli.py --serve`, open http://127.0.0.1:8000, click **Import a deck**,
paste the list. It matches every card, validates legality, runs the same
gap-check heuristic as step 2 below, and offers a one-click "run greedy" /
"run MCTS" form against a reference gauntlet — with an explainer of why the
two numbers can disagree baked into the results page. Use its output directly
instead of re-running the CLI commands below by hand when it's available.

CLI equivalent (same underlying code, useful for scripting or when the UI
isn't running):

```
cd ~/dev/ptcg-analyzer
python3 cli.py --import-deck --name <deck_name> <<'EOF'
<paste the decklist here>
EOF
```

This matches names against `data/standard_pool.json` (accent/case-insensitive,
energy normalized), reports matched/missing cards, and checks legality via
`src/engine/legality.py`. **Stop and report back to the user** if:
- Any card doesn't resolve — don't silently drop it or guess a substitute.
- Any card is illegal for the current Standard rotation (check the mark
  against `STANDARD_LEGAL_MARKS` in `legality.py`) — flag it, don't just
  proceed with an illegal decklist.
- The deck isn't exactly 60 cards, or breaks the ≤4-copy / ≤1-ACE-SPEC rules.

## 2. Gap-check card implementation

The web UI's import report runs this automatically. To run it standalone:

```python
from src.engine.cards import CardDB
from src.analysis.gap_check import check_deck_implementation
db = CardDB.from_pool("data/standard_pool.json")
check_deck_implementation(recipe, db)   # recipe = [(name, qty), ...]
```

This is a heuristic (see the module docstring) — it flags any Pokémon
ability/attack with non-empty effect text that isn't in `ABILITY_EFFECTS` /
`PASSIVE_ABILITIES` / `ATTACK_EFFECTS`, and any Trainer not in
`TRAINER_EFFECTS`. A flagged item might already be covered by a generic engine
fallback; an unflagged item could still be subtly wrong (that's what
`tests/test_effects.py`-style tests are for). If a card appears flagged and
its effect is more than "deals printed damage with no rider," it needs
implementing before the sim numbers mean anything. Two paths depending on
scope:

- **1-3 small cards**: implement directly. Look up the card's EXACT text on
  Bulbapedia (bulbagarden.net) via WebFetch/WebSearch — never trust memory,
  and never trust `data/standard_pool.json`'s text field as authoritative,
  it's the legality/name-matching source only. Follow the conventions in
  `CLAUDE.md`: randomness must use `ctx.rng`; in `play_trainer` the card is
  popped from hand before the effect runs; damage/counter chokepoints are
  `apply_attack_damage` / `place_counters` in `effects.py`. Write unit tests
  asserting the exact quoted card text, including negative cases. Then run
  the full suite (`for f in tests/test_*.py; do python3 "$f"; done` — this
  repo's tests are standalone scripts, not pytest-collectible) and confirm
  0 failures beyond any pre-existing, unrelated environment gaps.

- **4+ cards or anything with a passive ability / dynamic cost / new game
  mechanic**: use the Workflow tool with a recon → implement → verify → fix
  → livefire pipeline (this is exactly how Crustle/Milotic ex/Cornerstone
  Ogerpon ex/Bloodmoon Ursaluna ex and four trainers got built). Key
  non-negotiables to bake into the agent prompts:
  - Bulbapedia for card text, not the pool.
  - Explicit `model:` on every `agent()` call (sonnet default, opus for the
    implement/fix stages) — never let subagents inherit the session model.
  - A dedicated livefire agent that independently re-verifies the prior
    agent's claims by actually running seeded games and grepping emitted
    log lines for each new effect — do not accept "implemented" as
    "exercised." This is how the Budew `can_pay_cost` "Free"-cost bug (a
    real engine bug, not a card-script bug) got caught last time: a
    zero-cost attack was silently unplayable because the cost check treated
    the pool's `"Free"` sentinel as a real energy type.
  - After the workflow returns, actually read its full result (the
    `<output-file>` JSON, not just the truncated notification text) before
    trusting "all green."

## 3. Register and smoke-test

Two options — a deck does NOT need a permanent `DECKS` entry just to be
simulated:

- **One-off / exploratory**: use `cli.run_recipe(recipe, opponent, ...)`
  directly (or the web UI, which already calls it) — it takes a raw
  `[(name, qty), ...]` recipe for side A against any registered opponent by
  name, with no `decks.py` edit required. This is what the import UI's "run"
  buttons do under the hood. Verified byte-identical to `cli.run()` for the
  same recipe/seed/agent in `tests/test_run_recipe.py`.
- **Permanent / reusable** (e.g. it's becoming a named reference deck like
  `no_vacancy`/`innkeeper`): add it to `DECKS` in `src/engine/decks.py`.

Either way, smoke-test before trusting any numbers:

```
python3 cli.py --deck1 <name> --deck2 dragapult --games 5 --seed 1   # if registered
```

or the equivalent `run_recipe(...)` call for an unregistered deck. Zero
exceptions, sane-looking win/loss split. If it throws, that's an engine or
deck-recipe bug — fix it before running real numbers.

## 4. Run the real numbers

Default reference gauntlet — always include `dragapult` (the faithful,
tournament-accurate meta benchmark); add others the deck is specifically
built to beat or is likely to struggle against:

```
python3 cli.py --list   # dragapult, charizard_xy (both faithful tournament
                         # lists), no_vacancy, innkeeper, plus archetype decks
                         # (gardevoir, raging_bolt, greninja, fire, water,
                         # dark, metal, fighting, colorless, beedrill)
```

For each gauntlet opponent, run BOTH:

```
python3 cli.py --deck1 <name> --deck2 <opponent> --games 1000 --seed 2026 --agent greedy
python3 cli.py --deck1 <name> --deck2 <opponent> --games 100  --seed 2026 --agent mcts
```

Note: the deterministic shuffle is sensitive to the *order* cards appear in
the recipe list, not just the multiset — the same 60 cards listed in a
different order will play out differently for the "same" seed (confirmed
while building the import UI: a hand-written `DECKS` recipe and an
auto-imported recipe for the logically identical no_vacancy list gave 60.5%
vs 63.0% at n=200, seed 2026, purely from list-order differences feeding the
shuffle). This is expected, not a bug — it washes out statistically at
n=1000+ — but don't be alarmed if two "identical" recipes don't reproduce
bit-for-bit; only the exact same recipe list object/order is guaranteed to.

Always report both numbers, never just greedy. The project's own validation
notes (`docs/VALIDATION_RESULT.md`) warn that greedy ranks attacks by printed
damage and can't sequence multi-turn plans — it inflates aggro and mispilots
combo/control decks. If greedy and MCTS diverge by more than ~5-8 points,
that divergence is itself a finding worth calling out in the doc (it happened
with Innkeeper: 50.4% greedy vs 61% MCTS vs Dragapult — greedy was flatly
wrong about that matchup).

If you have time budget, save one representative game per matchup
(`--save-game`) and grep its log for the deck's key interactions, so the
strategy prose in the PDF describes what the deck ACTUALLY does in a real
game, not just what the decklist implies it should do.

## 5. Author the HTML

Copy `template.html` (in this skill directory) to a scratch path and fill
every `<!-- FILL: ... -->` marker with real content:

- Re-pick `--primary`/`--finisher`/`--caution` as hex values that fit this
  specific deck's identity — don't ship the No Vacancy green/orange/amber on
  an unrelated deck; a reused palette reads as templated.
- The phase sections are NOT boilerplate — derive them from this deck's
  actual card texts and this deck's actual sim/log behavior. A fast attacker
  needs a damage-math/sequencing phase, not a "the grind" phase; a mill deck
  needs a discard-tracking phase. Adapt the shape, don't force-fit it.
- The bad-draw recovery section must name THIS deck's actual dead-card traps
  (which Stage 1/2 lines can brick, which cards need no evolution as
  fallbacks) and this deck's actual dig tools (Ultra Ball / Poffin / whatever
  it runs) — not a copy-paste of Budew/Munkidori advice from a deck that
  doesn't run them.
- Matchup grades and the sim table come directly from step 4's numbers.
- No hedge/caveat line at the top ("if you meant X instead, say so") — state
  the finding directly.

## 6. Render to PDF and verify visually

```
.claude/skills/deck-playbook/render_pdf.sh <scratch>/playbook.html <out>/playbook.pdf
cd <out> && pdftoppm -png -r 100 playbook.pdf page && ls page*.png
```

Read every rasterized page with the Read tool before sending anything. Known
print-CSS failure modes to check for (both bit us building No Vacancy):

1. **A whole `<section>` with `break-inside: avoid`** — if the section
   doesn't fit the remaining page, the ENTIRE section jumps to the next
   page, leaving a large blank gap at the bottom of the current one. Only
   apply `break-inside: avoid` to small atomic elements (`.callout`,
   `.datatable`, `.decklist`), never a whole phase section.
2. **`white-space: nowrap` on a long-text table column** — if a cell's text
   can be more than ~3-4 words, nowrap forces it onto one very wide line,
   which blows the table past the printable page width. The overflow isn't
   reflowed or scrolled in a PDF (there's no scrollbar) — later columns get
   silently clipped off-page while the row still reports a tall height for
   the invisible content that would have wrapped there. Only use the `.card`
   class (bold+nowrap) on genuinely short columns like a card name.

If a page looks wrong, fix the HTML and re-render — don't ship a PDF you
haven't looked at page-by-page.

## 7. If asked for a TCG Live import paste

Real format, confirmed against actual exported TCG Live text (not guessed):
`Pokémon: N` / `Trainer: N` / `Energy: N` headers, blank line between
sections, card lines as `<qty> <Name> <SET> <number>` — no parens, no hyphen,
no zero-padded numbers (`25` not `025`, confirmed import-breaking bug).
Trainer and Item/Supporter/Stadium and Energy lines resolve by **name alone**
in TCG Live — drop the set code on those entirely. There's no upside to
including one and a real risk if it's subtly wrong. Pokémon lines have no
reliable name-fallback (too many cards share a name across prints with
different text), so they need a verified set+number.

**Promo cards are a distinct, higher-risk category — flag them BEFORE
sending the paste, not after it fails.** Any card whose only standard-legal
printing is a promo (set code `SVP`/`PR-<era>`, a Black Star Promo, a
tournament-kit or event exclusive — anything that isn't a mainline numbered
set) is meaningfully more likely to fail import even with a verified-correct
printed set+number. TCG Live's digital client sometimes indexes promo
variants under an internal code instead of the real printed one (confirmed
real-world case: a Cosmo foil Boss's Orders imports as `SWSHALT 127`, not
its printed `BRS 132`) — and a wrong code fails with the same generic
"Invalid Set ID" whether the code was guessed wrong or the card just isn't
digitized under any printed code at all, so there's no error-message signal
to tell you which. This already cost a real user two failed imports on a
single `Pecharunt SVP` line (tried 129, then 149, both rejected) before the
actual fix — the in-app card search, not another code guess — was found.

So: when handing over an import paste, identify every promo-only card up
front and say so explicitly in the same message — "X is a promo card; if
this line fails, use the client's own card search instead of trying another
set code, don't just guess a third number." One sentence, said before the
user tries it, not diagnosed after two failures.

## 8. Deliver

Publish the HTML via the Artifact tool (pick a fresh favicon emoji reflecting
this deck, not the same one as an unrelated prior deck) and send the PDF via
SendUserFile. Report the headline sim numbers in the chat reply, not just in
the document.
