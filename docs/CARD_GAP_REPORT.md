# Card-Implementation Gap Report — Dragapult ex & Mega Charizard X ex

**Purpose:** Scope the validation milestone. For each card in two current top Standard
lists, determine whether its non-trivial effects are implemented in
`src/engine/effects.py` (`ATTACK_EFFECTS` / `ABILITY_EFFECTS` / `TRAINER_EFFECTS`).
**Nothing is implemented here — this is the scope, not the work.**

## Sources

| Deck | Source | Player / Event | Date pulled |
|------|--------|----------------|-------------|
| Dragapult ex (Dusknoir variant) | limitlesstcg.com/decks/284 → /decks/list/27610 | Justin Newdorf — 3rd, Regional Indianapolis IN | list dated **May 30, 2026**; pulled **2026-06-02** |
| Mega Charizard X ex (X/Y toolbox) | play.limitlesstcg.com → tournament/…/khaine/decklist | Khaine — 3rd of 21, Ling TV ARENA (online) | **May 2026** (post-rotation); pulled **2026-06-02** |

> **Deck 2 was re-pulled.** The original Feb-2026 Regional list was a *pre-rotation* build
> (its OBF Charizard/Pidgeot engine is mark G, rotated out). It has been **replaced** with a
> current, all-legal (mark H/I/J) post-rotation list — a Mega Charizard **X/Y** toolbox. The
> superseded list is preserved in §A only as the cautionary note about validating illegal decks.

Card text verified against the project's own `data/standard_pool.json` where present;
cards absent from the pool were confirmed via limitlesstcg.com / pkmncards.com card pages.

## Status definitions (per the honesty rules requested)

