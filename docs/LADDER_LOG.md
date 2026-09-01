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

---

## 2026-08-23 · vs `VagMonstro` (Dragapult Blaziken) · **LOSS 0–3 (benched out)**

First game on `mega_excadrill_shaymin` — and it produced ZERO data on the
Flower Curtain question, because the game was a consistency brick, not a
matchup: mulligan (7 cards, zero Basics), then a game in which only THREE
Basics ever surfaced (3 Beldum). The Petrel/Transceiver engine can only fetch
Trainers, so the dig never found bodies; lost by bench-out with 0 prizes
taken. New end-condition shape parsed ("Knocked Out with no Benched
Pokémon"), 156/156 lines, zero unresolved — including Risky Ruins, a Stadium
already in the pool, first ladder sighting.

Pilot's own read: "shit draw, wouldn't have mattered." Largely true — turn-3
Blaziken 400 through Fire Weakness onto a Beldum is unanswerable from a
bricked board. One marginal note for the record: the turn-4 Ultra Ball
(discarding Metagross + Energy) fetched a second Metang while one was already
in hand; Genesect ex (draw engine + a 220HP body in a bench-out loss) or
Shaymin was the higher-value fetch. It buys a turn, probably not the game.

Matchup ledger: Dragapult Blaziken is now 0–2 lifetime in real games (sim:
63% favored) — but n=2 with one brick; not yet a calibration finding the way
Slowking's 0–3 is. Their build showcased the Blaziken/Munkidori/Risky Ruins
version — Seething Spirit recovering the retreat discard exactly as the
implementation notes predicted.

Ladder ledger: 34–28.

---

## 2026-08-23 · vs `Orlando314` (Mega Greninja / Mega Starmie water box) · **WIN by concession**

**THE CURTAIN FIRED.** First live datapoint for the variant's whole thesis,
verbatim from the client:

    Orlando314's Mega Starmie ex used Jetting Blow on Goatest1's Metagross for 120 damage.
    Goatest1's Shaymin used Flower Curtain.
    - Damage to Metang was prevented.

Jetting Blow's bench splash hit the Curtain and died. The opponent's damage
output for the whole game: 120 to an Active Metagross and two Itchy Pollens
(one blanked by Grass Resistance). They conceded facing double Metagross +
loaded Mega with two damaged Starmie on their side.

Other notes: double-Shaymin opening kept (correct — one Active as a safe
starter, one benched for the Curtain, and the Active later retreated out);
turn-2 Gravity Mountain denied the Stadium slot all game; the Boss's +
Metallic Hammer 300 onto a benched Mega Starmie ex (310 HP — survived by 10)
forced their concession math anyway. The variant's first clean game is a
proof-of-mechanism, not yet proof-of-matchup: this was a water box, not the
Slowking toolbox the experiment is really about.

Ladder ledger: 35–28 (Shaymin variant: 1–1, the loss being a no-data brick).

---

## 2026-08-23 · vs `JackoTheClown` (Dragapult / Munkidori / Yveltal disruption) · **WIN by concession, 5–0 prizes**

Variant record 3–1 (2–1 in games with data). Their disruption gauntlet — 2×
Team Rocket's Watchtower, Special Red Card, 2× Boss's Orders, 3× Crushing
Hammer (all three tails) — all failed against the engine's redundancy: Petrel
chains rebuilt every stripped hand, Metal Maker re-fueled every gust-strand,
and the second Gravity Mountain answered the Stadium war.

**Two findings for the variant ledger:**
1. **The Curtain's honest limit, demonstrated live: Phantom Dive's counters
   went THROUGH it** (6 counters onto our benched Metagross). Correct per card
   text — Flower Curtain prevents *damage*; placed counters are an effect, not
   damage (engine boundary verified: Curtain lives in apply_attack_damage,
   not place_counters). The variant blanks Trifrost/Nullifying Zero/Jetting
   Blow splash; it does NOT blank Dragapult spread. Battle Cage is the
   counters answer, and nobody's list runs it.
2. **Client owner-mislabel bug, two more instances** (Finding 3, TCGLIVE
   fidelity report): Adrena-Brain "moved 3 counters to JackoTheClown's Mega
   Excadrill ex" and Phantom Dive "put 6 counters on JackoTheClown's
   Metagross" — both destinations are OURS.

**Pilot's question — the deck-out line:** they noticed (half-asleep) the
opponent could be decked out. The instinct is sound and the ASYMMETRY is the
real insight: their build drew 6–9 cards/turn (double Recon Directive, Flip
the Script, Lillie's ×3) while OUR list regrows its own deck with Energy
Recycler (used 3× this game). Mega Excadrill is nearly deck-out-proof;
draw-engine decks are not. But the sequencing was right as played: at 5–0
with Maximum Drilling KOing a 2-prizer per turn, prizes finish in ~1–2 turns
vs ~6–8 for deck-out — attack while ahead, keep deck-out as the fallback if
the attack line ever stalls. Kieran mode-2 note: the +30 vs ex was chosen on
a turn the attack targeted MUNKIDORI (non-ex) — the bonus never applied;
mode-2 only pays when the Active you're hitting is the ex.

Ladder ledger: 36–28.

---

## 2026-08-24 · vs `DuarteLLoyd20` (Mega Venusaur ex / Teal Mask Ogerpon grass ramp) · **LOSS 1–6**

New archetype, first sighting: Mega Venusaur ex (380 HP, Solar Transfer
re-arranging Grass Energy at will) + Teal Mask Ogerpon ex (Teal Dance accel,
Myriad Leaf Shower) + Meganium / Meowth ex / Fezandipiti, drawn by a
Lillie's Determination + Bug Catching Set engine. Not in the registry; only
pool gap in the whole 33-card list is **Growing Grass Energy** (313/313 log
lines parsed).

**The loss mechanism — our own Energy killed us.** Myriad Leaf Shower counts
Energy attached to BOTH Active Pokémon. The Mega Excadrill ex KO (360 vs
340 HP, margin 20) breaks down as: their 7 Energy = 210, OUR 5 Energy =
+150. Metal Maker had greedily stacked 3 extra Energy onto the Active that
same turn — without those, the shower reads 270−30 = 240 and the Mega
LIVES. Against this archetype, over-fueling the Active is literally
self-damage at 30/card. All three KOs on our side were Active OHKOs
(240/360/270); resistance −30 is a rounding error against an unbounded
scaler.

**Second mechanism, older pattern: the Energy-piñata Drilbur.** A 70 HP
Grass-WEAK Basic was left holding 6 Energy in the Active (Boss'd up, then
fed further, then attacked with Call for Family instead of retreating out)
and died to a bare Ivysaur's 60-base Razor Leaf. One prize + 6 Energy for
their leftmost attacker. Drilbur is the matchup's weak link — vs Grass,
evolve it or keep it lean.

**What was played well:** both Boss's Orders stranded the loaded Ogerpon and
dodged its attack for a turn each; Gravity Mountain bounced Forest of
Vitality and won the Stadium war; Undermine's mills hit real cards
(Meganium, a Teal Mask Ogerpon ex, Night Stretcher); Energy Recycler
regrowth kept the deck alive to the end.

**Rematch plan:** (1) LEAN ACTIVES — attack-cost Energy only on whatever is
in front; park Metal Maker surplus on benched Metagross. (2) Hunt the
Ogerpons: 210 HP, Metallic Hammer 300 OHKOs through anything, 2 prizes
each — Boss + Hammer twice is 4 prizes. (3) Don't fight the Mega Venusaur
(350 even under Gravity Mountain); it never attacked all game — it's an
engine, so starve its targets instead. (4) Shaymin data: none — this deck
has ZERO bench damage, so the Curtain is dead weight here; both experiment
questions remain open.

Ladder ledger: 36–29 (Shaymin variant: 3–2).

---

## 2026-08-24 · vs `GandalfTheBaee1` (Mega Charizard X / Oricorio ex turbo) · **LOSS 1–6**

The registry's own `charizard_xy` shell, nearly card-for-card (Oricorio ex
Excited Turbo, Battle Cage, Lillie's, Night Stretcher — theirs runs
Firebreather). Structural problem first: our ENTIRE line is Fire-weak ×2,
so Inferno X (90 per discarded Energy, then doubled) lands 510–540 and
OHKOs everything we play, including the 340 HP Mega. Three Active OHKOs,
game.

**The pilot's own diagnosis is confirmed, and the miss was bigger than the
miscount.** Final turn, the board: our Metagross ACTIVE with 5 Energy,
their Active Mega Charizard X ex sitting at 300/360 — 60 HP from dead.
Every attack Metagross owns was lethal: M Bounce Back (cost [M], 60 = exact
lethal) or Metallic Hammer (150 base, no discard even needed). That's a
3-prize KO → 4–5 and their only powered attacker off the board. Instead the
turn went: retreat Metagross (−3 Energy), promote Genesect ex on 2 Energy
believing Protect Charge was payable (it costs [M][M][C] — three), Boss the
CHARMANDER up (pulling the dying Charizard out of range), pass. Genesect
was OHKO'd for the last prize. One energy miscount converted a 3-prize
turn into zero.

**The earlier strategic fork:** the turn Metagross Hammered the fresh
Charizard for 300, Boss's Orders was in hand and Oricorio ex sat at
150/190. Boss + Hammer = KO Oricorio (2–2), killing Excited Turbo — the
engine that pays Inferno X's 3-discards-a-turn (Night Stretcher recursion
fed it all game). Hammering Charizard was defensible (it set up the lethal
that was later missed), but the engine kill was probably the stronger line
in a matchup where every one of our Pokémon dies to one attack.

