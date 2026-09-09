# Doctrine — standing lessons from real ladder play

`docs/LADDER_LOG.md` is the **evidence**: one entry per real game, dated,
opponent-specific, never generalized past what that single game showed. This
file is the **conclusions** — the subset of ladder findings that have shown up
more than once, or are load-bearing enough to check every future game against
on their own. A doctrine entry is a checkable rule, not a war story.

**Why this file exists:** before 2026-09-09, "doctrine" only ever appeared as
an inline aside inside a specific game's writeup (grep `docs/LADDER_LOG.md`
for the word — seven scattered hits across three weeks of games). The
2026-08-23 JackoTheClown game contains almost the exact deck-out read that
won the 2026-09-09 Tristan421870 game (see D10/D12 below) — the same good
instinct, independently rediscovered three weeks apart, because nothing ever
promoted the first sighting into a standing rule anyone would check against.
This file, plus the `ladder-doctrine` skill, is the fix: **a real game is a
productive session even when it doesn't produce a new registry deck.**

Status key: **CONFIRMED** = held across 2+ independent games with no
contradiction. Single-instance entries say so plainly and should be read as
hypotheses, same provenance discipline as `LADDER_LOG.md` itself.

---

## Positioning & tempo

**D1 — Evolve into the Mega the turn it acts.** Don't sit a pre-evolution on
the bench past the turn it can evolve-and-swing.
*Why:* every turn spent as a pre-evolution is a turn of zero pressure and a
bench target that threatens nothing.
*Evidence:* 2026-08-24 vs `Birulas` — Drilbur held to turn 3, then evolve +
Maximum Drilling 330 in one motion; went on to score 3 of 4 KOs.
*Status:* single confirmation.

**D2 — Kill the win-condition while it's cold.** Gust (Boss's Orders /
Catcher-class) an opponent's benched, unfueled win-condition piece before it
powers up, rather than waiting for it to become a bigger threat.
*Why:* a Mega/ex sitting on 0–1 Energy that gets gusted into a KO dies having
contributed nothing; waiting lets it fuel up and either escape retreat range
or hit back first.
*Evidence:* 2026-08-24 vs `Birulas` — Boss's Orders dragged a 1-Energy,
never-attacked Mega Gengar ex into Maximum Drilling; their win condition died
without acting.
*Status:* single confirmation.

**D3 — A multi-prize body either opens Active or waits in hand; never bench
it mid-game unfueled.** CONFIRMED, most-repeated doctrine in the log.
*Why:* every multi-prize attacker sitting idle on the bench is a free
Boss's-Orders/gust target — 2–3 prizes for the opponent at zero risk to them.
*Evidence:* violated FOUR recorded times before being isolated as a pattern
(culminating 2026-08-26 vs `Pandabirb` — Mega Kangaskhan benched turn 3 with
2 Energy and no attack plan, fed a Boss + Energized Storm for 3 prizes);
refined 2026-08-30 vs `leoNardocruz000` (Kanga opened Active instead, went
5-KOs-for-3, "a trade worth taking every time"); held again 2026-09-01 vs
`JJ-Zacian` ("Kanga OPENED Active per the 08-30 refinement").
*Status:* **CONFIRMED** — 2 clean follow-through games since the refinement,
zero violations since. High confidence; check every game a multi-prize
attacker sits unplayed on the bench.

## Damage math & resource denial

**D4 — Know what the opponent's attack scales on, and starve it.** Before
chipping a target, check whether the OPPONENT's next attack scales off
something you're about to hand them (damage counters already on their own
Pokémon, their board's attached Energy, bench width, discard pile size,
hand size). Don't feed it unless the chip secures a kill this turn.
*Why:* self-feeding scalers turn a "safe" chip attack into arming the
opponent's next haymaker — chip damage isn't free just because it's small.
*Evidence:* THIRD documented instance as of 2026-08-26 vs `RSBKChise` —
Hungry Jaws (Mega Sharpedo ex) is +150 flat if the target already has ANY
damage counters; a 60-damage Metang chip armed a 270 one-shot. Earlier
instances: Myriad Leaf Shower (eats our attached Energy), Feather
Rondo/Mind Jack (eat our bench width).
*Status:* **CONFIRMED**, 3+ instances across different scaling mechanics —
this is a general pre-attack check, not a card-specific one.

