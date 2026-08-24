# TCG Live battle-log import — first fidelity report

**Date:** 2026-08-16, updated 2026-08-17 · **Parser:** `src/importers/tcglive_log.py` · **Tests:** `tests/test_tcglive_log.py`

## What was measured

55 real Pokémon TCG Live games, 2026-07-16 → 2026-08-17, one seat (`Goatest1`) across
~20 opponents on ladder. Record 29–26. Total 10,351 log lines.

Two games (vs `Alamo789`, Dragapult ex / Blaziken ex; vs `Ramukaka22`, Mega Darkrai ex /
Toxtricity) were captured AFTER the parser was written and are the only true holdouts:
**100% of their lines parsed on the first try**, including line shapes absent from the
other 53 (`Pokémon ex: 90 damage` and `2 damage counters: 110 damage` breakdown
components, `Unfair Stamp`'s double shuffle, `All Prize cards taken. X wins.`). They
produced Findings 3 and 4 below.

**The corpus is not in this repo, and shouldn't be.** The logs were recovered from pasted
text in prior Claude Code session transcripts (`~/.claude/projects/`); they name real
opponents' ladder handles. The parser's tests use synthetic fixtures written in the
client's exact phrasing instead. To re-run this report, re-extract to a scratch directory
and point `analyse()` at it.

**Why this matters:** every win rate this project has ever printed is engine-vs-engine.
A card whose script is subtly wrong stays wrong, because the unit test asserting it was
written from the same reading of the card. A real log is the only input that can
contradict us.

## Result: the log format is fully machine-readable

| | |
|---|---|
| lines parsed | **10,343 / 10,351 (99.9%)** |
| lines left unparsed | 8 — all of them **your own chat messages** pasted with the logs ("How the hell did I get nuked?") |
| distinct card names seen | 288 |
| resolved against the pool | **272 (94.4%)** |
| distinct event kinds | 57 |

Nothing about the format blocks a replay harness. The client emits one event per line
with an explicit actor, sub-effects nested one level down, and full damage breakdowns
(base / Weakness / Resistance / attack modifiers / total). Turn boundaries, coin flips,
prize counts, mulligans and the win condition are all recoverable.

Three quirks cost real effort and are documented in the module, because anything built on
top will hit them:

1. **Two paste dialects.** `- child` + `• grandchild` in one, `    •    child` + flush
   `• grandchild` in the other. Bullet depth alone is not a nesting signal.
2. **Mixed apostrophes inside a single line** — ASCII for the acting player, U+2019 for
   the target.
3. **Card names contain possessives** ("N's Zoroark ex", "Team Rocket's Petrel"), so
   possessive splitting must be anchored on a known player handle, not on `'s`.

A structural note for anything downstream: **a log is single-observer.** Your draws are
named, the opponent's are `drew a card`. `GameLog.observer` records which seat it came
from, and `draw_named` vs `draw_hidden` keeps the distinction. This mirrors the honest
limit already documented for `ISMCTSAgent`.

## Finding 1 — the card pool has a hole, and it is a set-coverage hole

16 distinct card names were played in real games and do **not** exist in
`data/standard_pool.json`:

| occurrences | games | card |
|---|---|---|
| 18 | 1 | Tyrantrum |
| 10 | 1 | Mega Zeraora ex |
| 9 | 1 | Tyrunt |
| 8 | 1 | Mega Zygarde ex |
| 8 | 1 | Morpeko ex |
| 7 | 1 | Fossil Quarry |
| 6 | 1 | Mega Darkrai ex |
| 6 | 2 | Earthen Vessel |
| 5 | 1 | Antique Jaw Fossil |
| 4 | 1 | Technical Machine: Evolution |
| 3 | 3 | Dark Bell |
| 2 | 2 | Youngster |
| 2 | 1 | Jacinthe |
| 2 | 1 | Shadowy Darkness Energy |
| 1 | 1 | Gladion's Final Battle |
| 1 | 1 | Nest Ball |

The distribution is the tell: most appear in exactly one game, i.e. one opponent's deck,
which points at missing *sets* rather than missing *staples*.

Grouping the pool by set id confirms it. Several recent sets are present **only** through
the hand-maintained supplement:

```
set    cards in pool    of which from data/manual_cards.json
pbl              9                    9
asc              3                    3
me5              3                    3
cri              2                    2
me4             47                    0
me3             14                    5
```

The automated fetch has **zero** coverage of PBL / ASC / ME05 / CRI. Every card the
project owns from those sets is one of the 26 cards someone added by hand, one at a time,
as a specific deck needed it. That is why `data/manual_cards.json` exists — but it means
the pool silently under-represents whatever nobody has needed yet, and there is no signal
when that happens. This corpus is that signal.

**Caveat, stated plainly:** I have not verified the set of each individual missing card —
that needs a fetch, which is a network call this run didn't make. "Consistent with the set
gap" is the claim; "proven to be in PBL" is not. `Nest Ball` and `Earthen Vessel` are worth
checking separately, since both are widely played and their absence may instead mean their
current print rotated and my expectation is stale.

## Finding 2 — bare card names can't identify a print, and 13 times they picked wrong

The log writes `Metagross`, never `Metagross (CRI)`. For 13 (card, move) pairs, the move
the log says was used does not exist on the print the pool holds under that bare name:

| pair | pool's print has | verdict |
|---|---|---|
| Metagross: Metallic Hammer | Meteor Mash, Luster Blast | **resolvable** — `Metagross (CRI)` has it |
| Banette: Puppet Pull | Cursed Words, Spooky Shot | **resolvable** — `Banette (PBL)` has it |
| Dhelmise: Vengeful Anchor | Spinning Attack, Steel Anchor | **resolvable** — `Dhelmise (PBL)` has it |
| Metagross: Bounce Back | `Metagross (CRI)` has "**M** Bounce Back" | a NAME mismatch, not a missing print — see Finding 4 |
| Froakie: Collect | Flock, Flop | no print in the pool has it |
| Kadabra: Psychic Draw | Psychic | ” |
| Miraidon: Photon Cord | Peak Acceleration, Sparking Strike | ” |
| Misdreavus: Ascension | Petty Grudge | ” |
| N's Darmanitan: Evolution | Back Draft, Flamebody Cannon | ” |
| Noibat: Rapid Draw | Flap | ” |
| Riolu: Accelerating Stab | Punch | ” |
| Tauros: Target Together | Destructive Horn | ” |
| Venipede: Poison Spray | Spit Poison, Spinning Attack | ” |

Two different problems wearing the same shirt:

- **3 are a resolution bug.** The correct print is already in the pool under its suffixed
  name; a bare-name lookup just can't find it. A log importer needs to disambiguate on
  evidence — the move used — rather than on name alone. The parser reports these instead
  of guessing, which is why they're visible at all.
- **1 is a transcription error in our own data** (Finding 4).
- **9 are Finding 1 again.** The pool holds one print per name (it dedupes by name), and
  the print actually played isn't in it.

This is worth stating precisely because it bears on `CLAUDE.md`'s print-collision rule.
That rule is sound and is not in question here: registry keys must use the exact suffixed
name. What this corpus adds is that **inbound** data — a log, and by extension any future
scraped list — arrives with bare names, so the import path needs a print-resolution step
that the deck importer currently doesn't have either.

## Finding 3 — the log lies about who owns a damage counter

The possessive on a damage-counter destination is **the acting player's, regardless of who
actually owns the Pokémon**. Measured against ownership evidence elsewhere in the same log
(the same Pokémon being played, evolved, promoted, retreated or attacked as a given
player's):

| event | total | label correct | label contradicted |
|---|---|---|---|
| `moved N damage counters ... to X's <mon>` | 21 | **0** | **21** |
| `put N damage counters on X's <mon>` | 35 | 17 | 17 |

`moved` is wrong every single time. `put` is right exactly when the effect is
self-targeting — Toxtricity's Sinister Surge damages its own side, so the actor's
possessive happens to be correct — and wrong whenever the effect reaches across the board.
**You cannot tell the two cases apart from the line itself**, which is what makes this
dangerous rather than merely annoying.

The 54th game proves it arithmetically rather than by inference:

```
Alamo789's Dragapult ex used Phantom Dive on Goatest1's Metagross for 200 damage.
- Alamo789 put 6 damage counters on Alamo789's Metang.        <- Alamo789 has no Metang
Goatest1's Metagross was Knocked Out!
Goatest1's Metang was Knocked Out!
```

Alamo789 never had a Metang in play. Goatest1's benched Metang did — carrying exactly 40
damage, taken back on turn 3 as a Beldum and kept through evolution. Metang has 100 HP,
6 counters are 60, and the very next line is that Metang being Knocked Out. The counters
landed on the opponent's board while the log attributed them to the attacker's own.

The 55th game shows the same bug in the `moved` shape, again with arithmetic:
Munkidori's Adrena-Brain moved counters onto "Ramukaka22's Drilbur" three times
(3 + 3 + 2 = 8 counters = 80 damage) and then `Goatest1's Drilbur was Knocked Out!`.
Drilbur has 70 HP, Ramukaka22 never had one, and the KO lands exactly where the running
total crosses 70.

Nor can it simply be inverted, because at least one shape gets **both** fields wrong in
the other direction:

```
5167's Mega Slowbro ex used Shellnado Spin.
- Goatest1 put 12 damage counters on 5167's Mega Excadrill ex.
```

The attacker is 5167; the Mega Excadrill ex is Goatest1's. Here the *actor* names the
victim's owner and the *possessive* names the attacker — the exact opposite of the
Phantom Dive case. The reliable signal in both is the **parent attack event**, not the
child's own possessives.

**Consequence for the replay harness:** the possessive on this event is not usable input.
The target has to be resolved from board state — which Pokémon can actually receive the
counters, and which totals are consistent with the KOs the log reports on the next line.
This is a good argument for building the harness to *reconcile* the log against engine
state rather than to *replay* it literally: the log is evidence, not a command stream, and
it has at least one systematic error in it.

## Finding 4 — one of our hand-transcribed attack names disagrees with the client

`Metagross (CRI)`'s first attack is recorded in `data/manual_cards.json` as
**"M Bounce Back"**, and `effects.py` registers the effect under that exact key
(`("Metagross (CRI)", "M Bounce Back")`). The client writes:

```
Goatest1's Metagross used Bounce Back on Ramukaka22's Gastly for 60 damage.
```

Same print (its other attack, Metallic Hammer, matches), same 60 damage, same
switch-out effect — but the client calls it **"Bounce Back"**, with no `M` prefix.

Severity is low and worth stating honestly: the engine is internally consistent, so the
effect fires correctly today and no test is wrong. What it costs is *external* agreement —
any check against real card data, and any log-driven move matching, sees a name that
doesn't exist. This is exactly the failure mode the manual supplement invites: 26 cards
transcribed by hand, with nothing to check them against until now.

**Not fixed here.** The evidence is one client log line; `CLAUDE.md`'s rule is to never
invent card text, and correcting card data on my own reading is the same move in reverse.
Confirm against the physical/digital card and it's a three-line change (the supplement
entry, the registry key, and a comment in `decks.py`).

## Finding 5 (RESOLVED) — a 2-Prize Mega KO, explained by an Ability the log never names

One observation (2026-08-24, vs `Birulas`): `Mega Gengar ex` was Knocked Out and
the client awarded **2** Prize cards, though the Mega Evolution ex Rule says 3
(and the client has awarded 3 for our own Mega Excadrill ex in three logged
games). Resolution — pilot-supplied, then confirmed in the pool entry (me2-56):
Mega Gengar ex's Ability **Shadowy Concealment** — "If 1 of your Darkness
Pokémon is Knocked Out by damage from an attack from your opponent's Pokémon
ex, that player takes 1 fewer Prize card." The KO came from Mega Excadrill ex
(an ex): 3 − 1 = 2. Consistently, a later Gengar KO by the same attacker paid
the full prize — Mega Gengar ex had left play, taking its Ability with it.

The FINDING that survives the resolution: **the log never mentions the
Ability.** No "Shadowy Concealment was activated" line — the prize count is
just silently different. A replay/reconcile harness cannot treat prize counts
as derivable from the KO event alone; passive abilities alter them invisibly.
(Also surfaced: plain **Gengar with "Mind Jack"** — 10 + 30 × opponent's Bench
— is a pool gap.)

## What this does not do

The parser reads logs. It does **not** replay them against `GameState`, and no claim in
this document is a validation of the engine's *rules*. Card resolution and move ownership
are checked; damage arithmetic, legality of sequences, and prize math are not — those need
the replay harness, which is the natural next piece and now has a trustworthy front door.

## Suggested next steps, in order

1. **Re-run the pool fetch with PBL / ASC / ME05 / CRI included**, then re-run this report.
   Findings 1 and 2 should both shrink sharply. This is the cheapest high-value fix.
2. **Add print resolution to the import path** — when a bare name is ambiguous, pick the
   print whose attack/ability list contains the move the log actually used.
3. **Build the replay harness.** Drive `GameState` from the event stream and diff engine
   damage against the log's `Damage breakdown:` totals. That is the first real test of
   card fidelity against evidence the project did not author.
4. **Then, and only then, policy evaluation.** 53 games of real human decisions is a test
   set for asking whether `greedy` / `mcts` / `mcts2` choose the move a laddering human
   chose — a sharper question than any self-play win rate.