**Played well:** the mulligan reveal telegraphed Mega Charizard X from turn
0; Precious Trolley built the full bench through Judge disruption; Jumbo
Ice Cream's 80 heal kept Genesect alive to trade (Protect Charge KO'd
Charmeleon); Energy Recycler kept fuel flowing after every 6-card KO
dump.

**Sim read (fresh, greedy n=200 seed 2026):** `mega_excadrill_shaymin` 68%
vs `charizard_xy` — but aggro-bias caveat applies AND greedy underplays
Inferno X's discard sequencing for the opponent, so treat 68% as
optimistic. Real games say: whoever's board comes online first wins, and
their Rare Candy + Excited Turbo setup is one turn faster than three
Metal Makers. **Shaymin data: none again** — third straight opponent with
zero bench damage; the Curtain has been dead weight in every game since
Orlando314.

Ladder ledger: 36–30 (Shaymin variant: 3–3).

---

## 2026-08-24 · vs `Dunny9901` (Mega Skarmory ex / Greninja ex / Steven's) · **WIN 6–0, flawless**

The opponent bricked — three consecutive turns of draw-pass with no play at
all — and the engine executed a textbook kill sequence into the stalled
board: Metallic Hammer (Steven's Beldum), Metallic Hammer 300 + Bounce Back
60 (Greninja ex), Maximum Drilling 330 (Mega Skarmory ex). Four attacks,
six prizes, ZERO damage taken all game. Little matchup signal in a brick,
but the sequencing was clean: bench-built two Metagross while the Active
Metang tanked nothing, and the Mega was held back until the 3-prize
Skarmory KO closed it in one hit.

**Rules moment worth keeping: Mist Energy did its job and it didn't
matter.** Bounce Back's switch effect was prevented ("Effects of Bounce
Back did not affect Greninja ex") but the 60 DAMAGE went through and
finished the 300-damaged Greninja anyway — effect shields don't stop
damage, the mirror image of the Curtain lesson (damage shields don't stop
effects). The client line was a NEW log shape; parser grammar extended
(`effect_shield`), this game re-parses 142/142, test suite still green.

**Sightings ledger:** Mega Skarmory ex is a POOL GAP (the game's only
unresolved card). Boomerang Energy appears again (second deck running it),
plus Mist Energy / Magnetic Metal Energy / Steven's Beldum — the Steven's
engine keeps showing up around Metal shells. Shaymin: benched, no data —
FOURTH straight opponent with zero bench damage.

Ladder ledger: 37–30 (Shaymin variant: 4–3).

---

## 2026-08-24 · vs `frappeman` (Mega Excadrill / Steven's Metagross ex — near-mirror) · **LOSS 0–6**

The mirror we've been theorizing about: OUR shell (Petrel/Trolley/Genesect/
Mega Excadrill) plus the Steven's package — Rare Candy into turn-2 Steven's
Metagross ex, whose X-Boot self-accelerates (they got TWO online = 2 boosts
per turn) and whose Metal Stomp does a flat 200 every turn. 176/176 lines
parsed, all 22 cards resolved — every card they played is already in our
pool.