- **implemented** — the effect's *meaningful* behavior is written in a registry **and**
  (per the project's validation rule) tested. Vanilla secondary attacks on these cards
  are fine and don't change the status.
- **vanilla-ok** — a plain attacker (attack deals damage, no rules text) or a basic
  Energy. Genuinely needs **no code**. Kept strictly separate from "implemented."
- **needs-effect** — **any** meaningful line of the card's text is unimplemented, even
  if the card name appears elsewhere or one of its two attacks is trivial. A
  half-implemented card is inert where it matters and is counted here, not as done.

---

## ⚠️ Read this before the tables — two gaps the per-card status can't show

The per-card "needs-effect" count understates the real distance to a faithful sim,
in two ways:

### A. Cards absent from the engine's card pool (a data-layer blocker, *separate* from effects.py)

These cards aren't in `data/standard_pool.json` at all, so the engine can't even load
them today — independent of whether an effect is written:

- **Dragapult list:** Meowth ex, Poké Pad.
- **Mega Charizard X/Y list (current):** Mega Charizard Y ex (ASC), Poké Pad (POR).

Both current lists are **fully mark H/I/J and Standard-legal** — the data gap is now small
and is pure pool-snapshot incompleteness, not rotation: just 3 distinct cards (Meowth ex,
Poké Pad, Mega Charizard Y ex) need adding to `standard_pool.json` before the engine can
load them. (Basic Fire/Psychic/Darkness Energy also show as "absent" but are injected by
the loader — no action.)

**Cautionary note (the superseded Deck 2):** the *first* Mega Charizard X list pulled was a
Feb-2026 Regional build whose entire engine — **Charizard ex, Pidgey, Pidgeotto, Pidgeot ex
(all Obsidian Flames, mark G)** — has since **rotated out**, exactly as CLAUDE.md warns. The
pool holds only marks **H/I/J**, so that list can't be built today. It's recorded here only
as the reason to always check the current legal pool before scoping a deck — validating it
would have validated an illegal deck. The current X/Y list above replaces it.

### B. Engine subsystems several effects depend on (infra, not registry entries)

Some effects can't be faithful as a lone registry function — they need mechanics the
engine must own first. Writing the registry entry without these is the "looks 80% done"
trap:

- **Special Conditions / status:** Confusion (Munkidori — Mind Bend), "can't retreat"
  (Dusknoir — Shadow Bind), "can't play Items next turn" (Budew — Itchy Pollen).
- **Self-KO abilities + the counter to them:** Cursed Blast (Dusclops/Dusknoir) place
  counters then KO the user; **Psyduck — Damp** specifically *disables* self-KO abilities.
  Needs an ability-granting/-suppression layer, not just two functions.
- **Stadiums:** Team Rocket's Watchtower, Battle Cage. **Battle Cage prevents damage
  counters on Benched Pokémon from the opponent's attack/ability effects — it directly
  neuters Phantom Dive's spread and Cursed Blast.** This is a live cross-deck interaction
  in *this very matchup*; without it the Dragapult-vs-Charizard number is wrong.
- **Pokémon Tools:** Air Balloon (retreat −2, passive), Powerglass (end-of-turn trigger),
  Technical Machine: Evolution (grants an attack to its holder).
- **Trigger hooks:** on-evolve (Charizard ex — Infernal Reign), on-bench-from-hand
  (Meowth ex — Last-Ditch Catch).
- **MEGA / Tera Pokémon rules:** **Mega Charizard X ex** is a *MEGA* Pokémon ex — even
  though Inferno X is implemented and in the registry, the card is **not faithful** until
  the engine models the MEGA evolution mechanic and its **3-prize** KO value.
  **Dragapult ex** is a *Tera* Pokémon — Tera prevents all attack damage to it **while
  Benched**; Phantom Dive being coded does not make Dragapult ex itself faithful until
  Tera is modeled. Both are flagged `implemented*` below with this asterisk.
- **Coin flips** (Crushing Hammer) and the **ACE SPEC one-per-deck rule** (Unfair Stamp,
  Precious Trolley).

---

## Deck 1 — Dragapult ex (Dusknoir variant) · Newdorf, Indianapolis 3rd

### Pokémon (21)

| Card | # | Status | Effect text to implement |
|------|---|--------|--------------------------|
| Dreepy | 4 | vanilla-ok | Petty Grudge / Bite — no text. (Basic evolution fodder.) |
| Drakloak | 4 | **implemented** | Ability *Recon Directive* (dig 2, take 1) — in `ABILITY_EFFECTS`. Dragon Headbutt vanilla. |
| Dragapult ex | 3 | implemented\* | *Phantom Dive*: 200 + put 6 counters on opp Bench — in `ATTACK_EFFECTS`. \*Tera rule (no damage while Benched) not modeled. |
| Duskull | 2 | needs-effect | *Come and Get You*: put up to 3 Duskull from discard onto your Bench. |
| Dusclops | 2 | needs-effect | Ability *Cursed Blast*: put 5 damage counters on 1 of opp's Pokémon; then this Pokémon is KO'd. |
| Dusknoir | 1 | needs-effect | Ability *Cursed Blast*: put **13** counters on 1 opp Pokémon, then self-KO. **+** *Shadow Bind*: 150; Defending Pokémon can't retreat next turn. |
| Fezandipiti ex | 1 | needs-effect | Ability *Flip the Script*: if any of your Pokémon were KO'd last turn, draw 3 (max 1/turn). **+** *Cruel Arrow*: 100 to any 1 opp Pokémon (no W/R on Bench). |
| Munkidori | 1 | needs-effect | Ability *Adrena-Brain*: if Darkness attached, move up to 3 damage counters from 1 of your Pokémon to 1 opp Pokémon. **+** *Mind Bend*: 60, opp Active now Confused. |
| Budew | 1 | needs-effect | *Itchy Pollen*: 10; opp can't play Item cards from hand next turn. |
| Meowth ex | 1 | needs-effect | Ability *Last-Ditch Catch*: when played from hand to Bench, search deck for a Supporter → hand (once/turn). *(Also absent from pool — see §A.)* |
| Moltres | 1 | needs-effect | *Fighting Wings*: 20+; if opp Active is a Pokémon ex, +90 damage. |

### Trainer (31)

| Card | # | Status | Effect text to implement |
|------|---|--------|--------------------------|
| Lillie's Determination | 4 | needs-effect | Shuffle hand into deck, draw 6 (draw 8 instead if you have exactly 6 Prizes remaining). |
| Boss's Orders | 3 | **implemented** | Gust a Benched opp Pokémon to Active — in `TRAINER_EFFECTS`. |
| Crispin | 3 | needs-effect | Search deck for 2 Basic Energy of different types; attach 1 to a Pokémon, put the other into hand. |
| Dawn | 1 | needs-effect | Search deck for a Basic, a Stage 1, **and** a Stage 2 Pokémon, put all into hand, shuffle. |
| Buddy-Buddy Poffin | 4 | **implemented** | Search up to 2 Basic Pokémon with ≤70 HP → Bench — in `TRAINER_EFFECTS`. |
| Poké Pad | 4 | needs-effect | Search deck for a Pokémon that doesn't have a Rule Box → hand, shuffle. *(Also absent from pool — §A.)* |
| Ultra Ball | 4 | needs-effect | Discard 2 cards from hand; search deck for any Pokémon → hand, shuffle. |
| Crushing Hammer | 3 | needs-effect | Flip a coin; if heads, discard an Energy from 1 of opp's Pokémon. *(Needs coin-flip primitive.)* |
| Night Stretcher | 2 | needs-effect | Put a Pokémon **or** a Basic Energy from your discard → hand. |
| Unfair Stamp | 1 | needs-effect | ACE SPEC. Playable only if one of your Pokémon was KO'd last turn: each player shuffles hand into deck; you draw 5, opponent draws 2. |
| Team Rocket's Watchtower | 2 | needs-effect | Stadium. *(Needs Stadium framework; exact text to confirm at impl time.)* |

### Energy (8)

| Card | # | Status | Effect text to implement |
|------|---|--------|--------------------------|
| Fire Energy | 4 | vanilla-ok | Basic Energy — injected by loader, no code. |
| Psychic Energy | 3 | vanilla-ok | Basic Energy — no code. |
| Darkness Energy | 1 | vanilla-ok | Basic Energy — no code. (Also "fuels" Munkidori's Adrena-Brain gate.) |

**Deck 1 tally:** implemented 3 cards · vanilla-ok 4 cards · **needs-effect 14 cards → 20 distinct new effect functions** (Dusknoir, Fezandipiti, Munkidori each contribute 2).

---

## Deck 2 — Mega Charizard X/Y ex toolbox · Khaine, Ling TV ARENA 3rd (May 2026, post-rotation)

### Pokémon (16)

| Card | # | Status | Effect text to implement |
|------|---|--------|--------------------------|
| Dunsparce (TEF) | 3 | needs-effect | *Dig*: 30; flip a coin — if heads, during opp's next turn prevent all damage & effects of attacks done to this Pokémon. (Mainly Dudunsparce fodder; Dig low-priority. Needs coin flip.) Gnaw vanilla. |
| Dudunsparce (TEF) | 2 | needs-effect | Ability *Run Away Draw*: once/turn draw 3; if you drew any, shuffle this Pokémon **and all attached cards** into your deck. (Core draw engine.) Land Crush vanilla. |
| Charmander (PFL) | 3 | needs-effect | Ability *Agile*: if no Energy attached, no Retreat Cost. (Passive; minor — needs retreat-modifier layer.) Live Coal vanilla. |
| Charmeleon (PFL) | 1 | vanilla-ok | Steady Firebreathing 40 — no text. |
| Mega Charizard X ex (PFL) | 2 | implemented\* | *Inferno X*: discard any # Fire Energy, 90× per discard — in `ATTACK_EFFECTS`. \*MEGA mechanic + 3-prize rule not modeled. |
| Mega Charizard Y ex (ASC) | 1 | needs-effect | *Explosion Y*: discard 3 Energy from this Pokémon; 280 to 1 of opp's Pokémon (no W/R on Bench). *(Absent from pool — §A.)* |
| Oricorio ex (PFL) | 2 | needs-effect | Ability *Excited Turbo*: as often as you like, if a Fire MEGA ex is in play, attach a Basic Fire Energy from hand to a Benched Fire Pokémon. Fire Wing vanilla. |
| Fezandipiti ex (ASC) | 1 | needs-effect | Same as Deck 1 — Ability *Flip the Script* **+** *Cruel Arrow*. |
| Fan Rotom (SCR) | 1 | needs-effect | Ability *Fan Call*: once on your first turn, search deck for up to 3 Colorless Pokémon with ≤100 HP → hand. **+** *Assault Landing*: 70, but does nothing if no Stadium in play. |

### Trainer (33)

| Card | # | Status | Effect text to implement |
|------|---|--------|--------------------------|
| Hilda (WHT) | 3 | needs-effect | Search deck for an Evolution Pokémon **and** an Energy card → hand, shuffle. |
| Lillie's Determination (MEG) | 3 | needs-effect | Same as Deck 1 (shuffle hand, draw 6 / 8 at 6 prizes). |
| Dawn (PFL) | 3 | needs-effect | Search deck for a Basic, a Stage 1, **and** a Stage 2 Pokémon → hand, shuffle. *(Shared with Deck 1.)* |
| Judge (POR) | 2 | needs-effect | Each player shuffles their hand into their deck and draws 4 cards. |
| Boss's Orders (MEG) | 2 | **implemented** | Gust — in `TRAINER_EFFECTS`. |
| Rare Candy (MEG) | 3 | **implemented** | Skip Stage 1 onto an in-play Basic — in `TRAINER_EFFECTS`. |
| Poké Pad (POR) | 3 | needs-effect | Search deck for a Pokémon that doesn't have a Rule Box → hand, shuffle. *(Shared with Deck 1; absent from pool — §A.)* |
| Buddy-Buddy Poffin (TEF) | 2 | **implemented** | Search up to 2 Basic Pokémon ≤70 HP → Bench — in `TRAINER_EFFECTS`. |
| Energy Retrieval (SVI) | 2 | needs-effect | Put up to 2 Basic Energy from your discard → hand. |
| Night Stretcher (ASC) | 2 | needs-effect | Same as Deck 1 (a Pokémon **or** Basic Energy from discard → hand). |
| Ultra Ball (MEG) | 2 | needs-effect | Same as Deck 1 (discard 2; search any Pokémon → hand). |
| Switch (MEG) | 1 | needs-effect | Switch your Active with 1 of your Benched Pokémon. |
| Air Balloon (ASC) | 1 | needs-effect | Tool: holder's Retreat Cost is −2. (Passive Tool modifier.) |
| Powerglass (SFA) | 1 | needs-effect | Tool: end of turn, if holder is Active, attach a Basic Energy from discard to it. (Needs end-of-turn Tool trigger.) |
| Battle Cage (PFL) | 3 | needs-effect | Stadium: prevent all damage counters placed on Benched Pokémon (both players) by the **opponent's** attack/ability effects. **Directly counters Phantom Dive & Cursed Blast.** |

### Energy (11)

| Card | # | Status | Effect text to implement |
|------|---|--------|--------------------------|
| Fire Energy (MEE) | 10 | vanilla-ok | Basic Energy — injected by loader, no code. |
| Enriching Energy (SSP) | 1 | needs-effect | Special Energy (ACE SPEC): provides Colorless; **when attached from hand, draw 4 cards**. (Needs Special-Energy + on-attach-trigger support.) |

**Deck 2 tally:** implemented 3 cards (+1 implemented\*) · vanilla-ok 2 cards · **needs-effect 11 cards → 22 distinct new effect functions** (Fezandipiti & Fan Rotom each contribute 2). Cleaner list than Deck 1: only 1 ACE SPEC, every card legal.

---

## Summary — total new effects to make both lists fully faithful

**35 distinct new effect functions** across the two current lists (after de-duplicating the
7 shared: Fezandipiti's *Flip the Script* + *Cruel Arrow*, Lillie's Determination, Dawn,
Poké Pad, Ultra Ball, Night Stretcher).

| Bucket | Distinct effects |
|--------|-----------------:|
| Pokémon abilities & attacks | **18** |
| Trainers (Items / Supporters / Stadiums / Tools) | **16** |
| Special Energy | **1** |
| **Total distinct new effects** | **35** |
| Deck 1 (Dragapult) alone | 20 |
| Deck 2 (Charizard X/Y) alone | 22 |
| Shared between decks | 7 |

**Already done (relevant to these lists):** Phantom Dive, Inferno X, Recon Directive,
Rare Candy, Buddy-Buddy Poffin, Boss's Orders. (Registry also holds Raging Bolt ex,
Teal Mask Ogerpon ex, Cheren — not used by either list.)

### These 35 are necessary but **not sufficient**. Blocking prerequisites:

1. **Data layer:** 3 distinct cards are missing from `standard_pool.json` and can't be
   loaded at all — Meowth ex & Poké Pad (Dragapult), Mega Charizard Y ex & Poké Pad
   (Charizard). Add them to the snapshot before effects. *(Both lists are otherwise fully
   mark H/I/J and legal — see §A. Swapping to the post-rotation Charizard X/Y list removed
   the earlier 13-card rotation/data hole.)*
2. **Engine subsystems** (block whole groups of the 35): Special Conditions
   (Confusion / no-retreat / Item-lock), self-KO + ability-suppression (Cursed Blast vs
   Damp), Stadiums (Battle Cage's bench-damage prevention is live in *this* matchup),
   Pokémon Tools, on-evolve / on-bench / first-turn triggers, coin flips, Special Energy
   (Enriching Energy), ACE SPEC singleton rule, and the **MEGA + Tera** mechanics — without
   which Mega Charizard X ex and Dragapult ex themselves are not faithful even though their
   attacks are coded.

**Honest headline for milestone planning:** across the two current lists there are ~26
distinct *non-vanilla* cards; **6 are implemented** and **~20 need work** (effect, data, or
both). The two namesake attackers are coded but each carries an unmodeled core mechanic
(Mega Charizard X ex — MEGA prize count; Dragapult ex — Tera bench-immunity), and the
single most matchup-relevant card — **Battle Cage** (3 copies in the Charizard list) — sits
behind a Stadium framework that doesn't exist yet and directly cancels Phantom Dive's
spread. This is closer to the *start* of the validation milestone than the middle, but the
post-rotation swap meaningfully shrank the data hole (13 → 3 missing cards).
