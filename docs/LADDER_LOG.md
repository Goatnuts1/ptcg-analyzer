# Ladder log — real TCG Live matches

A running record of real games played on ladder as `Goatest1`, with the pilot lessons
that came out of them. This is the **evidence side** of the project: everything else here
is engine-vs-engine, so a real match is the only place a wrong assumption gets punished by
something other than our own code.

Provenance rules: a match here is a single game, not a sample. Conclusions drawn from one
game are hypotheses to be tested in the sim, and are marked as such. The parsed logs live
outside the repo (they name real opponents) — see `docs/TCGLIVE_LOG_FIDELITY.md`.

Deck piloted unless stated: **`mega_excadrill`** (the house list) through 2026-08-22.
**As of 2026-08-23 the piloted deck is `mega_excadrill_shaymin`** (the anti-bench-wipe
variant: +2 Shaymin (DRI), +1 Gravity Mountain, −1 Ethan's Pichu, −1 Special Red Card,
−1 Jumbo Ice Cream) — switched after the Fmz1822 Trifrost loss made it three real losses
to turn-2/3 bench wipes. The open question this switch tests: does Flower Curtain
actually convert the Slowking-toolbox matchup (real record 0–3) — and what does the
Grimmsnarl handicap cost in practice? Games below state the deck when it matters.

---

## 2026-08-17 · vs `Ramukaka22` (Mega Darkrai ex / Toxtricity) · **WIN 6–3**

Went second. Their engine: Toxtricity's Sinister Surge accelerates Darkness Energy but
puts 2 damage counters on **their own** Pokémon; Munkidori's Adrena-Brain then relocates
that self-inflicted damage onto our board. Self-damage as a resource — it killed a benched
Drilbur for a free prize without ever attacking it.

Prize flow: they took 2 (Genesect ex) + 1 (Drilbur) = 3. We took 3 (Mega Darkrai ex) +
1 (Gastly) + 2 (Meowth ex) = 6.

**Done well**

- **Metallic Hammer into Mega Darkrai ex for 3 prizes.** The single highest-value swing
  available: their main attacker, two Darkness invested, and a Mega giving up 3. Half the
  game won in one attack. This is the mirror of the `Alamo789` loss below, where the same
  rule ran the other way.
- **Correct read that the retreat was worth it.** Retreating Mega Excadrill ex cost 4
  Basic Metal Energy (its full retreat cost), which is brutal — but Maximum Drilling's 200
  would not have KO'd a Mega Darkrai ex sitting on only 10 damage, and Metallic Hammer's
  300 did. Paying four Energy to convert a 1-prize turn into a 3-prize turn is right.
- **Closing on prize math, not on damage.** The last Boss's Orders pulled Meowth ex — a
  2-prize ex — when exactly 2 prizes remained. Correct target selection to end it rather
  than the biggest available hit.
- **Air Balloon pivot on the final turn**, letting Metagross leave the Active Spot after
  it had already discarded 3 Energy to Metallic Hammer and couldn't pay retreat.

**To do better**

- **The Boss's Orders on Gastly is the questionable one.** It bought 1 prize off a
  freshly-benched basic. Meanwhile **Munkidori** — the piece relocating damage onto our
  board every single turn, and the piece that took Drilbur — was never touched, and went
  on to keep working for the rest of the game. Killing the engine over taking the cheap
  prize is the line worth testing.
  *Caveat:* Metagross attacked with Bounce Back (60), not Metallic Hammer (150), which
  suggests it was short of Energy at that moment. Munkidori has 70 HP, so Bounce Back
  would not have KO'd it either. Whether the better line existed depends on Energy in hand
  on that turn — the log doesn't fully show it. **Hypothesis, not a verdict.**
- **Energy attrition is this deck's real cost curve.** Across the game we discarded 4
  Energy to one retreat, 3 to Metallic Hammer, 3 more to a second Metallic Hammer, and 1
  to a Metagross retreat. The deck runs 17 Basic Metal and 2 Energy Recycler; neither
  Recycler was used. Worth watching whether Recycler is being held too long.

---

## 2026-08-16 · vs `Alamo789` (Dragapult ex / Blaziken ex) · **LOSS 5–6**

The reverse of the above, and the more instructive game.

Every Pokémon in the deck is ×2 Fire, and this is a Fire deck. Mega Excadrill ex (340 HP)
was one-shot by Smolder-sault (200 base → 400). Even Moltres's 20-base Fighting Wings hit
it for 220. The main attacker was simultaneously the easiest thing on the board to kill
**and** worth 3 prizes — they needed only four Knock Outs to take six prizes.

**Done well:** the damage trade was actually favourable — three of their Pokémon KO'd,
two of them 2-prize ex. Losing on prize *weighting*, not on tempo.

**To do better**

- 40 damage taken on a turn-3 Beldum survived evolution into Metang and was exactly what
  made a later Phantom Dive's 6 bench counters lethal — one attack, two prizes, set up
  eight turns earlier by chip damage.