**"Shit hand" verdict: mostly true, with one structural bleed on top.** Our
engine never arrived — no Genesect ex all game, one Petrel, no Trolley, no
Boss, no second Poffin; first real attack came on the FINAL turn while
Metal Stomp had been landing 200 since their turn 3. That tempo gulf is the
draw. But the 3-prize bleed was positional: Drilbur was evolved to Mega
Excadrill ex on turn 3 with no attack in sight, and it sat on the bench for
five turns as Boss bait — dragged up twice, KO'd for 3. Same lesson as the
Venusaur game, now twice in a row: **against Boss decks, the Mega evolves
the turn it acts, not before. Benched Drilbur risks 1 prize; benched Mega
risks 3.** Prize ledger of the loss: Beldum 1, Shaymin sac 1, Mega 3,
Metagross 1.

**The agonizing margin:** our one Metallic Hammer hit their Steven's
Metagross ex for 300 — under our own Gravity Mountain its 340 HP was
effectively 310. It survived on 10 HP and KO'd back. Ten damage — one
turn-1 Dig Claws, one Kieran — and the exchange flips.

**Defensible plays:** the Shaymin sacrifice after the retreat-out was the
right prize math (Beldum is a future Metagross; Shaymin was inert vs a
zero-bench-damage deck); Energy Recycler recovered the retreat cost;
Gravity Mountain was net-neutral-to-positive (cost them 30 effective HP,
our Metagross died to Stomp either way).

