---
name: ladder-doctrine
description: After coaching a real ladder game (a LADDER_LOG.md entry has just been written or is about to be), check the game against docs/DOCTRINE.md's standing rules and update it — confirm, refine, or add doctrine. This is analysis, not deckbuilding: a game that produces no new registry deck is still a complete, productive pass if it sharpens doctrine. Use after every real game log, not on a schedule.
---

# Ladder doctrine review

`docs/LADDER_LOG.md` is the evidence (one real game, dated, never
generalized past what it showed). `docs/DOCTRINE.md` is the conclusions —
standing, checkable rules that have shown up more than once or are
load-bearing enough to check every future game against. This skill is the
bridge between them. Run it every time a real game gets logged — it does
NOT require building or touching a deck to count as done.

## 1. Read both files first

`docs/DOCTRINE.md` in full (it's short by design — if it's grown past ~15
entries, that's a signal some should be merged or retired, not a target to
hit) and the LADDER_LOG.md entry for the game just logged (or about to be).

## 2. Check the game against every standing doctrine entry

For each entry in DOCTRINE.md, ask: did this game touch the situation that
entry describes at all?
- **Not applicable** — the situation never came up. Say nothing about it;
  don't force a connection.
- **Held** — the situation came up and the doctrine's rule was followed.
  Note it briefly in the coaching reply ("D3 held again — Kanga opened
  Active"); if this pushes a single-instance entry to a second clean
  confirmation, upgrade its `*Status:*` line to **CONFIRMED** in
  DOCTRINE.md.
- **Violated** — the situation came up and the doctrine's rule was broken.
  Say so plainly in the coaching reply, same as any other real mistake. If
  this is the doctrine's first violation after a run of confirmations,
  that's worth flagging explicitly — it either means the read was
  situational all along (note the exception in DOCTRINE.md rather than
  quietly dropping the rule) or it was a genuine misplay (log it as one).
- **Contradicted** — the situation came up and doing the OPPOSITE of the
  doctrine's rule was clearly correct. Don't paper over this. Update the
  entry's status to flag the contradiction and the condition that flipped
  it, the same way D9 explicitly records a non-transfer rather than
  deleting the original claim.

## 3. Check whether anything new generalizes

A single game producing a genuinely new, checkable insight — not "this
opponent's deck was strong," but a rule that would change how a FUTURE game
gets played — is a candidate for a new DOCTRINE.md entry. The bar: would
you want to check a future game against this? If yes, it's doctrine. If the
lesson is entirely about this one opponent's specific decklist with no
generalizable shape, it stays in LADDER_LOG.md only.

Before adding: search DOCTRINE.md (and grep LADDER_LOG.md for "doctrine")
for whether this insight — or something close to it — already exists,
scattered or otherwise. **The known failure mode this skill exists to
prevent is a good insight getting noticed once, in one game's writeup, and
then never checked again** (see DOCTRINE.md's own note on D10/D12 — the
same deck-out read was independently rediscovered three weeks apart because
nothing promoted the first sighting). If a close match exists, that's not a
new entry — it's evidence for an existing one; add the cross-reference and
consider whether the existing entry's status should move toward CONFIRMED.

New entries follow the existing format exactly: statement, *Why:*
(mechanism, not just "it worked"), *Evidence:* (dated game + opponent),
*Status:* (single confirmation / CONFIRMED with count / flagged
contradiction). Never state a mechanism you haven't verified against the
actual log lines — same no-guessing discipline as the rest of this project
(`feedback_ptcg_no_bs_coaching`: verify, don't assert from memory).

## 4. Write it back

Edit `docs/DOCTRINE.md` directly for any status change or new entry. Commit
alongside (or immediately after) the LADDER_LOG.md commit for that game —
same message is fine if both changed together — following this repo's
existing commit style (see `git log` for the `ladder:` prefix convention).

## 5. Say it in the coaching reply, not just the file

The point of this routine is that the user sees doctrine working in real
time, not buried in a doc they have to go read. When replying about a real
game, name which doctrine applied (held/violated/new) as part of the normal
coaching response — the same way a chess coach names the opening principle
that was followed or broken, not as a separate report.

## What this is not

Not a deck-building trigger, not a meta-scan, not a request to run the
gauntlet. A game that surfaces zero new doctrine and confirms nothing new
is still a complete pass — say so plainly ("nothing new for doctrine this
game") rather than manufacturing a forced insight to justify the check.