- `Goatest1 didn't take an action in time.` — a full turn lost to the clock during setup,
  while they were assembling Blaziken.
- Gravity Mountain sat in the opening hand and was shuffled away by our own Lillie's
  Determination, never to reappear. They took the Stadium (Area Zero Underdepths)
  uncontested.

**Standing question this raises:** `Dragapult Blaziken` is **5.99% of the live metagame**
(4th most played) and we have no deck for it. It is the matchup most likely to be
structurally bad for this list, and it is the one we cannot currently measure.

---

## 2026-08-19 · vs `Estel1812` (Cynthia's Garchomp) · **WIN 6–4**

The matrix's closest cell (53.3%) played out exactly as a coin-flip matchup should:
a 2-for-3 prize trade in the middle, decided by which side's cleanup engine was better.
Their board: triple Cynthia's Roserade (Cheer On to Glory stacking to +90 — the log's
damage breakdowns confirm the engine's stacking implementation line for line) plus the
Gabite Champion's Call chain.

**The Mega Excadrill sacrifice (turn 7) was correct, and provably so** — see the
analysis in the session log: with three Roserade benched, Draconic Buster hits
260+90 = 350, which one-shots a FULL-HP 340 Mega. The Mega was un-keepable from that
board state on; the only choice was losing it for 2 prizes (Maximum Drilling KO on
Garchomp #1) or for nothing. Retreat was no escape either — retreat cost 4 discards
4 of its 5 Energy, gutting it as thoroughly as the KO.

**The Gravity Mountain → Metallic Hammer line from the playbook appendix fired and
won the game**: Garchomp ex 330 → 300 under GM, Hammer = exact OHKO (misses by 30
without it). Both edges of the card showed up, though — the same −30 dropped our own
Metagross to 150, so Dragonslice (40+90+30 = 160) one-shot it where it would have
survived at 180. Net still favorable (their 2-prize KO enabled vs our 1-prize loss),
matching the variant test's conclusion that a SECOND copy isn't worth a slot.

**One genuinely wasted card:** the turn-7 Jumbo Ice Cream. Heal 80 only matters
against incoming damage in the 180–260 band (Mega at 160 damage, 340 HP); their two
real attacks were Corkscrew Dive at 160 (survivable unhealed) and Draconic Buster at
350 (lethal healed). Zero scenarios where it changed the outcome — and the copy might
have saved the Gravity-Mountain-weakened Metagross later.

Ladder ledger: 30–26.

---

## 2026-08-20 · vs `KinooThePro` (Mega Zygarde ex / Mega Audino ex box) · **WIN 6–3**

Parser: 199/199 lines (100%). Two cards unresolved — **Mega Zygarde ex** (second
sighting, different opponent: the set-gap evidence from the fidelity report keeps
compounding) and **Mega Audino ex** (new). Lively Stadium, Hero's Cape and AZ's
Tranquility appeared in reveals and ARE resolvable/absent per the pool check.

The scariest single turn of the ladder run so far: turn-3 **Nullifying Zero snipes
the bench for 150 ×3** — two Metang and a fully-loaded Drilbur (4 Energy) died in one
attack, 3 prizes, 0–3 down with our board stripped. Then the comeback:

- **Special Red Card at its exact window.** They had just taken 3 prizes (= 3
  remaining, the card's own condition) with a freshly refueled hand — 9 cards to the
  bottom, draw 3. The disruption landed on the highest-value turn it could exist.
- **Undermine as Energy denial, twice.** Their Zygarde carried 5 Energy; two
  Undermines discarded 4 of it (plus chip damage that eventually finished it after
  Gaia Wave's −30 rider blunted one Maximum Drilling).
- **The all-Mega opposing board pays 3 prizes per KO.** Zygarde KO (3) + Boss's
  Orders dragging Mega Audino ex up for an exact-330 Maximum Drilling (3) = 6 prizes
  in two attacks. Same prize-weighting lesson as the Ramukaka22 game, at maximum
  amplitude.
- Honest ledger note: they timed out on two consecutive turns mid-comeback — the win
  is real, the margin overstates it.

**Deck-building implication worth testing:** Nullifying Zero's bench snipe is exactly
Flower Curtain's use case — the `mega_excadrill_shaymin` variant blanks all three hits
(Metang/Drilbur are non-Rule-Box). The Shaymin call is matchup-split now: RIGHT vs
bench-snipe (Zygarde, Slowking/Trifrost), WRONG vs Grimmsnarl (Freezing Shroud taxes
the extra Ability body). Neither variant dominates; this is a meta call, not a fix.

Ladder ledger: 31–26.

---

## 2026-08-21 · vs `SawyerOverweg` (Cornerstone Ogerpon / Pecharunt ex poison box) · **WIN by concession (2–0 prizes)**

Parser: 130/130 (100%), first live `Pokémon Checkup` poison block and first
`Opponent conceded.` ending, both handled. Morpeko ex: second opponent sighting,
still pool-missing (set gap).

Short game, one clean sequence worth keeping: they used Pecharunt ex's
Subjugating Chains to promote and poison their own Morpeko ex (a gust+setup
engine); we answered by retreating Genesect (2 Energy — cheap vs the Mega's 4)
into Metagross for Metallic Hammer 300, exactly lethal on the poisoned Morpeko:
2 prizes, and their tempo piece gone. They conceded two turns later facing a
full Metal board with Mega Excadrill loaded and their Judge disruption already
spent (it hit our 8-card Lillie's hand but Petrel/Transceiver rebuilt in one
turn — the Team Rocket tutor chain is real disruption insurance).

Note for the anti-disruption ledger: their Boss's Orders dragged Genesect up
early to strand it — the Metal Maker engine refueled it and the retreat cost
only 2. This deck shrugs off gust-strand lines unless the target is the Mega.

Ladder ledger: 32–26.

---

## 2026-08-22 · vs `eoja-iii` (Slowking toolbox / Mega Kangaskhan draw engine) · **WIN by concession (3–0 prizes)**

Turn-4 race win: Precious Trolley into full bench, double Metal Maker loading
Drilbur to 5 Energy in one turn, and Maximum Drilling's 330 KO'd the fresh
Mega Kangaskhan ex (300 HP, 30 overkill) — 3 prizes on the first attack of the game. They
rebuilt (second Kangaskhan, Boomerang Energy on Slowking, Prime Catcher
stranding our Metang), then drew 8 off Lillie's and conceded mid-combo —
reading between the lines: the Seek Inspiration engine had nothing worth
copying and the prize race was unwinnable at 0–3 down against a loaded board.
The Prime Catcher strand didn't matter for the same reason it didn't vs
SawyerOverweg: Metal Maker refuels whoever gets dragged up.

Ladder ledger: 33–26.

---

## 2026-08-22 · vs `Fmz1822` (Slowking toolbox / Mega Kangaskhan) · **LOSS 1–6**

Parser: 227/227 (100%), zero unresolved. New end-condition shape handled
("Opponent Knocked Out all your Pokémon in play...").

The full Slowking toolbox, piloted well, and the game was decided on THEIR
TURN 2: Academy at Night plant -> Seek Inspiration -> **Trifrost off a
discarded Kyurem** hit both Beldum (110 each, dead) and the 1-Energy Drilbur
(dead) — three bench KOs, 3 prizes, the Mega line's entire early board gone
in one attack. Ten turns of topdeck recovery followed (four consecutive
draw-pass turns), a Protect Charge KO on one Slowking, and then the indignity:
their Slowking copied **our own Metallic Hammer** (Seek-discarding the
Metagross they run as fodder) through Protect Charge for the 300 KO on
Genesect. Closed with a second Trifrost. They also showcased Lucky Helmet,
Wondrous Patch, Telepathic Psychic Energy — the modern toolbox shell.

**The lesson is the same as the Zygarde game, and it now has three data
points: the house list has no answer to turn-2/3 bench wipes.** Trifrost
(this game), Nullifying Zero (KinooThePro), Phantom Dive chip (Alamo789) all
convert our own development — a bench of 60-100HP pieces holding Energy —
into multi-prize turns. `mega_excadrill_shaymin` EXISTS for exactly this
(Flower Curtain blanks Trifrost's bench halves and Nullifying Zero entirely);
it was built after the original ladder Slowking losses and we keep not
playing it into the matchup it answers.

**Sim-calibration note (honest ledger):** the matrix says mega_excadrill
beats `slowking` 75% and `slowking_annihilape` 80%. Real Slowking-toolbox
record vs this pilot: 0–3 lifetime (two pre-corpus losses that spawned the
counter-build, now this). The sim's Slowking cells are POLICY FLOORS on the
opposing side — mcts2 cannot pilot Academy-at-Night top-deck planning, so
those 75-80% numbers measure a lobotomized Slowking. Treat the real matchup
as unfavorable for the house list until the Shaymin variant gets ladder reps.

Ladder ledger: 33–27.

---

## 2026-08-22 · vs `cak4597` (Mega Absol Box / Pecharunt) · **WIN by timeout (3–0 prizes)**

Parser: 116/116 (100%), zero unresolved — Mega Absol ex IS in the pool (the
rank-23 archetype, 1.15% live share, first ladder sighting). Honest ledger:
they lagged all game (one full timeout mid-turn before the end), so this is a
soft win — but the board state was real: 3–0 up, Mega loaded, second Metagross
online.

One sequence worth keeping — the **Air Balloon double-promote**: Petrel
fetched Air Balloon, attached to the ACTIVE Metang, free-retreated into the
benched fueled Metang, evolved it to Metagross, Hammer 300 = 3-prize KO on
Mega Absol ex. The Balloon turned a stranded Active into attacker selection —
that's the card earning its 1-of slot in a way the sim's pilot never finds.

Third Pecharunt/Subjugating-Chains sighting (self-gust + self-poison engine).
The Absol box leans on Munkidori chip relocation like Ramukaka22's build; a
KO'd 4-Energy Mega Absol before it ever attacked was the whole game.

Ladder ledger: 34–27.