**Variant ledger, honest read at 4–4:** the Curtain has now been LIVE-
USEFUL in exactly one of eight variant games (Orlando314) and dead weight
in the rest — five straight opponents with zero bench damage, and today it
was sac fodder. The Slowking/Grimmsnarl questions it was built for remain
untested. **Meta drift note: third Steven's-package sighting TODAY** (two
in Metal shells, one dedicated). A `mega_excadrill_stevens` variant build +
house-list matchup test is flagged for the next scan cycle — the cards are
all implemented (doublade line).

Ladder ledger: 37–31 (Shaymin variant: 4–4).

---

## 2026-08-24 · vs `Birulas` (Mega Gengar ex / Gengar Mind Jack) · **WIN by concession, 4–2**

The bounce-back, and the best-piloted game of the day. Three doctrine
points executed on their first outing:
- **Mega evolves the turn it acts** — Drilbur stayed Drilbur until turn 3,
  then evolve + Maximum Drilling 330 (Haunter KO) in one motion. It went on
  to score three of our four KOs and was healed (Jumbo Ice Cream) out of
  Mind Jack range.
- **Kill the Mega while it's cold** — Boss's Orders dragged the benched
  Mega Gengar ex (1 Energy, never attacked) into Maximum Drilling. Their
  win condition died without ever acting.
- **Kieran's switch mode, first live use** — pivoted Shaymin out / loaded
  Metagross in and Hammer'd the Gastly, all in tempo.

**Rules find of the game (Finding 5, RESOLVED — pilot spotted it):** the
Mega Gengar KO awarded 2 prizes, not 3. Mega Gengar ex's Ability **Shadowy
Concealment** — a Darkness Pokémon KO'd by damage from an opponent's
Pokémon EX yields 1 fewer prize. Our Mega is an ex; our METAGROSS line
isn't. Rematch implication: route KOs through Metagross to pay full price.
The log never names the Ability — prize counts silently change, a real
constraint on the future replay harness (recorded in the fidelity report).

**Cost of the wide bench, measured:** their 1-prize Gengar's Mind Jack does
10 + 30 × OUR Bench. At 5 benched = 160, which — after THEIR Gravity
Mountain shaved our Metagross to 150 (clever: GM as an enabler against us)
— cleared two Metagross exactly. At 4 benched = 130, it stopped killing
anything. Precious Trolley's fill-the-bench opening has a real price
against Mind Jack-class scalers; second bench-width lesson of the meta
(Feather Rondo scales the same way).