**D5 — Bench-width has a real, measured cost against scaling spread
attacks.** A wide-bench opening (Precious Trolley and similar fill-the-bench
tools) isn't free against a Feather-Rondo/Mind-Jack-class attack that scales
off bench count.
*Why:* measured directly in one game — Mind Jack at 5 benched (160 dmg)
cleared 2 Metagross; the same attack at 4 benched (130 dmg) killed nothing.
*Evidence:* 2026-08-24 vs `Birulas`.
*Status:* single confirmation, but a hard measured threshold — worth
re-checking bench count before a fill-the-bench play vs any spread deck.

## Wall & archetype-identity doctrine

**D6 — Vs ex-attacker decks, an ability-based ex-wall isn't just a win
condition, it's your Mega's bodyguard.** Once Cornerstone Stance / Mysterious
Rock Inn is live, retreat a damaged multi-prize attacker BEHIND it rather
than continuing to tank hits the wall would otherwise blank to zero.
*Why:* the wall reduces an opposing ex-attacker's damage to nothing — every
turn the multi-prize body stays Active and exposed instead is pure unforced
damage taken for no reason.
*Evidence:* 2026-09-01 vs `JJ-Zacian` — Kangaskhan ate FOUR Undermines (360
damage total) while Rock Inn sat unused on the bench; the moment the first
Crustle stood up, the wall should have taken over immediately. Stated in the
log itself as a "new doctrine line."
*Status:* single instance, not yet re-tested — check this explicitly next
time an ex-wall archetype is on the board.

**D7 — The non-ex beater answers the ex-wall, in both directions.** CONFIRMED.
Any deck built around an ex-blanking wall — ours or an opponent's — needs,
and should expect the opponent to run, a non-ex secondary attacker that
walks straight through it.
*Why:* Rock Inn/Cornerstone gate on the ATTACKER's card only, never the
defender's, so a non-ex attacker's damage is completely unaffected by either
wall.
*Evidence:* FIVE separate sightings (Hariyama's Wild Press, Solrock's Cosmic
Beam, Snorlax's Collapse, and twice our OWN Metagross Hammer routing around
Shadowy Concealment/Rock Inn) — most recently 2026-09-01 vs `JJ-Zacian`,
where the opponent's own house-archetype Metagross did exactly what we tell
our pilots to do.
*Status:* **CONFIRMED**, highest instance count of any entry here — read
`crustle_modern`'s/`cornerstone_box`'s matrix cells as optimistic against
any real list until the opponent's non-ex secondary is priced in.

**D8 — A wall deck plays into mill; versus mill, the correct posture is
race, not wall.** Don't stall a mill matchup.
*Why:* a wall wins by making time worthless for the opponent; mill wins BY
spending time. Every turn spent sitting behind a wall compounds the mill
engine's progress instead of neutralizing it.
*Evidence:* 2026-08-27 vs `Reecie_Puffs` — LOSS by deck-out while up 2–0 on
prizes, piloting `crustle_modern`. Explicit finding logged: "a wall deck
plays into mill — walls win slow, mill wins slower games harder."
*Status:* single instance, but a LOSS, and costly enough to trust without a
second data point.

