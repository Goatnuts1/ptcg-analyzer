---
name: verify-next
description: Things to re-check in future PTCGCoach sessions
metadata:
  type: project
---

Re-check whether these are fixed/changed before re-litigating:
- Are Iono / Professor's Research / Nest Ball / Earthen Vessel now in cards.json? (grep). If added, re-run importer to confirm legality passes and the false Legality reps disappear.
- Does the Meta detail board still show the greedy table while Simulate shows the prize-race model? Has either been labeled/reconciled?
- Coach Analysis: does the segmented highlight match the shown player's analysis now?

Not yet exercised live (verify these actually fire on-screen, not just in unit tests):
- Importing a USER-pasted deck end-to-end (paste UI) then tapping Simulate — only the hardcoded Gardevoir AUTOSIM path was screenshotted. Try osascript taps or a new hook.
- "Save to My Decks" from Meta, and the My Decks library persistence.
- Review import from a FILE (vs the seeded sample) and PTCG_SEEDGAME library row.
- The matchup-board screen on a Meta deck (no hook exists; needs real taps).

Deck-search next steps: confirm Crabominable vs Wailord on a fully legal shell; probe whether any 1-prize attacker loses to Dragapult/Beedrill less than Zekrom's 55%.