Sightings: plain Gengar (Mind Jack print) is a POOL GAP; Grand Tree /
Janine's Secret Art / Grimsley's Move / Tatsugiri seen (mulligan +
Grimsley's). Shaymin: pivot duty, took 30, retreated — earned its slot as
a pivot, Curtain unused (sixth straight no-bench-damage opponent).

Ladder ledger: 38–31 (Shaymin variant: 5–4).

---

## 2026-08-24 · vs `PetePanZ` (Ethan's Typhlosion / Toucannon fire box) · **LOSS 2–6** · piloting `crustle_modern`

**Deck note: NOT the Shaymin variant** — this was the paper deck, and it is
the registry's `crustle_modern` card-for-card. That matters: this is the
FIRST LIVEFIRE GAME for the matrix's maximin champion ("no losing matchup,
floor 53.3%") — and it ran into a hard counter the matrix never modeled.
320/320 lines parsed, all 36 cards resolved: the Ethan's Typhlosion
archetype is fully in-pool but NOT in the registry.

**Why the matchup is near-unwinnable:**
1. **Crustle is Fire-weak ×2.** The wall the deck is named for died twice
   without attacking — Buddy Blast hit it for 460 and 580. Mist Energy tech
   was dead weight (Buddy Blast is pure damage, no effects to block).
2. **Buddy Blast scales on Ethan's Adventure cards in their discard**
   (60 each) and the engine self-feeds: Quilava's ability fetches an
   Adventure every turn, playing it draws 3 AND banks 60 future damage.
   It grew 110 → 460 → 580 across the game. Nothing in crustle_modern
   touches an opponent's discard.
3. **KOs don't stick.** We KO'd Typhlosion twice (Rapid-Fire Combo 450
   high-roll, then a 200 base); Sacred Ash + Rare Candy rebuilt it twice
   more. Two prizes bought zero tempo.
4. **Feather Rondo counts BOTH benches** — 8 benched = 220/turn from a
   1-PRIZE Toucannon, which is what actually killed both Kangaskhans
   (through Hero's Cape the first time). Bench-width lesson #3 this
   weekend (Mind Jack, now Rondo): our own full bench was a third of
   their damage.

**Played well:** Crushing Hammer heads bought a turn; both stall Bosses
(Fezandipiti, then Cyndaquil) were right — the second was beaten only by
a topdecked-or-held Rare Candy; the first Rapid-Fire Combo high-roll
(5 heads, 450) cashed a Typhlosion. **Debatable:** benching the second
Kangaskhan and Cornerstone Ogerpon late fed Rondo +40/turn and put a
second 3-prize body on a board we were losing.

**Calibration takeaway (important):** `crustle_modern`'s "no losing
matchup" claim is TRUE ONLY AGAINST THE MODELED 14-DECK FIELD. The live
ladder just produced a counter — discard-scaling damage through Fire
weakness — that no registry deck represents. Register the Ethan's
Typhlosion archetype next scan cycle and re-run the crustle_modern column;
its maximin crown is provisional until then.

**Client bug corpus:** Spiky Energy fired twice, owner-mislabeled BOTH
times ("Goatest1's Toucannon" / "Goatest1's Ethan's Typhlosion" — both
PetePanZ's). Finding 3 keeps growing.

Ladder ledger: 38–32 (Shaymin variant unchanged: 5–4; crustle_modern
livefire: 0–1).

---

## 2026-08-26 · vs `PNGtaytay` (Mega Lucario / Hariyama / cosmic-duo fighting box) · **LOSS 3–6 (benched out)** · piloting `crustle_modern`

crustle_modern livefire game 2, and the most instructive cell-check yet.
The matrix says crustle_modern beats `fighting` 61.7% (37–23, n=60). Live,
the fighting player won going away — because **the real build carries what
our registry list doesn't: NON-EX attackers.**

**The wall worked exactly as designed, and it didn't matter.** Mysterious
Rock Inn blanked Mega Lucario ex's Aura Jab TWICE (130 → 0, verbatim in
the log). But the deck routed every KO around it: Hariyama's Wild Press
(non-ex, 210 with self-recoil) killed three Crustles, and the closer was
Solrock's Cosmic Beam with THREE stacked Premium Power Pro (70+90 = 160)
— item-boosted non-ex burst, purpose-built anti-wall tech. Our registry
`fighting` list is ALL ex attackers (Mega Lucario ex / Regirock ex / Iron
Boulder ex): in the sim, Rock Inn blanks the whole deck, hence 61.7%. The
cell is optimistic against real builds. Same lesson as the PetePanZ game
from the other side: **crustle_modern's matrix column is inflated wherever
the modeled opponent lacks the non-ex secondary that real lists carry.**
Both livefire counters (Fire weakness; non-ex beaters) are now on record.

**Play notes.** Good: Boss + Superb Scissors on Lunatone (grass weakness,
120→240) was a clean snipe that also killed their Lunar Cycle draw; the
attrition math on Hariyama (their 140 self-recoil + our 120) cashed a KO;
the Spiky mutual-KO trade was fine. Costly: after the double-KO, promoting
Cornerstone Ogerpon ex (1 Energy, no attack that turn) into an ex-heavy
board gave Mega Brave a free 2-prize KO — promoting the benched CRUSTLE
instead blanks both their ex attackers and forces the 3-item Solrock line
a turn early. Same doctrine, third time: don't put multi-prize bodies in
front while behind. Two attach-pass turns after their Judge + Special Red
Card show the disruption bit hard; the bench was never rebuilt, which is
how a 3–6 loss ended as a simultaneous bench-out.

Sightings: Hariyama's Heave-Ho Catcher (ability gust), Ciphermaniac's
Codebreaking, Maximum Belt, Fighting Gong, Premium Power Pro stacking —
all in-pool, none in the registry `fighting` list. Registry refresh of
`fighting` toward the real Hariyama/cosmic shell joins the Ethan's
Typhlosion build on the next-cycle list.

Ladder ledger: 38–33 (Shaymin variant unchanged: 5–4; crustle_modern
livefire: 0–2).

---

## 2026-08-26 · vs `RSBKChise` (Mega Sharpedo / Toxtricity darkness turbo) · **LOSS 0–4 (benched out)** · back on `mega_excadrill_shaymin`

Fast bench-out: turn-2 Mega Sharpedo ex (Carvanha straight to Mega),
Boss + Greedy Fang picked off the energy-loaded Drilbur immediately, and
the engine never arrived — no Genesect, no Petrel/Trolley all game (same
draw shape as the frappeman loss). Shaymin never drawn: a no-data variant
game.

**The lesson worth the loss — DON'T CHIP MEGA SHARPEDO.** Hungry Jaws is
120+, and gets **+150 flat if Sharpedo has ANY damage counters on it**
(pool text confirmed). Our Metang's 60-damage Beam armed it for the rest
of the game: armed 270 one-shots Metagross (180), unarmed 120 does NOT
(and doesn't even clear our-GM-shaved 150). Chip it only with lethal in
sight (330 HP), otherwise leave it clean. Caveat on the counterplay:
their own Toxtricity (Sinister Surge) places counters on their own
Pokémon, so they can self-arm a bench Sharpedo — but making them spend
that is still better than arming the Active for free. Note the pattern
count: that's the THIRD self-feeding scaler the ladder has shown us
(Myriad Leaf Shower eats our Energy, Feather Rondo/Mind Jack eat our
bench, Hungry Jaws eats our chip damage). The doctrine generalizes:
**know what the opponent's attack scales on, and starve it.**

Also repeated: turn-1 Energy on benched Drilbur = Boss bait vs turbo
decks (Greedy Fang KO'd it for a prize + the Energy). Against decks with
a turn-2 attacker, hold the attachment or bench a second body first.

Sightings: Mega Sharpedo ex / Pecharunt ex / Toxtricity Sinister Surge —
all in pool, archetype not in registry (third unregistered archetype hit
this week). 116/116 lines parsed.

Ladder ledger: 38–34 (Shaymin variant: 5–5, no-data game; crustle_modern
livefire: 0–2).

---

## 2026-08-26 · vs `Pandabirb` (Delphox / Emboar fire toolbox) · **WIN by concession, 2–4 down** · piloting `crustle_modern`

crustle_modern's first livefire WIN (1–2) — and a strategy-defining one:
**the opponent conceded while AHEAD 4–2 on prizes**, because the board had
become unwinnable for them. Cornerstone Mask Ogerpon ex's Cornerstone
Stance prevents ALL attack damage from Pokémon that have an Ability — and
their entire engine has Abilities: Delphox (Flaring Magic), Emboar
(Inferno Fandango), Fezandipiti, Meowth ex. Their ONLY legal attacker into
the wall was a vanilla Fennekin plinking 10 a turn, and Spiky Energy made
each plink cost 20 back. Demolish (140, immune to their effects) started
cleaning: Fennekin KO, then 140 onto the gusted Fezandipiti. They ran the
math and scooped.

**The two walls cover different meta slices — this game proved the split:**
Crustle's Rock Inn blanks EX attackers but folds to Fire weakness;
Cornerstone blanks ABILITY-havers regardless of type. Vs a fire toolbox,
Cornerstone is the wall, Crustle is bait. Deck identity, sharpened.

**The bad beats and the one real error:** double mulligan (opponent +2
cards, energy-and-trainers hands — variance). The error was the FOURTH
instance of the doctrine violation: Mega Kangaskhan benched turn 3 with 2
Energy and no attack plan; Boss + Energized Storm (30 × 10 attached
Energy = 300, their whole board's Energy fed by Inferno Fandango) took 3
prizes. Every multi-prize body we bench idle keeps converting into
opponent prizes. Kanga either stays in hand or comes down the turn it
swings.

Sightings: Delphox / Emboar (Inferno Fandango!) / Max Rod / Firebreather —
all in-pool, fourth unregistered archetype this week. 230/230 lines
parsed.

Ladder ledger: 39–34 (Shaymin variant: 5–5; crustle_modern livefire: 1–2).

---

## 2026-08-27 · vs `Reecie_Puffs` (Chandelure / Comfey MILL) · **LOSS by DECK-OUT, up 2–0 on prizes** · piloting `crustle_modern`

First mill opponent in the corpus, and it beat us without taking a single
prize. The engine: up to three Chandelures' Alluring Light (both players
draw 1, each, every turn) + Comfey's Flower Shower (both draw 3) force-fed
us 4–6 cards a turn; their side is immune because Lillie's Determination
recycles their hand into their deck (they shuffled 18 back in one turn
near the end); Xerosic's Machinations then deleted the 8-card hand the
force-feeding built. We died on the draw-for-turn with 4 prizes still to
take.

**What worked:** Comfey KO'd twice (right target — the biggest drip), both
our Lillie's were played as deck-refills (7 then 12 shuffled back — the
only reason the game lasted this long). **What lost it, beyond the
matchup:** (1) OPTIONAL DRAWS ARE POISON VS MILL — Run Errand every turn
(+8 cards over the game), plus Poffin/Pokégear/Hilda/Poké Pad, all
accelerated our own clock for marginal value. Skip the draw ability unless
it finds this turn's KO. (2) The race was too slow: 2 prizes in ~12 turns,
not helped by Rapid-Fire Combo rolling 0 heads twice running (25% chance).
(3) Strategic shape: A WALL DECK PLAYS INTO MILL — walls win slow, mill
wins slower games harder. Versus mill the correct crustle_modern posture
is pure race: every turn spent stalling compounds their engine, and their
board was tissue (Comfey/Maractus/Chandelure, all 1-prize).

**Deck-audit note:** the JackoTheClown doctrine ("Mega Excadrill is nearly
deck-out-proof") does NOT transfer — crustle_modern is draw-heavy with no
Energy-Recycler-style shuffle-back, making mill its THIRD documented
livefire predator (fire weakness, non-ex beaters, now mill). The maximin
crown keeps shrinking against the unmodeled field.

Sightings: **Mega Chandelure ex is a POOL GAP** (4th this week, joining
Growing Grass Energy / Mega Skarmory ex / Mind Jack Gengar); Telepathic
Psychic Energy, Xerosic's Machinations, Comfey, Maractus all in-pool.
Fifth unregistered archetype this week. 268/268 lines parsed.

Ladder ledger: 39–35 (Shaymin variant: 5–5; crustle_modern livefire: 1–3).

---

## 2026-08-27 · vs `AyItzTorch` (Vivillon / Decidueye ex grass disruption) · **WIN by concession, 2–1** · piloting `crustle_modern`

The matchup crustle_modern was BUILT for, played out exactly as designed
(livefire 2–3). Their deck: Vivillon Blow Through (120/turn) + Grand Wing
hand-shredding (our hand bottom-decked TWICE), Decidueye ex + Maximum
Belt as the closer, Judge ×2 on top. And the walls answered everything:

- **Rock Inn's showcase moment: Crushing Arrow 240 → 0.** Decidueye ex is
  an ex; Mysterious Rock Inn blanked the Maximum-Belt-boosted hit
  entirely. Note the boundary AGAIN, this time our way: the attack's
  EFFECT still discarded our Spiky Energy — walls stop damage, never
  effects. Both directions of that rule are now in the corpus.
- **The attrition trade favored us:** their Vivillons die to one Superb
  Scissors (120) while our Caped Crustle needed three Blow Throughs. Two
  Vivillons KO'd; when the second fell they were out of set-up line
  (Spewpa forced Active) and conceded at 2–1 with their only real
  attacker permanently walled.

**Survival notes:** mulligan again (variance), Judge ×2 + Grand Wing ×2
shredded the hand all game — the deck's own Lillie's density (played 3)
kept restoring function; Boss stranding Decidueye out of the Active reset
their tempo a full turn.

Sightings: **Decidueye ex is a POOL GAP** (5th this week), Growing Grass
Energy seen AGAIN (still a gap — 3rd sighting, promote to top of the
manual_cards queue). 291/291 lines parsed.

Ladder ledger: 40–35 (Shaymin variant: 5–5; crustle_modern livefire: 2–3).

---

## 2026-08-27 · vs `REYBAD` (Empoleon ex / Snorlax stall-tank box) · **LOSS 0–6** · piloting `crustle_modern`

Livefire 2–4, zero prizes taken, and this opponent — knowingly or not —
packed the complete anti-Crustle toolkit:
1. **Grass Resistance on the main tank.** Empoleon ex (320 HP, healing
   twice via Jumbo Ice Cream) takes Superb Scissors at 120−30 = 90/turn.
   The mono-attack problem in one number: our whole offense was 90 chip
   into a self-healing 320.
2. **A non-ex beater the walls can't stop — again.** Snorlax's Collapse
   160 one-shot THREE Crustles (140 HP), its self-sleep drawback erased by
   two heads flips and a Jumbo heal. Fourth non-ex-beater loss pattern
   (Hariyama, Solrock, now Snorlax).
3. **Boss + Iron Feathers 210×2** took the Mega Kangaskhan for 3 —
   the recurring Kanga-as-Boss-magnet cost, though this time it was a
   forced trade-off: Kanga IS the draw engine, benching it isn't optional.

**The card that would have mattered never showed:** Empoleon ex has an
Ability (Emperor's Stance) — Cornerstone Stance walls it completely. We
never drew Cornerstone all game. With it, their ONLY wall-breaker is
Snorlax and the game is a real fight. Draw variance, but also a list
question: 1 Cornerstone in 60 is thin for how load-bearing it's proven
(the Pandabirb game was won by it alone).

**Print-collision find (Finding 2 strikes again):** the pool's bare
"Snorlax" is the Lazy Press 120 print — the ladder's Snorlax used
**Collapse 160**. Different print, unpooled. Queue "Snorlax (<set>)" for
manual_cards alongside Growing Grass Energy / Mega Skarmory ex / Mind
Jack Gengar / Mega Chandelure ex / Decidueye ex.

Ladder ledger: 40–36 (Shaymin variant: 5–5; crustle_modern livefire: 2–4).

---

## 2026-08-30 · vs `leoNardocruz000` (Team Rocket's Honchkrow / Porygon-Z box) · **WIN 6–4** · piloting `crustle_modern`

Livefire 3–4, and Mega Kangaskhan's best recorded game: FIVE consecutive
Rapid-Fire Combo KOs (Porygon, Murkrow, Honchkrow, Honchkrow, Porygon2),
with Crustle's Superb Scissors closing the sixth. The structural reason it
worked: **their board was all 1-prize Rockets**, so 200-a-turn cleared one
body per turn and the prize race was never in doubt — the aggro-into-
fodder matchup is where this deck's Kanga plan actually shines.

**The Kanga paradox, resolved by this game:** every prior loss featured
Kanga as a benched Boss-magnet. Here it OPENED Active — draw engine and
attacker in the same body from turn 0, Cape/Mist/Spiky loaded, Run Errand
every turn while attacking. When it finally fell (3 prizes) the ledger
read 5 KOs for 3 — a trade worth taking every time. Doctrine refinement:
Kanga either OPENS Active or waits in hand; the bad pattern is
specifically mid-game benching.

**Respect the burst that killed it:** Team Rocket's Honchkrow's Rocket
Feathers does 60 × Team Rocket's cards discarded from the attacker's
hand — they dumped SEVEN (both Giovannis, both Protons, both Archers, an
Ariana) for 420 through Cape. It's a hand-emptying nuke: the first
Honchkrow could only afford 3 (180). After the big one their engine was
spent, and the last Honchkrow died to Superb Scissors holding nothing.

Sightings: the ENTIRE Team Rocket box — Honchkrow line, Porygon2's R
Command (20 × cards in own discard), Porygon-Z, Articuno, Giovanni's
double-switch, Roto-Stick, Ignition Energy — is ALREADY FULLY IN POOL
(the TR engine overlaps mega_excadrill's search package). Sixth
unregistered archetype of the stretch, and the cheapest to build. Their
Team Rocket's Factory fired 5 times — the Stadium our engine already
implements.

Ladder ledger: 41–36 (Shaymin variant: 5–5; crustle_modern livefire: 3–4).

---

## 2026-09-01 · vs `JJ-Zacian` (Mega Excadrill w/ Skarmory + Cape/Jumbo tech) · **LOSS 3–6 (benched out)** · piloting `crustle_modern`

Beaten by the house archetype from the wrong side of the table — their list
is our `mega_excadrill` plus tech we've been cataloging all week (Hero's
Cape on a Drilbur, Jumbo Ice Cream ×2 healing 160 off the Mega, a Mega
Skarmory ex in the 60). Matrix says this pairing is a near-coinflip
(crustle_modern 53.3% — its FLOOR cell, n=60); the live game was decided
by three compounding factors:

1. **TRIPLE mulligan** — opponent started with a 10-card hand and a
   4-Pokémon board vs our lone Kangaskhan. Worst start of the logged
   corpus.
2. **The Kanga chip-war error (the one real lesson):** Kanga sat Active
   eating FOUR Undermines (90 × 4 = 360 > 300 HP) while drawing. But
   Undermine comes off an EX — Mysterious Rock Inn blanks it to ZERO, as
   the log later shows verbatim, twice. The moment the first Crustle stood
   up, retreating the damaged 3-prizer behind the wall turns their entire
   Active's output off. New doctrine line: **vs ex-attacker decks, the
   wall isn't just a wincon — it's the Mega's bodyguard.** Undermine's
   mill (2/turn off our deck: both Hammers, Spiky, Mist, a Lillie's) was
   the quieter half of that bleed.
3. **The non-ex beater, FIFTH instance — and it's OUR tech.** Their
   1-prize Metagross Hammer'd two Crustles (150 > 140) exactly the way we
   told the pilot to route KOs around Shadowy Concealment on 08-27. The
   house archetype carries the anti-Crustle answer innately: ex blanked by
   Rock Inn, so the non-ex Metagross does the wall-breaking.

**Played well:** doctrine held everywhere else — Kanga OPENED Active per
the 08-30 refinement and traded 2-for-position early (Boss + Rapid-Fire
300 assassinated Genesect); Kanga #2 got the Cape BEFORE fronting and
survived Metallic Hammer 300 at 400 effective, KOing Metagross back;
both walls blanked every Undermine aimed at them. The 3–6 line understates
how close the middlegame was.

293/293 lines parsed; the one unresolved card is Mega Skarmory ex — the
known pool gap, now sighted in a SECOND deck. Ladder ledger: 41–37
(Shaymin variant: 5–5; crustle_modern livefire: 3–5).