**D9 — A deck's resilience trait doesn't transfer to a different deck, even
a stronger one.** CONFIRMED as a non-transfer.
*Why:* "this deck doesn't deck itself out" is a property of ITS specific
resource-recursion tools (e.g. Energy Recycler's shuffle-back loop), not of
"being the best deck" in general — audit resource-out risk per decklist.
*Evidence:* originated 2026-08-23 vs `JackoTheClown` ("Mega Excadrill is
nearly deck-out-proof"); explicitly did NOT transfer, confirmed 2026-08-27
vs `Reecie_Puffs` ("the JackoTheClown doctrine does NOT transfer —
`crustle_modern` is draw-heavy with no Energy-Recycler-style shuffle-back,
making mill its THIRD documented livefire predator").
*Status:* **CONFIRMED** as a non-transfer — never assume deck-out resistance
from a deck's overall win rate.

## Deck-out as a live win condition

**D10 — Deck-out is a legitimate race, but subordinate to a faster attack
line when one exists.** If ahead and the board can close in 1–2 turns, take
the attack — don't switch to playing for a 6–8 turn deck-out with a faster
kill sitting right there.
*Why:* the math the pilot ran live: at 5–0 prizes with a KO-per-turn line,
prizes finish in ~1–2 turns vs ~6–8 for a deck-out race. Attack while ahead;
keep deck-out as the fallback if the attack line stalls, not the default.
*Evidence:* 2026-08-23 vs `JackoTheClown` — the pilot spotted the opponent's
asymmetric draw-engine deck-out risk mid-game and the read was confirmed
sound, but correctly subordinated to the faster attack line already live
that game.
*Status:* single instance, confirmed sound.

**D11 — Deck-out is checked at the draw step, before prizes are read: the
prize differential does not matter once it's live.** Don't weigh "am I
ahead on prizes" when deciding whether a deck-out race is worth playing for
— it's binary, independent of score on either side.
*Why:* the rule itself. A player who cannot draw for their turn loses
immediately, regardless of prizes taken by either side.
*Evidence:* 2026-09-09 vs `Tristan421870` — WIN by opponent deck-out while
DOWN 3–5 on prizes.
*Status:* rule-level. Flagged as its own entry because D10 and D11 are easy
to conflate in the moment — see D12's note below for how to tell them apart.

**D12 — Read resource-strain tells, and pivot to clock-denial once a
deck-out race is actually live.** NEW as of 2026-09-09.
Two tells, in order:
1. A big refill Supporter (Lillie's Determination-class) that shuffles back
   almost nothing before drawing a full hand. A small shuffle-in count
   reveals a near-empty hand under what LOOKS like a power turn on the
   surface (2 cards → 8 is not the same signal as "8 cards, no tell").
2. Once spotted, STOP attacking/trading and hold the board. Passing costs
   nothing; every KO taken while the opponent is thin is a turn spent
   feeding trades instead of denying draws, and every KO given away is a
   prize that wasn't needed once the opponent physically cannot reach 6.
*Why:* once a real deck-out race is live, continuing to trade — even
winning trades — is pure downside. It does nothing to hasten the actual win
condition and exposes the board to more damage for no reason.
*Evidence:* 2026-09-09 vs `Tristan421870` — a `Lillie's Determination`
shuffled back exactly 1 card before drawing 8 (the tell); the pilot answered
with two consecutive non-attacking turns (build board, pass) instead of
continuing to trade into a Phantom Maze that could two-shot anything on the
board. Opponent decked out on their following draw step.
*Status:* single instance, but directly continuous with D10's origin (see
below) — treat as provisionally confirmed pending a second sighting.

**How D10 and D12 relate — the actual decision rule:** is the current attack
line WINNING the prize race outright, or just trading? If it's winning
outright (D10's case), keep attacking — deck-out is the fallback, not the
plan. If it's just trading — even trading favorably — and the opponent shows
a resource tell (D12's case), the deck-out read becomes the PRIMARY plan and
continued trading is a cost, not progress. The 2026-09-09 game had no faster
attack line available (down 3–5 on prizes into a two-shotting attacker), so
D12 correctly took priority over continuing to trade.

**On "why wasn't this already obvious":** it basically was — D10's origin
game (2026-08-23) is the same instinct, independently confirmed sound at the
time, and then never checked again for three weeks because there was no
standing doctrine file to check it against. That gap is the actual finding
here, not the deck-out read itself.
