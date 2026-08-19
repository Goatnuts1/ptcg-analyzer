#!/usr/bin/env python3
"""
effects.py — the effect scripting system. This is the project's hard core.

THE DESIGN (hybrid, as agreed):
  - A small library of reusable PRIMITIVES for the patterns that recur across
    hundreds of cards (deal damage to bench, draw, heal, discard from deck,
    dig N and pick one, ...).
  - A REGISTRY mapping a specific card's attack/ability to a hand-written effect
    function, which composes primitives. Gnarly one-off cards get bespoke Python.
  - Effects receive an EffectContext and mutate game state directly.

WHY THIS SHAPE: card text is unbounded and irregular, so we do NOT try to parse
arbitrary English. We hand-write the ~150-300 cards that actually appear in the
meta, leaning on primitives so each entry is a few lines. This is the same
strategy TCG ONE uses. It's the honest, maintainable path.

VALIDATION RULE: every effect added must have a test asserting it does exactly
what the card text says. A wrong effect silently corrupts every win rate that
touches that card. effects without tests are not trusted.

DAMAGE COUNTERS: in the TCG, 1 damage counter = 10 damage. "6 damage counters"
= 60 damage, placed in 10-point chunks.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable, Optional

from .state import GameState, InPlayPokemon, PlayerState


@dataclass
class EffectContext:
    """Everything an effect needs to do its job.

    `source` is optional (Trainer effects have no source Pokemon). `target` lets
    an effect carry a chosen target when the engine/agent picks one; effects that
    decide their own targets (the "any way you like" cases) can ignore it. `db`
    gives card lookups for searches and evolution-chain checks.
    """
    state: GameState
    me: PlayerState          # the player using the attack/ability/trainer
    opp: PlayerState         # their opponent
    source: Optional[InPlayPokemon] = None
    target: Optional[object] = None
    db: Optional[object] = None
    rng: Optional[random.Random] = None
    # WHICH KIND of effect is resolving: "attack" | "ability" | "trainer" | "energy".
    # Needed only
    # where a card's text distinguishes them at a SHARED chokepoint — Rocky Fighting
    # Energy prevents "effects of ATTACKS", but place_counters is also used by abilities,
    # so without this the Energy would wrongly block an opposing Ability's counters.
    # game.py sets it at each hook; the default is "attack" because that's the case the
    # attack-effect unit tests construct contexts for.
    effect_kind: str = "attack"


# --------------------------------------------------------------------------- #
# PRIMITIVES — reusable building blocks. Keep these faithful and well-named.
# --------------------------------------------------------------------------- #
def damage_active(ctx: EffectContext, amount: int) -> None:
    """Plain damage to the opponent's Active (no extra weakness math here; base
    attack damage + weakness is handled by the engine before effects run)."""
    if ctx.opp.active and amount > 0:
        ctx.opp.active.damage += amount


def place_counters_on_bench(ctx: EffectContext, counters: int,
                            policy: str = "maximize_ko") -> None:
    """Place `counters` damage counters (×10 dmg) on the opponent's BENCH,
    distributed 'in any way you like'. v0 default policy: greedily finish the
    benched Pokemon closest to a knockout, to maximize prizes — a strong,
    common line. The policy is a hook an agent can later own.
    """
    bench = ctx.opp.bench
    if not bench:
        return
    # "In any way you like" means the ATTACKER chooses, so a counter that a
    # prevention effect refuses (Battle Cage, Hide 'n' Sneak, Sparkling Scales,
    # Tera-adjacent walls) must NOT be thrown away — a real player simply puts it
    # somewhere else. Without this, one 30 HP Poltchageist with Hide 'n' Sneak would
    # soak an entire Phantom Dive, which is not what the card does. A target that
    # refuses a counter is recorded and skipped for the rest of THIS placement.
    remaining = counters
    blocked: list[InPlayPokemon] = []
    while remaining > 0:
        alive = [m for m in bench
                 if not m.is_knocked_out and not any(m is x for x in blocked)]
        if not alive:
            break
        if policy == "maximize_ko":
            # target the lowest remaining HP (closest to KO)
            target = min(alive, key=lambda m: m.remaining_hp)
        else:  # "spread"
            target = max(alive, key=lambda m: m.remaining_hp)
        # route through the chokepoint so preventions get their say
        if place_counters(ctx, target, 1, owner=ctx.opp):
            remaining -= 1
        else:
            blocked.append(target)


def heal(ctx: EffectContext, mon: InPlayPokemon, amount: int) -> None:
    mon.damage = max(0, mon.damage - amount)


def damage_active_with_weakness(ctx: EffectContext, amount: int) -> None:
    """Deal `amount` to the opponent's Active, applying Weakness (×2) and
    Resistance based on the SOURCE Pokémon's type. Used by variable-damage attacks
    that compute their own total, so weakness multiplies the whole hit once.

    Thin wrapper over the attack-damage chokepoint (§2.5) targeting the Active."""
    apply_attack_damage(ctx, ctx.opp.active, amount, owner=ctx.opp, source=ctx.source)


def discard_basic_energy_from_own(ctx: EffectContext, count: int,
                                  energy_type: Optional[str] = None) -> int:
    """Discard up to `count` Basic Energy from the acting player's Pokémon
    (active first, then bench). If `energy_type` is given, only that type is
    discarded (e.g. Inferno X discards Fire). Returns how many were discarded."""
    discarded = 0
    for mon in ctx.me.all_in_play():
        i = 0
        while i < len(mon.energy) and discarded < count:
            e = mon.energy[i]
            if e.is_basic_energy and (energy_type is None or energy_type in e.types):
                ctx.me.discard.append(mon.energy.pop(i))
                discarded += 1
            else:
                i += 1
    return discarded


def count_basic_energy_on_own(ctx: EffectContext, energy_type: Optional[str] = None) -> int:
    return sum(1 for mon in ctx.me.all_in_play() for e in mon.energy
               if e.is_basic_energy and (energy_type is None or energy_type in e.types))


def attach_basic_energy_from_hand(ctx: EffectContext, energy_type: str,
                                  target: InPlayPokemon) -> bool:
    """Find a Basic <type> Energy in hand and attach it to `target`. (Used by
    acceleration abilities like Teal Dance — does NOT count as the turn's manual
    energy attachment.)"""
    for i, c in enumerate(ctx.me.hand):
        if c.is_basic_energy and energy_type in c.types:
            target.energy.append(ctx.me.hand.pop(i))
            return True
    return False


def discard_hand_and_draw(ctx: EffectContext, n: int) -> None:
    ctx.me.discard.extend(ctx.me.hand)
    ctx.me.hand = []
    ctx.me.draw(n)


def shuffle_hand_into_deck(ctx: EffectContext, who: PlayerState) -> None:
    """Put `who`'s hand into their deck and shuffle. (Lillie's Determination, Judge.)"""
    who.deck.extend(who.hand)
    who.hand = []
    if ctx.rng:
        ctx.rng.shuffle(who.deck)


def draw(ctx: EffectContext, n: int) -> int:
    return ctx.me.draw(n)


def flip(ctx: EffectContext) -> bool:
    """A coin flip — True = heads. Uses ctx.rng so clone/determinize stay reproducible."""
    return bool(ctx.rng.randint(0, 1)) if ctx.rng else True


def discard_opponent_deck_top(ctx: EffectContext, n: int) -> None:
    for _ in range(n):
        if ctx.opp.deck:
            ctx.opp.discard.append(ctx.opp.deck.pop(0))


def dig_and_pick(ctx: EffectContext, look: int, take: int = 1) -> None:
    """Look at the top `look` cards, put `take` into hand (best-first by a simple
    value heuristic), the rest on the BOTTOM of the deck. Models card-selection
    abilities like Drakloak's Recon Directive.
    """
    top = []
    for _ in range(look):
        if ctx.me.deck:
            top.append(ctx.me.deck.pop(0))
    if not top:
        return

    def value(card):
        # crude desirability: Pokemon/Supporter > other Trainer > energy
        if card.is_pokemon:
            return 3
        if card.is_supporter:
            return 3
        if card.is_trainer:
            return 2
        return 1

    top.sort(key=value, reverse=True)
    taken = top[:take]
    rest = top[take:]
    ctx.me.hand.extend(taken)
    ctx.me.deck.extend(rest)   # to the bottom


# --------------------------------------------------------------------------- #
# DECK SEARCH + DISCARD RECOVERY (VALIDATION_MILESTONE §2.1)
# One generalized search primitive that a dozen Trainers/abilities compose. Each
# entry in `predicates` finds ONE best-matching card (so [pred]*3 means "up to 3
# of that kind"; [predA, predB] means "one of each"). The pick policy is a hook an
# agent (MCTS) can later own — v0 grabs the most useful match by a simple value.
# --------------------------------------------------------------------------- #
def _search_value(card) -> int:
    """v0 desirability for which match to grab. Evolution-relevant Basics and
    Stage-2 payoffs first, then other Pokémon/Supporters, then the rest."""
    if card.is_pokemon and card.is_basic and card.evolves_to:
        return 5                      # evolution fodder you can build on
    if card.is_pokemon and "Stage 2" in card.subtypes:
        return 4
    if card.is_pokemon or card.is_supporter:
        return 3
    if card.is_trainer:
        return 2
    return 1


def search_deck(ctx: EffectContext, predicates, dest: str = "hand",
                shuffle: bool = True, policy=None) -> int:
    """Search the acting player's deck. For each predicate, take ONE best match
    (by `policy`, default `_search_value`) into `dest` ('hand' or 'bench'). 'Up to
    N of a kind' = repeat the predicate N times. Shuffles after (a search reveals
    deck order). Returns how many cards were found. Respects bench space."""
    me = ctx.me
    policy = policy or _search_value
    found = 0
    for pred in predicates:
        if dest == "bench" and len(me.bench) >= bench_limit(ctx.state, me):
            break
        candidates = [c for c in me.deck if pred(c)]
        if not candidates:
            continue
        pick = max(candidates, key=policy)
        me.deck.remove(pick)
        if dest == "bench":
            me.bench.append(InPlayPokemon(card=pick, played_this_turn=True))
        else:
            me.hand.append(pick)
        found += 1
    if shuffle and ctx.rng:
        ctx.rng.shuffle(me.deck)
    return found


def recover_from_discard(ctx: EffectContext, predicates, policy=None) -> int:
    """Like search_deck but pulls from the discard pile into hand (no shuffle).
    Used by Night Stretcher, Energy Retrieval, etc."""
    me = ctx.me
    policy = policy or _search_value
    found = 0
    for pred in predicates:
        candidates = [c for c in me.discard if pred(c)]
        if not candidates:
            continue
        pick = max(candidates, key=policy)
        me.discard.remove(pick)
        me.hand.append(pick)
        found += 1
    return found


# Reusable card predicates (compose into the searches above).
def _has_rule_box(card) -> bool:
    subs = {s.lower() for s in card.subtypes}
    return bool(subs & {"ex", "mega", "v", "vmax", "vstar", "gx", "v-union"})

def p_pokemon(c):            return c.is_pokemon
def p_basic_pokemon(c):      return c.is_pokemon and c.is_basic
def p_evolution_pokemon(c):  return c.is_pokemon and c.evolves_from is not None
def p_stage1(c):             return c.is_pokemon and "Stage 1" in c.subtypes
def p_stage2(c):             return c.is_pokemon and "Stage 2" in c.subtypes
def p_non_rule_box_pokemon(c): return c.is_pokemon and not _has_rule_box(c)
def p_basic_energy(c):       return c.is_basic_energy
def p_energy(c):             return c.is_energy
def p_supporter(c):          return c.is_supporter
def p_pokemon_or_basic_energy(c): return c.is_pokemon or c.is_basic_energy
def p_colorless_le100(c):    return c.is_pokemon and "Colorless" in c.types and (c.hp or 999) <= 100
def p_pokemon_ex(c):         return c.is_pokemon and any(s.lower() == "ex" for s in c.subtypes)
def p_stadium(c):            return c.is_trainer and "Stadium" in c.subtypes
def p_trainer(c):            return c.is_trainer
def p_non_rule_box_pkmn_or_basic_energy(c):
    return (c.is_pokemon and not _has_rule_box(c)) or c.is_basic_energy
def p_tera(c):               return c.is_pokemon and "Tera" in c.subtypes
def p_tool(c):               return c.is_trainer and "Pokémon Tool" in c.subtypes
def p_item(c):               return c.is_item
def p_basic_psychic_pokemon(c): return c.is_pokemon and c.is_basic and "Psychic" in c.types
def p_cynthias_pokemon(c) -> bool:
    """A "Cynthia's Pokémon" (Cynthia's Gabite's Champion's Call, Cynthia's Roserade's
    Cheer On to Glory, Cynthia's Power Weight, Cynthia's Spiritomb's Raging Curse).
    Matched on the printed English name, exactly how the cards are worded — every such
    print is named "Cynthia's <Pokémon>". Same approach as p_team_rocket_supporter."""
    return c.is_pokemon and c.name.startswith("Cynthia's")
def p_basic_fighting_energy_or_basic_fighting_pokemon(c) -> bool:
    """Fighting Gong: "a Basic [F] Energy card or a Basic [F] Pokémon". Note the two
    different senses of "Basic" — a Basic Energy CARD, or a Basic (stage) Pokémon."""
    return ((c.is_basic_energy and "Fighting" in c.types)
            or (c.is_pokemon and c.is_basic and "Fighting" in c.types))
def p_grass_pkmn_or_basic_grass_energy(c):
    return (c.is_pokemon and "Grass" in c.types) or (c.is_basic_energy and "Grass" in c.types)
def p_any(c):                return True


def look_and_take(ctx: EffectContext, look: int, predicates, from_bottom: bool = False) -> int:
    """'Look at the top (or bottom) `look` cards; take one best match per predicate
    into hand; shuffle the others back into your deck.' Models Pokégear 3.0, Drayton,
    Dusk Ball — strictly weaker than a full deck search (you only see a window)."""
    me = ctx.me
    if not me.deck:
        return 0
    look = min(look, len(me.deck))
    if from_bottom:
        window, rest = me.deck[-look:], me.deck[:-look]
    else:
        window, rest = me.deck[:look], me.deck[look:]
    pool = list(window)
    taken = []
    for pred in predicates:
        cands = [c for c in pool if pred(c)]
        if not cands:
            continue
        pick = max(cands, key=_search_value)
        pool.remove(pick)
        taken.append(pick)
    me.hand.extend(taken)
    # "Shuffle the other cards back into your deck" — leftovers + the rest, reshuffled.
    me.deck = rest + pool
    if ctx.rng:
        ctx.rng.shuffle(me.deck)
    return len(taken)


def search_deck_to_top(ctx: EffectContext, n: int, policy=None) -> int:
    """'Search your deck for up to N cards, shuffle your deck, then put those cards
    on TOP of it in any order.' (Ciphermaniac's Codebreaking.) The cards go to the
    TOP of the deck to be drawn next — NOT into hand. Deck index 0 is the top (draw
    pops index 0), so the highest-value pick is placed first and drawn first. Shuffle
    happens BEFORE the picks are stacked, exactly as the card sequences it."""
    me = ctx.me
    policy = policy or _search_value
    picked = []
    for _ in range(n):
        if not me.deck:
            break
        pick = max(me.deck, key=policy)
        me.deck.remove(pick)
        picked.append(pick)
    if ctx.rng:
        ctx.rng.shuffle(me.deck)
    me.deck[0:0] = picked      # picked[0] (highest value) ends up on top, drawn first
    return len(picked)


# --------------------------------------------------------------------------- #
# DAMAGE CHOKEPOINTS + STADIUMS (VALIDATION_MILESTONE §2.5)
#
# Two DISTINCT paths — deliberately NOT merged (confirmed ruling):
#   apply_attack_damage() — "damage done by an attack" (printed number ± W/R).
#       Blocked by Tera on the Bench. NOT blocked by Battle Cage.
#   place_counters()      — damage counters placed by an attack/ability EFFECT
#       (Phantom Dive's spread, Cursed Blast). Blocked by Battle Cage when the
#       source is the opposing player. NOT blocked by Tera.
# See docs/project memory project_ptcg_mega_tera_rules.
# --------------------------------------------------------------------------- #

# Stadiums whose FULL printed text is faithfully handled (passive logic lives in
# the chokepoints below). A Stadium not listed here is still playable via the
# engine's Stadium zone, but its effect is unimplemented → the coverage test
# keeps it `needs-effect`.
STADIUM_IMPLEMENTED: set[str] = {"Battle Cage", "Team Rocket's Watchtower",
                                 "Nighttime Mine", "Surfing Beach",
                                 "Gravity Mountain",
                                 # Prism Tower: "Once during each player's turn, that
                                 # player may discard 2 cards from their hand in order to
                                 # draw a card." An ACTIVATED Stadium ability, so unlike
                                 # the passive Stadiums above it is an engine ACTION
                                 # (game.legal_actions / apply_action "stadium_draw",
                                 # budgeted by PlayerState.stadium_draw_used_this_turn) —
                                 # the same shape as Surfing Beach's free switch.
                                 "Prism Tower",
                                 # Academy at Night: "Once during each player's turn,
                                 # that player may put a card from their hand on top of
                                 # their deck." An ACTIVATED Stadium ability — an engine
                                 # ACTION (game.legal_actions / apply_action
                                 # "stadium_academy", budgeted by
                                 # PlayerState.stadium_academy_used_this_turn), enumerated
                                 # per hand card so the agent picks WHICH card. Feeds
                                 # Slowking's Seek Inspiration (top-deck discard).
                                 "Academy at Night",
                                 # Area Zero Underdepths: a PASSIVE Stadium that changes
                                 # the per-player BENCH CAP (8 for a player with a Tera
                                 # Pokémon in play) -> effects.bench_limit, consulted at
                                 # every Bench-placement site, plus the two shrink clauses
                                 # -> effects.enforce_bench_limits.
                                 "Area Zero Underdepths",
                                 # Jamming Tower: "Pokémon Tools attached to each Pokémon
                                 # (both yours and your opponent's) have no effect." A
                                 # PASSIVE Stadium -> effects.tools_disabled, consulted at
                                 # every site that reads an attached Tool (retreat_cost,
                                 # refresh_hp_modifiers, apply_attack_damage,
                                 # end_of_turn_tools).
                                 "Jamming Tower",
                                 # Grand Tree (ACE SPEC) and Mystery Garden: ACTIVATED
                                 # Stadiums, i.e. real engine actions with their own
                                 # once-per-turn budgets on PlayerState — the Prism Tower
                                 # / Surfing Beach shape. "stadium_evolve" runs Grand
                                 # Tree's deck-search evolution chain, "stadium_garden"
                                 # runs Mystery Garden's discard-an-Energy-to-refill draw.
                                 "Grand Tree",
                                 "Mystery Garden",
                                 # Team Rocket's Factory: "Once during each player's turn,
                                 # if they played a Supporter card that has 'Team Rocket'
                                 # in its name from their hand this turn, they may draw 2
                                 # cards." An ACTIVATED Stadium (the Prism Tower shape) —
                                 # game action "stadium_factory", budgeted by
                                 # PlayerState.stadium_factory_used_this_turn, and GATED on
                                 # PlayerState.team_rocket_supporter_played_this_turn, which
                                 # game.apply_action sets when such a Supporter resolves.
                                 "Team Rocket's Factory"}

# Stadiums that change the MAXIMUM HP of Pokémon in play. Stadium name -> mon -> the
# HP delta for that Pokémon. Symmetric (both players) and not an Ability, so — like
# STADIUM_COST_MODIFIERS — it is NOT gated on ability_suppressed.
STADIUM_HP_MODIFIERS: dict[str, Callable] = {
    # Gravity Mountain: "Each Stage 2 Pokémon in play (both yours and your opponent's)
    # gets −30 HP."
    "Gravity Mountain": lambda mon: -30 if "Stage 2" in mon.card.subtypes else 0,
}

# Pokémon TOOLS that change the maximum HP of the Pokémon they're attached to. Tool name
# -> mon -> HP delta. Folded into the same derived `hp_modifier` as the Stadium modifiers
# (never accumulated), so attaching/losing a Tool always lands on the right maximum HP.
TOOL_HP_MODIFIERS: dict[str, Callable] = {
    # Cynthia's Power Weight: "The Cynthia's Pokémon this card is attached to gets
    # +70 HP." Only a Cynthia's Pokémon — the Tool is legal on anything, but grants
    # nothing to a holder that isn't one.
    "Cynthia's Power Weight": lambda mon: 70 if p_cynthias_pokemon(mon.card) else 0,
    # Hero's Cape (ACE SPEC): "The Pokémon this card is attached to gets +100 HP." No
    # holder restriction, unlike Cynthia's Power Weight.
    "Hero's Cape": lambda mon: 100,
}


def refresh_hp_modifiers(state: GameState) -> None:
    """Recompute every in-play Pokémon's `hp_modifier` from the Stadium currently in play
    PLUS its attached Tool. Derived state, recomputed from scratch (never accumulated), so
    installing/replacing/discarding a Stadium, attaching a Tool, or evolving into/out of
    Stage 2 under one always lands on the right maximum HP. Called at the top of
    process_knockouts (so every damage/effect path sees fresh HP) and directly after a
    Stadium is played, a Tool is attached, or a Pokémon evolves."""
    mod = STADIUM_HP_MODIFIERS.get(current_stadium_name(state))
    no_tools = tools_disabled(state)     # Jamming Tower: attached Tools have no effect
    for p in state.players:
        for mon in p.all_in_play():
            delta = mod(mon) if mod is not None else 0
            if mon.tool is not None and not no_tools:
                tool_mod = TOOL_HP_MODIFIERS.get(mon.tool.name)
                if tool_mod is not None:
                    delta += tool_mod(mon)
            mon.hp_modifier = delta


_PRINT_SUFFIX = re.compile(r"\s+\([A-Z0-9]{2,5}\)$")


def print_base_name(name: str) -> str:
    """Strip this project's print-disambiguation suffix: "Dunsparce (JTG)" -> "Dunsparce".

    When a deck needs a DIFFERENT print of a card the pool already has under the bare
    name, the new print is added as "Name (SETCODE)" (Metagross (CRI), Drilbur (TEF),
    Dunsparce (JTG), Shuppet (PBL), ...). That suffix is pool bookkeeping, NOT part of the
    card, so any rule that reads a card's PRINTED name must strip it first.

    SCOPE: used by game.evolves_onto and effects._rare_candy, i.e. the evolution-name
    match. It is NOT applied to registry keys — ATTACK_EFFECTS / ABILITY_EFFECTS stay
    keyed on the exact pool name precisely so two prints can carry different effects,
    which is the whole point of the suffix.
    """
    return _PRINT_SUFFIX.sub("", name)


def _on_bench(player: PlayerState, mon: InPlayPokemon) -> bool:
    """Identity test — NOT `mon in player.bench`. InPlayPokemon is a value-equality
    dataclass, so `in`/`==` would treat two identical Pokémon (e.g. two undamaged
    Dragapult ex) as the same object and mis-locate the target."""
    return any(mon is m for m in player.bench)


def owner_of(state: GameState, mon: InPlayPokemon) -> Optional[PlayerState]:
    """Which player has `mon` in play (active or bench), or None. Identity-based."""
    for p in state.players:
        if mon is p.active or _on_bench(p, mon):
            return p
    return None


def current_stadium_name(state: GameState) -> Optional[str]:
    return state.stadium.name if state.stadium else None


def grand_tree_stage1_for(state: GameState, player: PlayerState,
                          mon: InPlayPokemon):
    """The best Stage 1 in `player`'s deck that evolves from the BASIC `mon`, or None.

    Grand Tree (SCR 136, Stadium/ACE SPEC): "Once during each player's turn, that player
    may search their deck for a Stage 1 Pokémon that evolves from 1 of their Basic
    Pokémon and put it onto that Pokémon to evolve it..."

    The evolution-name match goes through game-level semantics: a card evolves onto `mon`
    when its printed `evolves_from` equals `mon`'s PRINTED name, i.e. with this project's
    "(SETCODE)" disambiguation suffix stripped (print_base_name) — same rule as
    game.evolves_onto and Rare Candy.
    """
    if mon is None or not mon.card.is_basic:
        return None
    base = print_base_name(mon.card.name)
    cands = [c for c in player.deck if p_stage1(c) and c.evolves_from == base]
    return max(cands, key=_search_value) if cands else None


def grand_tree_stage2_for(state: GameState, player: PlayerState, stage1_card):
    """The best Stage 2 in `player`'s deck that evolves from `stage1_card`, or None
    (Grand Tree's second, optional step)."""
    if stage1_card is None:
        return None
    base = print_base_name(stage1_card.name)
    cands = [c for c in player.deck if p_stage2(c) and c.evolves_from == base]
    return max(cands, key=_search_value) if cands else None


def grand_tree_can_evolve(state: GameState, player: PlayerState,
                          mon: InPlayPokemon) -> bool:
    """Is `mon` a legal Grand Tree target for `player` right now?

    The card's own reminder is the whole timing rule: "(Players can't evolve a Basic
    Pokémon during their first turn or a Basic Pokémon that was put into play this turn.)"
    — hence turns_taken >= 2 and not played_this_turn. `evolved_this_turn` is also
    required because a Pokémon that already evolved this turn is not a legal evolution
    target under the general rule; Grand Tree's OWN Basic→Stage 1→Stage 2 chain is the
    explicit exception its text grants, and that happens inside one action.
    """
    if mon is None or player.turns_taken < 2:
        return False
    if mon.played_this_turn or mon.evolved_this_turn:
        return False
    return grand_tree_stage1_for(state, player, mon) is not None


def mystery_garden_target(state: GameState, player: PlayerState) -> int:
    """Mystery Garden (MEG 122): "...draw cards until they have as many cards in their
    hand as they have Psychic Pokémon in play." Returns that hand-size target — the
    number of `player`'s OWN Psychic Pokémon in play (Active + Bench)."""
    return sum(1 for m in player.all_in_play() if "Psychic" in m.card.types)


def mystery_garden_playable(state: GameState, player: PlayerState) -> bool:
    """Offer Mystery Garden's activated draw only when it actually does something:
    an Energy card in hand to pay with, cards left in the deck, and a hand that is
    still SHORT of the Psychic-count target AFTER paying the Energy. (Same standard as
    every other offered effect — the engine never offers a do-nothing action.)"""
    if not player.deck:
        return False
    if not any(c.is_energy for c in player.hand):
        return False
    return (len(player.hand) - 1) < mystery_garden_target(state, player)


def tools_disabled(state: Optional[GameState]) -> bool:
    """Jamming Tower (TWM 153 / sv6-153): "Pokémon Tools attached to each Pokémon (both
    yours and your opponent's) have no effect."

    Symmetric and board-wide, and NOT an Ability — so, like STADIUM_HP_MODIFIERS and
    bench_limit, it is deliberately not gated on ability_suppressed.

    Exactly what "no effect" switches off — every place this engine reads an attached
    Tool, all four of them gated on this one predicate:
      - game.retreat_cost           Air Balloon's −2 retreat.
      - refresh_hp_modifiers        TOOL_HP_MODIFIERS (Cynthia's Power Weight's +70 HP).
      - apply_attack_damage         Brave Bangle's +30, Lucky Helmet's draw-2.
      - end_of_turn_tools           Powerglass's end-of-turn Energy attachment.
    What it does NOT do (correctly): it does not discard Tools, does not stop a Tool
    being ATTACHED (a Tool with no effect is still legally attachable, and it starts
    working the moment Jamming Tower leaves play), and does not touch Special Energy,
    which is not a Tool.
    """
    return state is not None and current_stadium_name(state) == "Jamming Tower"


def can_play_stadium(state: GameState, card) -> bool:
    """A Stadium is playable unless one with the SAME name is already in play
    (a same-name Stadium can't replace itself)."""
    return state.stadium is None or state.stadium.name != card.name


# --------------------------------------------------------------------------- #
# BENCH SIZE (Area Zero Underdepths). The Bench cap used to be the fixed constant
# PlayerState.MAX_BENCH = 5 read directly at every placement site. Area Zero
# Underdepths makes it PER-PLAYER and DYNAMIC, so every one of those sites now goes
# through `bench_limit(state, player)` and MAX_BENCH is the DEFAULT, not the rule.
# --------------------------------------------------------------------------- #
def bench_limit(state: Optional[GameState], player: PlayerState) -> int:
    """How many Pokémon `player` may have on their Bench right now.

    Area Zero Underdepths (SCR 131): "Each player who has any Tera Pokémon in play can
    have up to 8 Pokémon on their Bench." Symmetric (BOTH players get it, not just the
    one who played the Stadium) and conditional on that player's OWN board having a Tera
    Pokémon in play (Active or Bench). Not an Ability, so — like STADIUM_HP_MODIFIERS —
    it is NOT gated on ability_suppressed.

    `state` may be None for callers that have no game state (nothing outside the engine
    does); the answer then is the default 5."""
    if state is not None and current_stadium_name(state) == "Area Zero Underdepths" \
            and any(p_tera(m.card) for m in player.all_in_play()):
        return 8
    return PlayerState.MAX_BENCH


def enforce_bench_limits(state: GameState, first_index: Optional[int] = None) -> None:
    """Shrink both Benches down to their CURRENT `bench_limit`, discarding the excess.

    This is the other half of Area Zero Underdepths, and it covers both of the card's
    shrink clauses, which are the same operation at different moments:
      - "If a player no longer has any Tera Pokémon in play, that player discards
        Pokémon from their Bench until they have 5." (their Tera left -> limit is 5 again)
      - "When this card leaves play, both players discard Pokémon from their Bench until
        they have 5, and the player who played this card discards first." (`first_index`
        is that player; game.apply_action passes the OUTGOING Stadium's owner, captured
        before the replacement overwrites state.stadium_owner.)
    The discard ORDER matters only for which player over-fills first in a rules sense; it
    is preserved anyway so the log reads correctly.

    v0 CHOICE POLICY (the card says "discards Pokémon from their Bench", the player
    chooses which): drop the LAST-benched Pokémon first — the newest, least-invested
    ones. All attached cards (Energy, Tool, the pre-evolution cards underneath) go to the
    discard with it, per the normal "leaves play" rule. A discarded Bench Pokémon is NOT
    a Knock Out: no prizes are taken, which is why this never routes through
    process_knockouts."""
    order = [0, 1]
    if first_index == 1:
        order = [1, 0]
    for idx in order:
        pl = state.players[idx]
        limit = bench_limit(state, pl)
        while len(pl.bench) > limit:
            mon = pl.bench.pop()
            pl.discard.append(mon.card)
            pl.discard.extend(mon.evolved_from)
            pl.discard.extend(mon.energy)
            if mon.tool is not None:
                pl.discard.append(mon.tool)
            state.emit(f"Area Zero Underdepths: {pl.name} discarded {mon.card.name} "
                       f"from the Bench (down to {limit})")


def _fairy_zone_active(state: GameState, defender: InPlayPokemon) -> bool:
    """Lillie's Clefairy ex "Fairy Zone": a continuous, board-wide, non-self Ability —
    while an OPPONENT of `defender` has a Lillie's Clefairy ex in play (Active or Bench,
    Ability not suppressed), each of that opponent's Dragon Pokémon has its Weakness
    rewritten to Psychic. Scoped to "in play for the ability's controller" per the real
    card text (no Active-only restriction). Unlike the passive wall Abilities — which
    check suppression on the DEFENDER — here the holder is a third party to the attack,
    so we check suppression on the HOLDER."""
    if "Dragon" not in defender.card.types:
        return False
    d_owner = owner_of(state, defender)
    if d_owner is None:
        return False
    foe = next((p for p in state.players if p is not d_owner), None)
    if foe is None:
        return False
    return any(m.card.name == "Lillie's Clefairy ex" and not ability_suppressed(state, m)
               for m in foe.all_in_play())


def _apply_weakness_resistance(state: GameState, source_card,
                               defender: InPlayPokemon, dmg: int,
                               skip_weakness: bool = False,
                               skip_resistance: bool = False) -> int:
    """×2 Weakness / flat Resistance based on the SOURCE's first type. (Only the
    Active takes W/R; bench-damage attacks say 'don't apply W/R for Benched'.)

    The two halves are skippable INDEPENDENTLY, because real cards say each on its own:
    Cynthia's Gible's Rock Hurl skips only Resistance, Cynthia's Spiritomb's Raging Curse
    skips only Weakness, and Demolish / Nebula Beam skip both.

    Fairy Zone override: a Dragon defender under an opponent's Lillie's Clefairy ex
    has its Weakness REPLACED by Psychic (the printed Weakness no longer applies);
    Resistance is untouched, since the Ability only changes Weakness."""
    if dmg <= 0:
        return dmg
    stypes = source_card.types if source_card else ()
    if skip_weakness:
        pass
    elif _fairy_zone_active(state, defender):
        if stypes and stypes[0] == "Psychic":
            dmg *= 2
    else:
        for wtype, _ in defender.card.weaknesses:
            if stypes and wtype == stypes[0]:
                dmg *= 2
    if skip_resistance:
        return dmg
    for rtype, rval in defender.card.resistances:
        if stypes and rtype == stypes[0]:
            try:
                dmg = max(0, dmg + int(rval))
            except ValueError:
                pass
    return dmg


# --------------------------------------------------------------------------- #
# Passive "wall" abilities — always-on damage-prevention keyed on a property of
# the ATTACKING Pokémon (its Card), evaluated on the DEFENDER that holds the
# ability. Respect ability suppression (Team Rocket's Watchtower) on the holder.
#   Crustle "Mysterious Rock Inn"           -> source is a Pokémon ex
#   Cornerstone Mask Ogerpon ex "Cornerstone Stance" -> source has an Ability
#   Milotic ex "Sparkling Scales"           -> source is a Tera Pokémon (also blocks
#                                              attack EFFECTS via place_counters)
# --------------------------------------------------------------------------- #
def _source_is_opp_ex(card) -> bool:
    return any(s == "ex" for s in card.subtypes)   # Mega ex carry the 'ex' subtype too


def _is_ex_or_v(card) -> bool:
    """"Pokémon ex and Pokémon V" (Kieran's damage buff). Mega Evolution Pokémon ex carry
    the 'ex' subtype, so they count. Pokémon VMAX / VSTAR are their OWN kinds of Pokémon
    and are NOT Pokémon V, so only the exact 'V' subtype matches."""
    return any(s == "ex" or s == "V" for s in card.subtypes)


def skyliner_free_retreat(state: GameState, owner: PlayerState,
                          mon: InPlayPokemon) -> bool:
    """Latias ex 'Skyliner': "Your Basic Pokémon in play have no Retreat Cost." A
    board-wide passive — a Basic Pokémon of `owner` retreats for free while `owner`
    has an un-suppressed Latias ex in play. (Consulted by game.retreat_cost.)"""
    if not mon.card.is_basic:
        return False
    return any(m.card.name == "Latias ex" and not ability_suppressed(state, m)
               for m in owner.all_in_play())


def _source_is_tera(card) -> bool:
    return "Tera" in card.subtypes


def _wall_is_active(state: GameState, target: InPlayPokemon,
                    source: Optional[InPlayPokemon]) -> bool:
    """Gate shared by the wall checks: `source` is an OPPONENT's Pokémon relative to
    `target`, and `target`'s Ability is not suppressed."""
    if source is None:
        return False
    t_owner = owner_of(state, target)
    s_owner = owner_of(state, source)
    if t_owner is None or s_owner is None or t_owner is s_owner:
        return False
    return not ability_suppressed(state, target)


def wall_prevents_damage(state: GameState, target: InPlayPokemon,
                         source: Optional[InPlayPokemon]) -> bool:
    """True if a passive wall Ability on `target` prevents all attack DAMAGE from
    `source` (an opponent's Pokémon ex / ability-holder / Tera Pokémon)."""
    if not _wall_is_active(state, target, source):
        return False
    sc = source.card
    for ab in target.card.abilities:
        if ab.name == "Mysterious Rock Inn" and _source_is_opp_ex(sc):
            return True
        if ab.name == "Cornerstone Stance" and bool(sc.abilities):
            return True
        if ab.name == "Sparkling Scales" and _source_is_tera(sc):
            return True
    return False


def flat_damage_reduction(state: GameState, target: InPlayPokemon) -> int:
    """Passive Abilities on `target` that reduce attack damage by a FLAT amount, applied
    AFTER Weakness and Resistance.

    Mega Diancie ex (PFL 41 / me2-41) "Diamond Coat": "This Pokémon takes 30 less damage
    from attacks (after applying Weakness and Resistance)."

    Precisely what this covers:
      - Attack damage only — it lives in apply_attack_damage, so damage COUNTERS placed
        by an effect (place_counters) are untouched, exactly as printed.
      - Unconditional on the source: the text names no attacker, so it reduces damage
        from any attack, not just an opponent's. (Hence, unlike the wall Abilities, it
        does NOT go through _wall_is_active's opponent test.)
      - It IS an Ability, so ability suppression (Team Rocket's Watchtower on a Colorless
        holder, an opposing Active Flutter Mane's Midnight Fluttering) switches it off.
      - Stacks additively with Genesect ex's Protect Charge rider, which sits at the same
        point in the chokepoint; both are floored at 0 damage together.
    """
    if target is None or not target.card.abilities:
        return 0
    if not any(ab.name == "Diamond Coat" for ab in target.card.abilities):
        return 0
    return 0 if ability_suppressed(state, target) else 30


def wall_prevents_effect(state: GameState, target: InPlayPokemon,
                         source: Optional[InPlayPokemon]) -> bool:
    """Sparkling Scales also prevents the EFFECTS of attacks (damage counters, and
    conditions routed through helpers) from the opponent's Tera Pokémon."""
    if not _wall_is_active(state, target, source):
        return False
    return (_source_is_tera(source.card)
            and any(ab.name == "Sparkling Scales" for ab in target.card.abilities))


def hide_n_sneak_prevents_effect(state: GameState, target: Optional[InPlayPokemon],
                                 source: Optional[InPlayPokemon],
                                 effect_kind: str) -> bool:
    """Hide 'n' Sneak (Shuppet (PBL) / Banette (PBL) / Poltchageist (PBL) /
    Sinistcha (PBL)): "Prevent all effects of your opponent's Pokémon's attacks and
    Abilities done to this Pokémon. (Damage is not an effect.)"

    Exactly what this covers, and what it does not:
      - COVERS effects of an opposing POKÉMON's ATTACK or ABILITY aimed at the holder —
        hence the `effect_kind in ("attack", "ability")` gate and the requirement that
        `source` be a Pokémon on the other side. Live at both effect chokepoints:
        place_counters (damage counters) and effect_prevented_on (the defender-side
        attack riders: Confusion, forced switch-out).
      - DOES NOT cover damage. "Damage is not an effect", so apply_attack_damage never
        consults this and the holder takes full attack damage. Unlike Poltchageist's OLD
        Twilight Masquerade Ability ("Storehouse Hideaway"), this is NOT damage
        prevention and is NOT restricted to the Bench — it is always on, anywhere.
      - DOES NOT cover TRAINER cards or Special Energy: the text names your opponent's
        *Pokémon's* attacks and Abilities only, so a Boss's Orders gust still moves the
        holder. Trainer effects reach the chokepoints with effect_kind="trainer" (and no
        Pokémon source), which this gate rejects.
      - DOES NOT cover riders the engine models at PLAYER scope rather than on the
        Pokémon (Shadow Bind's can't-retreat, Itchy Pollen's Item lock) — same known,
        deliberate limit documented on rocky_fighting_prevents_effect.
    It IS an Ability, so it is switched off by ability suppression (Team Rocket's
    Watchtower on a Colorless holder, an opposing Active Flutter Mane's Midnight
    Fluttering) — checked on the HOLDER, which is the defender here.
    """
    if target is None or source is None:
        return False
    if effect_kind not in ("attack", "ability"):
        return False
    if not any(ab.name == "Hide 'n' Sneak" for ab in target.card.abilities):
        return False
    if ability_suppressed(state, target):
        return False
    t_owner = owner_of(state, target)
    s_owner = owner_of(state, source)
    if t_owner is None or s_owner is None or t_owner is s_owner:
        return False
    return True


def damage_counter_move_blocked(state: GameState) -> bool:
    """Patrat (CRI)'s "Watchful Eye": "Damage counters on each Pokémon (both yours and
    your opponent's) can't be moved to other Pokémon."

    Symmetric and board-wide — ONE un-suppressed Patrat (CRI) in play, on EITHER side,
    stops every damage-counter MOVE for both players. Precisely scoped: it blocks moving
    counters that are already on a Pokémon (Munkidori's Adrena-Brain is the only such
    effect in this engine), and nothing else. PLACING new counters (Phantom Dive, Cursed
    Blast, Furtive Drop, Matcha Spin) is not moving and is untouched — as is healing.
    """
    return any(any(ab.name == "Watchful Eye" for ab in mon.card.abilities)
               and not ability_suppressed(state, mon)
               for p in state.players for mon in p.all_in_play())


def rocky_fighting_prevents_effect(state: GameState, target: InPlayPokemon,
                                   source: Optional[InPlayPokemon]) -> bool:
    """Rocky Fighting Energy (Special Energy): "Prevent all effects of attacks used by
    your opponent's Pokémon done to the [F] Pokémon this card is attached to. (Existing
    effects are not removed. Damage is not an effect.)"

    Precisely what this covers and what it does not:
      - COVERS: an attack EFFECT from an opposing Pokémon aimed at `target`, when
        `target` is a Fighting Pokémon with a Rocky Fighting Energy attached. Live at the
        engine's effect chokepoints — place_counters (counters placed by an attack) and
        effect_prevented_on (the defender-side riders: Confusion, forced switch-out).
      - DOES NOT cover damage: "Damage is not an effect", so apply_attack_damage never
        consults this. A Rocky-protected Pokémon still takes full attack damage.
      - DOES NOT retroactively remove an effect already applied ("Existing effects are
        not removed") — it only blocks new ones, which is exactly what a gate at the
        point of application does.
      - DOES NOT cover riders the engine models at PLAYER scope rather than on the
        Pokémon (Shadow Bind's can't-retreat, Itchy Pollen's Item lock): those are stored
        on PlayerState, not on the target, so this gate never sees them. A known,
        deliberate limit of the modeling, not a claim of coverage.
    It is a Special Energy, NOT an Ability, so Team Rocket's Watchtower cannot switch it
    off (ability_suppressed is deliberately not consulted)."""
    if target is None or source is None:
        return False
    if "Fighting" not in target.card.types:
        return False
    if not any(e.name == "Rocky Fighting Energy" for e in target.energy):
        return False
    t_owner = owner_of(state, target)
    s_owner = owner_of(state, source)
    if t_owner is None or s_owner is None or t_owner is s_owner:
        return False
    return True


def mist_energy_prevents_effect(state: GameState, target: InPlayPokemon,
                                source: Optional[InPlayPokemon]) -> bool:
    """Mist Energy (Special Energy): "Prevent all effects of attacks used by your
    opponent's Pokémon done to the Pokémon this card is attached to. (Existing effects
    are not removed. Damage is not an effect.)"

    Identical coverage/scope to rocky_fighting_prevents_effect (same chokepoints, same
    "damage is not an effect" carve-out, same PlayerState-scope blind spot) — the only
    difference from Rocky Fighting Energy is there is no holder-type restriction (Mist
    Energy protects ANY Pokémon it's attached to, not just Fighting-type)."""
    if target is None or source is None:
        return False
    if not any(e.name == "Mist Energy" for e in target.energy):
        return False
    t_owner = owner_of(state, target)
    s_owner = owner_of(state, source)
    if t_owner is None or s_owner is None or t_owner is s_owner:
        return False
    return True


# --------------------------------------------------------------------------- #
# DYNAMIC ATTACK COSTS — start from the printed cost and discount Colorless
# symbols per active modifiers (Bloodmoon Ursaluna ex's Seasoned Skill). Only
# Colorless symbols are removed (never typed ones), clamped at 0. `can_pay_cost`
# stays pure; game.legal_actions / evaluation consult effective_cost.
# --------------------------------------------------------------------------- #
_STARTING_PRIZES = 6


def _controller_opponent(state: GameState, mon: InPlayPokemon) -> Optional[PlayerState]:
    owner = owner_of(state, mon)
    for p in state.players:
        if p is not owner:
            return p
    return None


def _blood_moon_discount(state: GameState, mon: InPlayPokemon) -> int:
    """Seasoned Skill: Blood Moon costs Colorless less for each Prize the opponent
    has already taken (= 6 − their remaining Prizes)."""
    opp = _controller_opponent(state, mon)
    return _STARTING_PRIZES - len(opp.prizes) if opp else 0


# (card_name, attack_name) -> (state, mon) -> number of Colorless symbols to remove.
COST_MODIFIERS: dict[tuple[str, str], Callable] = {
    ("Bloodmoon Ursaluna ex", "Blood Moon"): _blood_moon_discount,
}

# Stadium name -> (state, mon) -> number of Colorless symbols to ADD. Unlike
# COST_MODIFIERS these are stadium effects, not Abilities, so they are NOT
# gated on ability_suppressed and apply symmetrically to both players.
STADIUM_COST_MODIFIERS: dict[str, Callable] = {
    # Nighttime Mine: "Attacks used by each Tera Pokémon in play (both yours and
    # your opponent's) cost [C] more."
    "Nighttime Mine": lambda state, mon: 1 if _source_is_tera(mon.card) else 0,
}


def effective_cost(state: GameState, mon: InPlayPokemon, atk) -> tuple:
    """The attack's Energy cost after Colorless discounts/increases. Ability-based
    discounts (COST_MODIFIERS) respect ability suppression; Stadium-based increases
    (STADIUM_COST_MODIFIERS) don't — they aren't Abilities."""
    discount = 0
    mod = COST_MODIFIERS.get((mon.card.name, atk.name))
    if mod is not None and not ability_suppressed(state, mon):
        discount = mod(state, mon)
    increase = 0
    stad_mod = STADIUM_COST_MODIFIERS.get(current_stadium_name(state))
    if stad_mod is not None:
        increase = stad_mod(state, mon)
    if discount <= 0 and increase <= 0:
        return atk.cost
    typed = [s for s in atk.cost if s != "Colorless"]
    colorless = max(0, sum(1 for s in atk.cost if s == "Colorless") - discount) + increase
    return tuple(typed) + ("Colorless",) * colorless


def apply_attack_damage(ctx: EffectContext, target: InPlayPokemon, amount: int,
                        owner: Optional[PlayerState] = None,
                        source: Optional[InPlayPokemon] = None,
                        ignore_active_effects: bool = False,
                        ignore_weakness: bool = False,
                        ignore_resistance: bool = False) -> int:
    """Deal `amount` ATTACK damage to `target`. Applies Weakness/Resistance to an
    Active target, and Tera bench-immunity to a Benched one. Returns damage dealt.

    `ignore_active_effects` (Superb Scissors / Demolish): skip damage-prevention
    "effects on the opponent's Active" — Dunsparce Dig's shield and the passive wall
    Abilities. `ignore_weakness` / `ignore_resistance` skip exactly the half they name,
    independently, because cards say each on its own: Cynthia's Gible's Rock Hurl isn't
    affected by Resistance, Cynthia's Spiritomb's Raging Curse isn't affected by
    Weakness, and Demolish / Nebula Beam pass BOTH."""
    if target is None or amount <= 0:
        return 0
    if getattr(target, "shielded", False) and not ignore_active_effects:
        ctx.state.emit(f"{target.card.name} is shielded — no attack damage")
        return 0
    owner = owner if owner is not None else owner_of(ctx.state, target)
    source = source if source is not None else ctx.source
    on_bench = owner is not None and _on_bench(owner, target)
    dmg = amount
    # Brave Bangle (Tool): a non-Rule-Box holder's attacks do 30 more damage to the
    # opponent's Active Pokémon ex, BEFORE Weakness/Resistance. (Only the Active, and
    # only a Pokémon ex target — verified card text, both prints.)
    # (Jamming Tower switches every attached Tool off — see tools_disabled.)
    no_tools = tools_disabled(ctx.state)
    if (not on_bench and source is not None and source.tool is not None and not no_tools
            and source.tool.name == "Brave Bangle" and not _has_rule_box(source.card)
            and _source_is_opp_ex(target.card)):
        dmg += 30
    # Kieran (Supporter, 2nd mode): "During this turn, attacks used by your Pokémon do
    # 30 more damage to your opponent's Active Pokémon ex and Active Pokémon V (before
    # applying Weakness and Resistance)." Read off the ATTACKER's owner (not ctx.me, so
    # it stays correct for damage dealt outside the attacker's own resolve path), and
    # only against the opponent's ACTIVE ex/V — never a Benched one.
    #
    # Premium Power Pro (Item): "During this turn, attacks used by your [F] Pokémon do 30
    # more damage to your opponent's Active Pokémon (before applying Weakness and
    # Resistance)." Read off the ATTACKER's owner and gated on the attacker being a
    # Fighting Pokémon; ANY Active target (not just ex/V), and never a Benched one.
    #
    # Cynthia's Roserade "Cheer On to Glory" (passive Ability): "Attacks used by your
    # Cynthia's Pokémon do 30 more damage to your opponent's Active Pokémon (before
    # applying Weakness and Resistance)." Same shape, keyed on the attacker being a
    # Cynthia's Pokémon whose owner has an un-suppressed Cynthia's Roserade in play
    # (Active or Bench). Copies STACK: each Roserade is its own continuous Ability, so a
    # board with 2 gives +60. Modeled here rather than as a wall/registry entry for the
    # same reason Brave Bangle is — it's a pre-W/R damage add at the chokepoint.
    if not on_bench and source is not None:
        s_owner = owner_of(ctx.state, source)
        t_owner = owner if owner is not None else owner_of(ctx.state, target)
        if s_owner is not None and t_owner is not None and s_owner is not t_owner:
            if s_owner.bonus_damage_vs_ex_v and _is_ex_or_v(target.card):
                dmg += s_owner.bonus_damage_vs_ex_v
            # Gladion's Final Battle: "+80 more damage to your opponent's Active
            # Pokémon (before W/R)" for attackers WITHOUT a Rule Box, this turn.
            if (s_owner.bonus_damage_nonrulebox and target is t_owner.active
                    and not _has_rule_box(source.card)):
                dmg += s_owner.bonus_damage_nonrulebox
            if target is t_owner.active:
                if (s_owner.bonus_damage_fighting_vs_active
                        and "Fighting" in source.card.types):
                    dmg += s_owner.bonus_damage_fighting_vs_active
                if p_cynthias_pokemon(source.card):
                    dmg += sum(30 for m in s_owner.all_in_play()
                               if m.card.name == "Cynthia's Roserade"
                               and not ability_suppressed(ctx.state, m))
    if not on_bench:
        dmg = _apply_weakness_resistance(ctx.state, source.card if source else None, target,
                                         dmg, skip_weakness=ignore_weakness,
                                         skip_resistance=ignore_resistance)
    # Genesect ex "Protect Charge": "During your opponent's next turn, this Pokémon takes
    # 30 less damage from attacks (AFTER applying Weakness and Resistance)" — hence this
    # sits below the W/R block. It is an effect ON the defender, so the "damage isn't
    # affected by any effects on your opponent's Active" attacks (Superb Scissors,
    # Demolish, Nebula Beam) bypass it, same as they bypass Dig's shield and the walls.
    #
    # Mega Diancie ex's "Diamond Coat" is the same shape — a flat 30 less "after applying
    # Weakness and Resistance" — but as a permanent passive Ability rather than a
    # one-turn rider, so it is read off the card here (flat_damage_reduction) instead of
    # from a turn-scoped field. Both are effects ON the defender, hence both sit under
    # the same `ignore_active_effects` bypass, and they stack additively.
    if dmg > 0 and not ignore_active_effects:
        passive = flat_damage_reduction(ctx.state, target)
        reduction = target.damage_reduction + passive
        if reduction:
            reduced = max(0, dmg - reduction)
            if reduced != dmg:
                why = ([("Protect Charge")] if target.damage_reduction else []) \
                      + (["Diamond Coat"] if passive else [])
                ctx.state.emit(f"{target.card.name} takes {dmg - reduced} less damage "
                               f"({' + '.join(why)})")
            dmg = reduced
    # Passive wall Abilities on the defender (Mysterious Rock Inn / Cornerstone
    # Stance / Sparkling Scales) — bypassed by "ignore effects on the Active" attacks.
    if not ignore_active_effects and wall_prevents_damage(ctx.state, target, source):
        ctx.state.emit(f"{target.card.name}'s Ability prevented {dmg} attack damage"
                       + (f" from {source.card.name}" if source else ""))
        return 0
    # Tera: "Prevent all damage done to this Pokémon by attacks while on your Bench."
    if on_bench and "Tera" in target.card.subtypes:
        ctx.state.emit(f"Tera: prevented {dmg} attack damage to benched {target.card.name}")
        return 0
    # Shaymin (DRI) "Flower Curtain" (passive Ability): "Prevent all damage done to your
    # Benched Pokémon that don't have a Rule Box by attacks from your opponent's
    # Pokémon." Exact scope, all three clauses: (1) BENCHED targets of the Shaymin's
    # owner only, (2) non-Rule-Box targets only (a benched Mega/ex is NOT protected —
    # and this print has no self-exception, so a benched Shaymin protects itself),
    # (3) attacks from the OPPONENT's Pokémon only (your own attack's spread — e.g. a
    # copied Trifrost hitting your own board — is not prevented). Damage only: an
    # effect-KO (Destined Fight) or placed counters are not "damage done by attacks"
    # here (counters route through place_counters, which this never sees).
    if (on_bench and source is not None and owner is not None
            and owner_of(ctx.state, source) is not owner
            and not _has_rule_box(target.card)
            and any(m.card.name == "Shaymin (DRI)"
                    and not ability_suppressed(ctx.state, m)
                    for m in owner.all_in_play())):
        ctx.state.emit(f"Flower Curtain: prevented {dmg} attack damage to benched "
                       f"{target.card.name}")
        return 0
    # Rabsca "Spherical Shield" (passive Ability): "Prevent all damage from and effects
    # of attacks from your opponent's Pokémon done to your Benched Pokémon." Broader
    # than Flower Curtain on one axis (no Rule-Box clause — an ex on the Bench IS
    # protected) and identical on the others: BENCHED targets of the Rabsca's owner,
    # opponent's attacks only. The effects half lives in place_counters.
    if (on_bench and source is not None and owner is not None
            and owner_of(ctx.state, source) is not owner
            and any(m.card.name == "Rabsca"
                    and not ability_suppressed(ctx.state, m)
                    for m in owner.all_in_play())):
        ctx.state.emit(f"Spherical Shield: prevented {dmg} attack damage to benched "
                       f"{target.card.name}")
        return 0
    if dmg > 0:
        target.damage += dmg
        # Record the KO CAUSE for Legacy Energy ("Knocked Out by damage from an attack
        # from your opponent's Pokémon"). This is the only path that is attack damage, and
        # the flag is set only when the hit came from the other side and actually finished
        # the target — so an effect's damage counters and a self-KO never arm it.
        if target.is_knocked_out and source is not None:
            s_owner = owner_of(ctx.state, source)
            if s_owner is not None and owner is not None and s_owner is not owner:
                target.koed_by_opponent_attack_damage = True
        # Lucky Helmet (Tool): when the holder is in the Active Spot and is damaged by
        # an opponent's attack (even if Knocked Out), its controller draws 2.
        if (owner is not None and not on_bench and target.tool is not None and not no_tools
                and target.tool.name == "Lucky Helmet" and source is not None
                and owner_of(ctx.state, source) is not owner):
            owner.draw(2)
            ctx.state.emit(f"Lucky Helmet: {owner.name} drew 2")
        # Shellnado Spin (Mega Slowbro ex): if the just-damaged target was set to
        # retaliate, place 12 counters on the ATTACKING Pokémon — fires even if this
        # damage just Knocked Out the retaliating target, since KOs are resolved by
        # the caller after apply_attack_damage returns, not inside it.
        if getattr(target, "retaliate", False) and source is not None and source is not target:
            src_owner = owner_of(ctx.state, source)
            placed = place_counters(ctx, source, target.retaliate_counters, owner=src_owner)
            if placed:
                ctx.state.emit(f"Retaliation: {target.card.name} places {placed * 10} "
                               f"damage on {source.card.name}")
        # Spiky Energy: "If the Pokémon this card is attached to is in the Active Spot and
        # is damaged by an attack from your opponent's Pokémon (even if this Pokémon is
        # Knocked Out), put 2 damage counters on the Attacking Pokémon." A STANDING
        # passive (unlike Shellnado Spin's one-turn flag) — checked directly off the
        # attached Energy every time, no set-and-clear needed, so it fires on every
        # qualifying hit for as long as the card stays attached and the holder is Active.
        if (not on_bench and source is not None and source is not target
                and any(e.name == "Spiky Energy" for e in target.energy)
                and owner_of(ctx.state, source) is not owner):
            src_owner = owner_of(ctx.state, source)
            placed = place_counters(ctx, source, 2, owner=src_owner)
            if placed:
                ctx.state.emit(f"Spiky Energy: retaliation places {placed * 10} "
                               f"damage on {source.card.name}")
    return dmg


def place_counters(ctx: EffectContext, target: InPlayPokemon, counters: int,
                   owner: Optional[PlayerState] = None) -> int:
    """Place `counters` damage counters (×10 dmg) on `target` via an attack/ability
    EFFECT. Battle Cage prevents counters on a Benched Pokémon placed by the
    OPPOSING player. Returns counters actually placed."""
    if target is None or counters <= 0:
        return 0
    if getattr(target, "shielded", False):     # Dig also blocks effects of attacks
        return 0
    # Sparkling Scales: prevent effect-damage (counters) from a Tera source.
    if wall_prevents_effect(ctx.state, target, ctx.source):
        ctx.state.emit(f"{target.card.name}'s Ability prevented {counters} counter(s) "
                       f"from a Tera Pokémon")
        return 0
    # Rocky Fighting Energy: prevents the EFFECTS of ATTACKS only — hence the
    # effect_kind gate, so an opposing ABILITY's counters (Cursed Blast, Adrena-Brain,
    # Mortal Shuriken) still land on the protected Pokémon.
    if (ctx.effect_kind == "attack"
            and rocky_fighting_prevents_effect(ctx.state, target, ctx.source)):
        ctx.state.emit(f"Rocky Fighting Energy: prevented {counters} counter(s) on "
                       f"{target.card.name} (effect of an attack)")
        return 0
    # Mist Energy: same "attacks only" scope as Rocky Fighting Energy, no type gate.
    if (ctx.effect_kind == "attack"
            and mist_energy_prevents_effect(ctx.state, target, ctx.source)):
        ctx.state.emit(f"Mist Energy: prevented {counters} counter(s) on "
                       f"{target.card.name} (effect of an attack)")
        return 0
    # Hide 'n' Sneak: prevents the effects of an opposing Pokémon's ATTACKS *and*
    # ABILITIES on the holder — so unlike Rocky Fighting Energy it also blocks an
    # opposing Ability's counters (Cursed Blast, Adrena-Brain, Mortal Shuriken).
    if hide_n_sneak_prevents_effect(ctx.state, target, ctx.source, ctx.effect_kind):
        ctx.state.emit(f"Hide 'n' Sneak: prevented {counters} counter(s) on "
                       f"{target.card.name}")
        return 0
    owner = owner if owner is not None else owner_of(ctx.state, target)
    on_bench = owner is not None and _on_bench(owner, target)
    # Rabsca "Spherical Shield": the "effects of attacks" half — an opposing ATTACK's
    # counters on the owner's Bench are prevented (an ABILITY's counters are not,
    # matching the card's "effects of attacks" wording).
    if (on_bench and owner is not ctx.me and ctx.effect_kind == "attack"
            and any(m.card.name == "Rabsca"
                    and not ability_suppressed(ctx.state, m)
                    for m in owner.all_in_play())):
        ctx.state.emit(f"Spherical Shield: prevented {counters} counter(s) on benched "
                       f"{target.card.name}")
        return 0
    if (on_bench and owner is not ctx.me
            and current_stadium_name(ctx.state) == "Battle Cage"):
        ctx.state.emit(f"Battle Cage: prevented {counters} counter(s) on benched "
                       f"{target.card.name}")
        return 0
    target.damage += counters * 10
    return counters


def effect_prevented_on(ctx: EffectContext, target: Optional[InPlayPokemon]) -> bool:
    """Shared gate for an ATTACK effect that is "done to" one specific Pokémon and isn't
    routed through place_counters — a Special Condition on the Defending Pokémon, a forced
    switch-out, etc. True when an effect-prevention on `target` blocks it.

    Only ever called from attack effects, so (unlike place_counters, which abilities also
    use) it needs no effect_kind test — Hide 'n' Sneak is therefore asked about the
    "attack" kind explicitly, which is the only kind that reaches here."""
    if target is None:
        return False
    return (wall_prevents_effect(ctx.state, target, ctx.source)
            or rocky_fighting_prevents_effect(ctx.state, target, ctx.source)
            or mist_energy_prevents_effect(ctx.state, target, ctx.source)
            or hide_n_sneak_prevents_effect(ctx.state, target, ctx.source, "attack"))


# --------------------------------------------------------------------------- #
# KNOCKOUT PROCESSING — shared by the engine after any damage is dealt.
# Effects can KO benched Pokemon (e.g. Phantom Dive), so this must scan the
# whole board, not just the Active.
# --------------------------------------------------------------------------- #
def process_knockouts(state: GameState) -> None:
    """Scan BOTH boards. For every knocked-out Pokémon, its owner's OPPONENT takes
    the prizes — so a self-KO (Cursed Blast) correctly gives prizes to the opponent.
    Move KO'd cards to discard, promote a new Active where needed, and record a
    player's KOs that happened on the OPPONENT's turn (for Flip the Script).

    HP modifiers (Gravity Mountain's −30, Cynthia's Power Weight's +70) are refreshed
    FIRST, so a Pokémon whose maximum HP just dropped to at-or-below its damage is swept
    here, exactly like one that was damaged past its printed HP.
    """
    refresh_hp_modifiers(state)
    for i, owner in enumerate(state.players):
        scorer = state.players[1 - i]
        koed_any = False

        survivors = []
        for m in owner.bench:
            if m.is_knocked_out:
                _ko_cleanup(state, scorer, owner, m)
                koed_any = True
            else:
                survivors.append(m)
        owner.bench = survivors

        if owner.active and owner.active.is_knocked_out:
            ko = owner.active
            owner.active = None
            _ko_cleanup(state, scorer, owner, ko)
            _promote(owner)
            koed_any = True

        # "during your opponent's last turn" = owner lost a Pokémon while it was
        # NOT owner's turn. (A self-KO on your own turn must NOT arm your own
        # Flip the Script.)
        if koed_any and state.active_index != i:
            owner.koed_during_opp_turn = True

    # Area Zero Underdepths: "If a player no longer has any Tera Pokémon in play, that
    # player discards Pokémon from their Bench until they have 5." A KO is the usual way
    # a player's last Tera Pokémon leaves play, and process_knockouts is the engine's
    # general post-action sweep (it runs after every attack, Trainer, evolve and Stadium
    # play), so the shrink is checked here for the same reason the HP refresh is.
    # PRECISE SCOPE: the sweep runs after attacks, Trainers, Abilities, evolutions and
    # Stadium plays — every engine path that can take a Pokémon out of play. The two
    # actions that do NOT sweep (play_basic, retreat) cannot remove a Pokémon from play,
    # so they cannot drop a player's last Tera. The one stadium-removal path outside
    # apply_action is Chien-Pao's Snow Sink, which calls enforce_bench_limits itself.
    enforce_bench_limits(state)


def _ko_cleanup(state, scorer, victim, mon) -> None:
    prizes = mon.card.gives_up_prizes
    # Legacy Energy (ACE SPEC): "If the Pokémon this card is attached to is Knocked Out by
    # damage from an attack from your opponent's Pokémon, that player takes 1 fewer Prize
    # card. This effect of your Legacy Energy can't be applied more than once per game."
    #   - "by damage from an attack from your opponent's Pokémon" -> the cause flag set in
    #     apply_attack_damage, so a self-KO or a KO by placed damage counters does NOT
    #     reduce prizes;
    #   - "your Legacy Energy" -> the once-per-game budget lives on the KO'd Pokémon's
    #     OWNER (the Energy's controller), not on the player taking the prizes;
    #   - 1 FEWER prize, floored at 0 (a 1-prize Pokémon awards none).
    if (mon.koed_by_opponent_attack_damage
            and any(e.name == "Legacy Energy" for e in mon.energy)
            and not victim.legacy_energy_prize_reduction_used):
        victim.legacy_energy_prize_reduction_used = True
        prizes = max(0, prizes - 1)
        state.emit(f"Legacy Energy: {scorer.name} takes 1 fewer Prize card "
                   f"for {mon.card.name}")
    # Lillie's Pearl (Tool): "If the Lillie's Pokémon this card is attached to is
    # Knocked Out by damage from an attack from your opponent's Pokémon, that player
    # takes 1 fewer Prize card." No once-per-game clause on this card (unlike Legacy
    # Energy) — each copy can trigger independently, once, on its own KO (the Tool
    # discards with its holder, so it physically can't re-fire).
    if (mon.koed_by_opponent_attack_damage
            and mon.tool is not None and mon.tool.name == "Lillie's Pearl"
            and mon.card.name.startswith("Lillie's")):
        prizes = max(0, prizes - 1)
        state.emit(f"Lillie's Pearl: {scorer.name} takes 1 fewer Prize card "
                   f"for {mon.card.name}")
    victim.discard.append(mon.card)
    victim.discard.extend(mon.energy)
    victim.discard.extend(mon.evolved_from)
    if mon.tool is not None:
        victim.discard.append(mon.tool)
    for _ in range(prizes):
        if scorer.prizes:
            scorer.hand.append(scorer.prizes.pop())
    state.emit(f"{mon.card.name} KO'd; {scorer.name} takes {prizes} prize(s)")


def _promote(victim: PlayerState) -> None:
    if victim.active is None and victim.bench:
        victim.bench.sort(key=lambda m: m.remaining_hp, reverse=True)
        victim.active = victim.bench.pop(0)


# --------------------------------------------------------------------------- #
# CARD REGISTRIES — hand-written effects, keyed by (card name, move name).
# Cards NOT listed here fall back to base-damage-only (engine default).
# --------------------------------------------------------------------------- #
def _phantom_dive(ctx: EffectContext) -> None:
    # 200 base damage to Active is applied by the engine; the EFFECT is the spread.
    place_counters_on_bench(ctx, counters=6, policy="maximize_ko")


def _recon_directive(ctx: EffectContext) -> None:
    dig_and_pick(ctx, look=2, take=1)


def _run_away_draw(ctx: EffectContext) -> None:
    """Dudunsparce ability: draw 3; if you drew any, shuffle THIS Pokémon and all
    attached cards back into your deck (removing it from play). The Charizard deck's
    core draw engine — used from the Bench, recycled into the deck each time."""
    drew = draw(ctx, 3)
    if drew <= 0:
        return
    mon = ctx.source
    me = ctx.me
    me.deck.append(mon.card)
    me.deck.extend(mon.energy)
    me.deck.extend(mon.evolved_from)
    if me.active is mon:
        me.active = None
        if me.bench:                       # promote the healthiest bencher (v0 policy)
            me.bench.sort(key=lambda m: m.remaining_hp, reverse=True)
            me.active = me.bench.pop(0)
    else:
        me.bench = [m for m in me.bench if m is not mon]
    if ctx.rng:
        ctx.rng.shuffle(me.deck)
    ctx.state.emit(f"Run Away Draw: drew {drew}, shuffled Dudunsparce into the deck")


# --- Raging Bolt ex / Teal Mask Ogerpon ex / Mega Charizard X ex ---
def _discard_energy_for_damage(ctx: EffectContext, per_hit: int,
                               energy_type: Optional[str] = None) -> None:
    """Shared logic for 'discard any amount of [Fire/Basic] Energy; N damage each'
    attacks (Inferno X, Bellowing Thunder). Engine applied 0 base; we compute it.

    Discard policy (v1, a hook MCTS can later own): discard exactly enough to KO
    the opponent's Active if reachable; otherwise discard a conservative 2 so we
    don't strip our own board. Weakness is applied to the total via the helper.
    """
    opp = ctx.opp.active
    available = count_basic_energy_on_own(ctx, energy_type)
    if available == 0 or opp is None:
        return
    src = ctx.source.card.types[0] if ctx.source and ctx.source.card.types else None
    effective = per_hit * 2 if any(w == src for w, _ in opp.card.weaknesses) else per_hit
    need = -(-opp.remaining_hp // effective)        # ceil division to reach lethal
    discard_n = need if 0 < need <= available else min(available, 2)
    discarded = discard_basic_energy_from_own(ctx, discard_n, energy_type)
    damage_active_with_weakness(ctx, per_hit * discarded)


def _bellowing_thunder(ctx: EffectContext) -> None:
    # 'Discard any amount of Basic Energy from your Pokémon. 70 damage for each.'
    _discard_energy_for_damage(ctx, per_hit=70, energy_type=None)


def _inferno_x(ctx: EffectContext) -> None:
    # 'Discard any amount of Fire Energy from among your Pokémon. 90 damage each.'
    _discard_energy_for_damage(ctx, per_hit=90, energy_type="Fire")


def _burst_roar(ctx: EffectContext) -> None:
    discard_hand_and_draw(ctx, 6)


def _teal_dance(ctx: EffectContext) -> None:
    """Ability: attach a Basic Grass Energy from hand to this Pokémon, then draw."""
    if attach_basic_energy_from_hand(ctx, "Grass", ctx.source):
        draw(ctx, 1)


def _myriad_leaf_shower(ctx: EffectContext) -> None:
    """'30+': 30 more damage for each Energy attached to BOTH Active Pokémon.
    Variable — engine applied 0 base; we compute 30 + 30*count and apply weakness.
    """
    n = 0
    if ctx.me.active:
        n += ctx.me.active.energy_count()
    if ctx.opp.active:
        n += ctx.opp.active.energy_count()
    damage_active_with_weakness(ctx, 30 + 30 * n)


# --- §2.7 KO / damage-manipulation engine (Cursed Blast, Adrena-Brain, Flip the
# Script, Cruel Arrow, Explosion Y). v0 targeting picks a KO where possible; MCTS
# owns the real choice. ---
def _pick_ko_target(player: PlayerState, dmg: int) -> Optional[InPlayPokemon]:
    """An opponent Pokémon `dmg` would KO (prefer most prizes, then lowest HP), else None."""
    koable = [m for m in player.all_in_play() if 0 < m.remaining_hp <= dmg]
    if koable:
        return max(koable, key=lambda m: (m.card.gives_up_prizes, -m.remaining_hp))
    return None


def _cursed_blast(ctx: EffectContext, counters: int) -> None:
    """Put `counters` damage counters on 1 opp Pokémon, then THIS Pokémon is KO'd
    (its owner's opponent takes the prize — that's the cost)."""
    opp = ctx.opp
    target = _pick_ko_target(opp, counters * 10) or opp.active
    if target is not None:
        place_counters(ctx, target, counters, owner=opp)   # Battle Cage may prevent on bench
    ctx.source.damage = ctx.source.card.hp or 9999          # self-KO; swept by process_knockouts
    ctx.state.emit(f"Cursed Blast: {counters} counters; {ctx.source.card.name} KO's itself")


def _cursed_blast_5(ctx: EffectContext) -> None:   _cursed_blast(ctx, 5)    # Dusclops
def _cursed_blast_13(ctx: EffectContext) -> None:  _cursed_blast(ctx, 13)   # Dusknoir


def _adrena_brain(ctx: EffectContext) -> None:
    """Move up to 3 damage counters from 1 of your Pokémon to 1 of the opponent's."""
    # Patrat (CRI)'s Watchful Eye: "Damage counters ... can't be MOVED to other Pokémon."
    # This is the engine's only counter-move effect, so this is the only gate it needs.
    if damage_counter_move_blocked(ctx.state):
        ctx.state.emit("Watchful Eye: damage counters can't be moved — Adrena-Brain does nothing")
        return
    mine = [m for m in ctx.me.all_in_play() if m.damage >= 10]
    if not mine:
        return
    donor = max(mine, key=lambda m: m.damage)
    n = min(3, donor.damage // 10)
    target = _pick_ko_target(ctx.opp, n * 10) or ctx.opp.active
    if target is None:
        return
    placed = place_counters(ctx, target, n, owner=ctx.opp)
    donor.damage -= placed * 10           # only the counters actually moved leave you
    if placed:
        ctx.state.emit(f"Adrena-Brain: moved {placed} counter(s) to {target.card.name}")


def _powerful_hand(ctx: EffectContext) -> None:
    """Alakazam: place 2 damage counters on the opponent's Active for each card in your
    hand (counters via place_counters, NOT attack damage — no Weakness). Hand size is
    read live, after the attack's Energy cost was already paid (Energy is never a hand
    card, so no interaction)."""
    n = 2 * len(ctx.me.hand)
    if n and ctx.opp.active is not None:
        placed = place_counters(ctx, ctx.opp.active, n, owner=ctx.opp)
        if placed:
            ctx.state.emit(f"Powerful Hand: placed {placed} counter(s)")


def _flip_the_script(ctx: EffectContext) -> None:
    """If a Pokémon of yours was KO'd during the opponent's last turn, draw 3."""
    if ctx.me.koed_last_turn:
        draw(ctx, 3)
        ctx.state.emit("Flip the Script: drew 3")


def _cruel_arrow(ctx: EffectContext) -> None:
    """100 damage to 1 of the opponent's Pokémon (no W/R for Benched — handled by
    the chokepoint, which applies W/R only to the Active)."""
    target = _pick_ko_target(ctx.opp, 100) or ctx.opp.active
    apply_attack_damage(ctx, target, 100, owner=ctx.opp)


def _explosion_y(ctx: EffectContext) -> None:
    """Discard 3 Energy from this Pokémon, then 280 to 1 of the opponent's Pokémon."""
    src = ctx.source
    for _ in range(3):
        if src.energy:
            ctx.me.discard.append(src.energy.pop())
    target = _pick_ko_target(ctx.opp, 280) or ctx.opp.active
    apply_attack_damage(ctx, target, 280, owner=ctx.opp)


# --- §2.6 Special Conditions (Confusion / can't-retreat / can't-play-Items).
# Base damage is applied by the engine; these add the rider. ---
def _mind_bend(ctx: EffectContext) -> None:
    """Munkidori: 60, and the opponent's Active is now Confused. Confusion is an EFFECT
    of the attack done to that Pokémon, so it goes through effect_prevented_on (Sparkling
    Scales / Rocky Fighting Energy can block it)."""
    if (ctx.opp.active and not effect_prevented_on(ctx, ctx.opp.active)
            and can_be_conditioned(ctx.state, ctx.opp.active)):
        ctx.opp.active.confused = True
        ctx.state.emit(f"Mind Bend: {ctx.opp.active.card.name} is Confused")


def _shadow_bind(ctx: EffectContext) -> None:
    """Dusknoir: 150, and during the opponent's next turn they can't retreat."""
    ctx.opp.pending_cant_retreat = True
    ctx.state.emit("Shadow Bind: opponent can't retreat next turn")


def _itchy_pollen(ctx: EffectContext) -> None:
    """Budew: 10, and during the opponent's next turn they can't play Item cards."""
    ctx.opp.pending_cant_play_items = True
    ctx.state.emit("Itchy Pollen: opponent can't play Items next turn")


def _shellnado_spin(ctx: EffectContext) -> None:
    """Mega Slowbro ex: 180 (applied by the engine), and during the opponent's next
    turn, if this Pokémon is damaged by an attack — even if that damage Knocks it
    Out — place 12 damage counters on the attacking Pokémon. Set directly (like
    Dunsparce's Dig shield) rather than via the pending/active split, since it isn't
    a turn-scoped debuff on the opponent, it's a standing retaliation on THIS
    Pokémon that the opponent triggers by attacking into it."""
    ctx.source.retaliate = True
    ctx.state.emit(f"Shellnado Spin: {ctx.source.card.name} will retaliate next turn")


def _repulsor_axe(ctx: EffectContext) -> None:
    """Iron Boulder ex: 60 (applied by the engine), and during the opponent's next
    turn, if this Pokémon is damaged by an attack — even if it's Knocked Out — place
    8 damage counters on the attacker. Same standing-retaliation shape as Shellnado
    Spin, just a smaller count (8 vs. 12)."""
    ctx.source.retaliate = True
    ctx.source.retaliate_counters = 8
    ctx.state.emit(f"Repulsor Axe: {ctx.source.card.name} will retaliate for 8 next turn")


# --- §2.x remaining cards: accel / triggers / disruption / tail ---
def _excited_turbo(ctx: EffectContext) -> None:
    """Oricorio: attach a Basic Fire Energy from hand to a Benched Fire Pokémon
    (repeatable; gated on a Fire MEGA ex in play + a Fire Energy in hand)."""
    fire_benched = [m for m in ctx.me.bench if "Fire" in m.card.types]
    if not fire_benched:
        return
    target = min(fire_benched, key=lambda m: m.energy_count())   # least-loaded first
    if attach_basic_energy_from_hand(ctx, "Fire", target):
        ctx.state.emit(f"Excited Turbo: accelerated Fire onto {target.card.name}")


def _fan_call(ctx: EffectContext) -> None:
    """Fan Rotom: once on your first turn, search up to 3 Colorless Pokémon (≤100 HP)."""
    n = search_deck(ctx, [p_colorless_le100] * 3, dest="hand")
    if n:
        ctx.state.emit(f"Fan Call: searched {n} Colorless Pokémon")


def _last_ditch_catch(ctx: EffectContext) -> None:
    """Meowth ex on-bench trigger: search your deck for a Supporter, put it in hand."""
    if search_deck(ctx, [p_supporter], dest="hand"):
        ctx.state.emit("Last-Ditch Catch: searched a Supporter")


def _snow_sink(ctx: EffectContext) -> None:
    """Chien-Pao on-bench trigger: you may discard a Stadium in play. (First "discard
    the Stadium in play" effect — mirrors play_stadium's replace-logic in game.py but
    installs nothing. "May" auto-resolved to always-take, per the v0 optional-beneficial
    convention.)"""
    if ctx.state.stadium is not None and ctx.state.stadium_owner is not None:
        name = ctx.state.stadium.name
        outgoing_owner = ctx.state.stadium_owner
        ctx.state.players[ctx.state.stadium_owner].discard.append(ctx.state.stadium)
        ctx.state.stadium = None
        ctx.state.stadium_owner = None
        ctx.state.emit(f"Snow Sink: discarded Stadium {name}")
        # Snow Sink is the only Stadium-removal path outside apply_action's play_stadium
        # branch, and Snow Sink fires from play_basic, which never sweeps. Discarding
        # Area Zero Underdepths is its "when this card leaves play, both players discard
        # Pokémon from their Bench until they have 5, and the player who played this card
        # discards first" clause, so enforce it here too.
        enforce_bench_limits(ctx.state, first_index=outgoing_owner)


def _psychic_draw(ctx: EffectContext) -> None:
    """Alakazam on-evolve trigger: when played from hand to evolve, you may draw 3.
    (v0: always take the beneficial draw.)"""
    n = draw(ctx, 3)
    ctx.state.emit(f"Psychic Draw: drew {n}")


def _crushing_hammer(ctx: EffectContext) -> bool:
    """Flip a coin; if heads, discard an Energy from 1 of the opponent's Pokémon."""
    if flip(ctx):
        targets = [m for m in ctx.opp.all_in_play() if m.energy]
        if targets:
            victim = max(targets, key=lambda m: m.energy_count())   # strip the most-loaded
            e = victim.energy.pop()
            ctx.opp.discard.append(e)
            ctx.state.emit(f"Crushing Hammer: heads — discarded {e.name} from {victim.card.name}")
    else:
        ctx.state.emit("Crushing Hammer: tails")
    return True          # the card is used either way (the flip IS the effect)


def _unfair_stamp(ctx: EffectContext) -> bool:
    """ACE SPEC: each player shuffles hand into deck; you draw 5, opponent draws 2."""
    shuffle_hand_into_deck(ctx, ctx.me)
    shuffle_hand_into_deck(ctx, ctx.opp)
    ctx.me.draw(5)
    ctx.opp.draw(2)
    ctx.state.emit("Unfair Stamp: reset hands (you 5, opponent 2)")
    return True


def _fighting_wings(ctx: EffectContext) -> None:
    """Moltres: 20, +90 more if the opponent's Active is a Pokémon ex."""
    dmg = 20
    d = ctx.opp.active
    if d is not None and any(s.lower() == "ex" for s in d.card.subtypes):
        dmg += 90
    apply_attack_damage(ctx, d, dmg, owner=ctx.opp)


def _come_and_get_you(ctx: EffectContext) -> None:
    """Duskull: put up to 3 Duskull from your discard pile onto your Bench."""
    placed = 0
    for c in list(ctx.me.discard):
        if placed >= 3 or len(ctx.me.bench) >= bench_limit(ctx.state, ctx.me):
            break
        if c.name == "Duskull":
            ctx.me.discard.remove(c)
            ctx.me.bench.append(InPlayPokemon(card=c, played_this_turn=True))
            placed += 1
    if placed:
        ctx.state.emit(f"Come and Get You: benched {placed} Duskull")


def _dig(ctx: EffectContext) -> None:
    """Dunsparce: 30, flip a coin; if heads, prevent all damage & effects of attacks
    done to this Pokémon during the opponent's next turn."""
    if flip(ctx):
        ctx.source.shielded = True
        ctx.state.emit(f"Dig: heads — {ctx.source.card.name} is shielded next turn")


def _assault_landing(ctx: EffectContext) -> None:
    """Fan Rotom: 70, but does nothing if there is no Stadium in play."""
    if current_stadium_name(ctx.state) is not None:
        apply_attack_damage(ctx, ctx.opp.active, 70, owner=ctx.opp)


def _tuck_tail(ctx: EffectContext) -> None:
    """Meowth ex: 60 (applied by the engine), then put THIS Pokémon and all attached
    cards into your hand (removing it from play; promote if it was Active)."""
    mon = ctx.source
    me = ctx.me
    me.hand.append(mon.card)
    me.hand.extend(mon.energy)
    me.hand.extend(mon.evolved_from)
    if mon.tool is not None:
        me.hand.append(mon.tool)
    if me.active is mon:
        me.active = None
        if me.bench:
            me.bench.sort(key=lambda m: m.remaining_hp, reverse=True)
            me.active = me.bench.pop(0)
    else:
        me.bench = [m for m in me.bench if m is not mon]
    ctx.state.emit("Tuck Tail: returned Meowth ex (and attached) to hand")


def _stick_n_draw(ctx: EffectContext) -> None:
    """Klefki attack: discard a card from your hand; if you do, draw 2. (0 base.)"""
    me = ctx.me
    if me.hand:
        i = min(range(len(me.hand)), key=lambda i: _search_value(me.hand[i]))
        me.discard.append(me.hand.pop(i))
        draw(ctx, 2)
        ctx.state.emit("Stick 'n' Draw: discarded 1, drew 2")


# --------------------------------------------------------------------------- #
# feature/more-cards — new meta archetypes (Mega Gardevoir / Colorless / Fire).
# Variable-damage ("×"/"+") attacks: engine applies 0 base, the effect computes the
# whole hit via damage_active_with_weakness (so Weakness multiplies the total once).
# Fixed-damage attacks: engine applies the printed number, the effect adds the rider.
# --------------------------------------------------------------------------- #

# --- Mega Gardevoir ex line (Psychic) ---
def _collect(ctx: EffectContext) -> None:
    """Ralts: draw a card."""
    draw(ctx, 1)


def _call_sign(ctx: EffectContext) -> None:
    """Kirlia: search your deck for up to 3 Pokémon, put them into your hand."""
    n = search_deck(ctx, [p_pokemon] * 3, dest="hand")
    if n:
        ctx.state.emit(f"Call Sign: searched {n} Pokémon")


def _overflowing_wishes(ctx: EffectContext) -> None:
    """Mega Gardevoir ex: for each of your Benched Pokémon, search your deck for a
    Basic Psychic Energy and attach it to that Pokémon. (No damage.)"""
    attached = 0
    for mon in list(ctx.me.bench):
        for i, c in enumerate(ctx.me.deck):
            if c.is_basic_energy and "Psychic" in c.types:
                mon.energy.append(ctx.me.deck.pop(i))
                attached += 1
                break
    if ctx.rng:
        ctx.rng.shuffle(ctx.me.deck)
    if attached:
        ctx.state.emit(f"Overflowing Wishes: accelerated {attached} Psychic Energy")


def _mega_symphonia(ctx: EffectContext) -> None:
    """Mega Gardevoir ex: 50 damage for each Psychic Energy attached to all of your
    Pokémon. (Variable — engine applied 0 base.)"""
    n = sum(1 for m in ctx.me.all_in_play() for e in m.energy if "Psychic" in (e.types or []))
    damage_active_with_weakness(ctx, 50 * n)


def _garland_ray(ctx: EffectContext) -> None:
    """Mega Diancie ex: discard up to 2 Energy from this Pokémon; 120 damage each.
    (Variable.) v0: discard up to 2 for maximum damage."""
    src = ctx.source
    discarded = 0
    while discarded < 2 and src.energy:
        ctx.me.discard.append(src.energy.pop())
        discarded += 1
    damage_active_with_weakness(ctx, 120 * discarded)


def _twin_shotels(ctx: EffectContext) -> None:
    """Iron Crown ex: 50 damage to 2 of the opponent's Pokémon. Not affected by
    Weakness/Resistance or any effects on those Pokémon — so apply it directly."""
    opp_mons = ([ctx.opp.active] if ctx.opp.active else []) + list(ctx.opp.bench)
    targets = sorted(opp_mons, key=lambda m: m.remaining_hp)[:2]   # the 2 closest to KO
    for m in targets:
        m.damage += 50
    if targets:
        ctx.state.emit(f"Twin Shotels: 50 to {len(targets)} Pokémon")


def _eon_blade(ctx: EffectContext) -> None:
    """Latias ex: 200 (engine), and during your next turn this Pokémon can't attack."""
    ctx.source.pending_cannot_attack = True
    ctx.state.emit("Eon Blade: this Pokémon can't attack next turn")


def _orichalcum_fang(ctx: EffectContext) -> None:
    """Koraidon ex (ASC 121): 50+. "If any of your Pokémon were Knocked Out by
    damage from an attack during your opponent's last turn, this attack does 120
    more damage." "+" suffix + registered effect -> engine applies 0 base, this
    function owns the full hit, same shape as Fighting Wings."""
    dmg = 50
    if ctx.me.koed_last_turn:
        dmg += 120
    apply_attack_damage(ctx, ctx.opp.active, dmg, owner=ctx.opp)


def _impact_blow(ctx: EffectContext) -> None:
    """Koraidon ex (ASC 121): 200 (engine, flat/no suffix), then "During your next
    turn, this Pokémon can't use Impact Blow" — scoped to this attack only, not a
    full-Pokémon lock (Orichalcum Fang stays usable), same pattern as Mega Brave."""
    ctx.source.pending_locked_attacks.append("Impact Blow")


# --- Colorless toolbox ---
def _hyper_whirlpool(ctx: EffectContext) -> None:
    """Lugia ex: 140 (engine). Flip a coin until tails; for each heads, discard an
    Energy from the opponent's Active Pokémon."""
    heads = 0
    while heads < 20 and flip(ctx):
        heads += 1
    removed = 0
    for _ in range(heads):
        if ctx.opp.active and ctx.opp.active.energy:
            ctx.opp.discard.append(ctx.opp.active.energy.pop())
            removed += 1
    ctx.state.emit(f"Hyper Whirlpool: {heads} heads, discarded {removed} Energy")


def _toss_and_turn(ctx: EffectContext) -> None:
    """Snorlax ex: flip 3 coins; 120 damage for each heads. (Variable.)"""
    heads = sum(1 for _ in range(3) if flip(ctx))
    damage_active_with_weakness(ctx, 120 * heads)


def _break_through(ctx: EffectContext) -> None:
    """Cyclizar ex: 130 (engine), and 30 to 1 of the opponent's Benched Pokémon."""
    if ctx.opp.bench:
        t = min(ctx.opp.bench, key=lambda m: m.remaining_hp)
        apply_attack_damage(ctx, t, 30, owner=ctx.opp)


def _zircon_road(ctx: EffectContext) -> None:
    """Cyclizar ex: 180 (engine), and you may draw 5 cards."""
    draw(ctx, 5)


def _run_errand(ctx: EffectContext) -> None:
    """Mega Kangaskhan ex (ability): if Active, draw 2 cards (once per turn)."""
    draw(ctx, 2)
    ctx.state.emit("Run Errand: drew 2")


def _rapid_fire_combo(ctx: EffectContext) -> None:
    """Mega Kangaskhan ex: 200 + 50 for each heads, flipping until tails. (Variable.)"""
    heads = 0
    while heads < 20 and flip(ctx):
        heads += 1
    damage_active_with_weakness(ctx, 200 + 50 * heads)


def _unified_beatdown(ctx: EffectContext) -> None:
    """Terapagos ex: 30 damage for each of your Benched Pokémon. (Variable.)"""
    damage_active_with_weakness(ctx, 30 * len(ctx.me.bench))


# --- Fire ---
def _scorching_fire(ctx: EffectContext) -> None:
    """Reshiram ex: 200 (engine), then discard an Energy from this Pokémon."""
    if ctx.source.energy:
        ctx.me.discard.append(ctx.source.energy.pop())


def _scorching_cyclone(ctx: EffectContext) -> None:
    """Volcanion ex: 160 (engine), then move an Energy from this Pokémon to 1 of
    your Benched Pokémon (v0: the least-loaded bencher)."""
    if ctx.source.energy and ctx.me.bench:
        target = min(ctx.me.bench, key=lambda m: m.energy_count())
        target.energy.append(ctx.source.energy.pop())
        ctx.state.emit(f"Scorching Cyclone: moved Energy to {target.card.name}")


def _shining_feathers(ctx: EffectContext) -> None:
    """Ethan's Ho-Oh ex: 160 (engine), then heal 50 damage from each of your Pokémon."""
    for m in ctx.me.all_in_play():
        heal(ctx, m, 50)
    ctx.state.emit("Shining Feathers: healed 50 from each of your Pokémon")


# --- Lightning ---
def _linked_lightning(ctx: EffectContext) -> None:
    """Tapu Koko ex: 60 + 20 for each of your Benched Pokémon. (Variable.)"""
    damage_active_with_weakness(ctx, 60 + 20 * len(ctx.me.bench))


# --------------------------------------------------------------------------- #
# feature/more-decks — Fighting / Dark / Metal / Water archetypes.
# --------------------------------------------------------------------------- #
def _attach_basic_from_discard(ctx: EffectContext, etype: str, target: InPlayPokemon,
                               upto: int) -> int:
    """Attach up to `upto` Basic <etype> Energy from your discard pile to `target`."""
    n = 0
    for c in list(ctx.me.discard):
        if n >= upto:
            break
        if c.is_basic_energy and etype in c.types:
            ctx.me.discard.remove(c)
            target.energy.append(c)
            n += 1
    return n


# --- Fighting (Mega Lucario) ---
def _aura_jab(ctx: EffectContext) -> None:
    """Mega Lucario ex: 130 (engine), then attach up to 3 Basic Fighting Energy from
    your discard pile to your Benched Pokémon."""
    placed = 0
    for mon in ctx.me.bench:
        if placed >= 3:
            break
        placed += _attach_basic_from_discard(ctx, "Fighting", mon, 3 - placed)
    if placed:
        ctx.state.emit(f"Aura Jab: attached {placed} Fighting Energy from discard")


def _regi_charge(ctx: EffectContext) -> None:
    """Regirock ex: attach up to 2 Basic Fighting Energy from discard to this Pokémon."""
    n = _attach_basic_from_discard(ctx, "Fighting", ctx.source, 2)
    if n:
        ctx.state.emit(f"Regi Charge: attached {n} Fighting Energy from discard")


def _giant_rock(ctx: EffectContext) -> None:
    """Regirock ex: 140, +140 more if the opponent's Active is a Stage 2. (Variable.)"""
    dmg = 140
    if ctx.opp.active and "Stage 2" in ctx.opp.active.card.subtypes:
        dmg += 140
    damage_active_with_weakness(ctx, dmg)


def _power_stomp(ctx: EffectContext) -> None:
    """Iron Boulder ex: 200 (engine), then discard 2 Energy from this Pokémon."""
    for _ in range(2):
        if ctx.source.energy:
            ctx.me.discard.append(ctx.source.energy.pop())


def _retribution_strike(ctx: EffectContext) -> None:
    """Koraidon ex: 20 + 10 for each damage counter on this Pokémon. (Variable.)"""
    damage_active_with_weakness(ctx, 20 + (ctx.source.damage // 10) * 10)


def _kaiser_tackle(ctx: EffectContext) -> None:
    """Koraidon ex: 280 (engine), and this Pokémon does 60 damage to itself."""
    ctx.source.damage += 60


# --- Dark (Mega Absol) ---
def _terminal_period(ctx: EffectContext) -> None:
    """Mega Absol ex: if the opponent's Active has EXACTLY 6 damage counters (60),
    it is Knocked Out. (No base damage; process_knockouts sweeps it.)"""
    t = ctx.opp.active
    if t is not None and t.damage == 60:
        t.damage = t.card.hp or 9999
        ctx.state.emit("Terminal Period: KO (exactly 6 damage counters)")


def _claw_of_darkness(ctx: EffectContext) -> None:
    """Mega Absol ex: 200 (engine), then discard a card from the opponent's hand
    (v0: the highest-value card — deterministic disruption)."""
    if ctx.opp.hand:
        i = max(range(len(ctx.opp.hand)), key=lambda i: _search_value(ctx.opp.hand[i]))
        c = ctx.opp.hand.pop(i)
        ctx.opp.discard.append(c)
        ctx.state.emit(f"Claw of Darkness: discarded {c.name} from opponent's hand")


# --- Metal (Mega Mawile) ---
def _gobble_down(ctx: EffectContext) -> None:
    """Mega Mawile ex: 80 damage for each Prize card you have taken. (Variable.)"""
    taken = 6 - len(ctx.me.prizes)
    damage_active_with_weakness(ctx, 80 * taken)


def _huge_bite(ctx: EffectContext) -> None:
    """Mega Mawile ex: 260, but if the opponent's Active already has any damage on it
    this attack's base is only 30. (Owns its damage — conditional base.)"""
    base = 30 if (ctx.opp.active and ctx.opp.active.damage > 0) else 260
    damage_active_with_weakness(ctx, base)


def _insta_strike(ctx: EffectContext) -> None:
    """Hop's Zacian ex: 30 (engine), and 30 to 1 of the opponent's Benched Pokémon."""
    if ctx.opp.bench:
        t = min(ctx.opp.bench, key=lambda m: m.remaining_hp)
        apply_attack_damage(ctx, t, 30, owner=ctx.opp)


# --- Water (Dondozo / Lapras) ---
def _avenging_billow(ctx: EffectContext) -> None:
    """Dondozo ex: 30 + 10 for each damage counter on this Pokémon. (Variable.)"""
    damage_active_with_weakness(ctx, 30 + (ctx.source.damage // 10) * 10)


def _full_moon_rondo(ctx: EffectContext) -> None:
    """Lillie's Clefairy ex: 20 + 20 for each Benched Pokémon, both yours and your
    opponent's. (Variable — engine applied 0 base.)"""
    bench_count = len(ctx.me.bench) + len(ctx.opp.bench)
    damage_active_with_weakness(ctx, 20 + 20 * bench_count)


def _icicle_loop(ctx: EffectContext) -> None:
    """Chien-Pao: put an Energy attached to this Pokémon into your hand. (120 fixed
    base, engine-applied — this is only the self-energy-recycling rider.)"""
    if ctx.source and ctx.source.energy:
        ctx.me.hand.append(ctx.source.energy.pop())
        ctx.state.emit("Icicle Loop: returned an Energy to hand")


def _dynamic_dive(ctx: EffectContext) -> None:
    """Dondozo ex: 120, and you may do 120 more (then 50 to itself). v0: always take
    the extra for maximum damage. (Variable — engine applied 0 base.)"""
    damage_active_with_weakness(ctx, 240)
    ctx.source.damage += 50


def _power_splash(ctx: EffectContext) -> None:
    """Lapras ex: 40 damage for each Energy attached to this Pokémon. (Variable.)"""
    damage_active_with_weakness(ctx, 40 * ctx.source.energy_count())


def _mega_brave(ctx: EffectContext) -> None:
    """Mega Lucario ex: 270 (engine), then this Pokémon can't use Mega Brave next turn."""
    ctx.source.pending_locked_attacks.append("Mega Brave")


def _brave_slash(ctx: EffectContext) -> None:
    """Hop's Zacian ex: 240 (engine), then this Pokémon can't use Brave Slash next turn."""
    ctx.source.pending_locked_attacks.append("Brave Slash")


# --- Mega Greninja ex (Water, Stage 2 MEGA) — snipe/spread board control ---
def _mortal_shuriken(ctx: EffectContext) -> None:
    """Ability: discard a Basic Water Energy from hand, then place 6 damage counters
    (60) on 1 of the opponent's Pokémon. v0 targeting: snipe a KO if one is reachable
    (prefer most prizes / lowest HP), else pile onto the Active."""
    me = ctx.me
    for i, c in enumerate(me.hand):                    # pay the cost: discard 1 Basic Water
        if c.is_basic_energy and "Water" in c.types:
            me.discard.append(me.hand.pop(i))
            break
    else:
        return                                         # no Water to discard (can_use guards this)
    target = _pick_ko_target(ctx.opp, 60) or ctx.opp.active
    if target is not None:
        placed = place_counters(ctx, target, 6, owner=ctx.opp)   # Battle Cage may block on bench
        if placed:
            ctx.state.emit(f"Mortal Shuriken: 60 to {target.card.name}")


def _ninja_spinner(ctx: EffectContext) -> None:
    """Mega Greninja ex: 120, and you MAY return a Water Energy attached to this
    Pokémon to your hand for +80 (-> 200). v0: take the +80 only if we'd still keep
    enough Energy attached to attack next turn — and the returned Water feeds Mortal
    Shuriken's discard cost. (Variable — engine applied 0 base.)"""
    src = ctx.source
    dmg = 120
    water = [e for e in src.energy if e.is_basic_energy and "Water" in e.types]
    if water and src.energy_count() >= 3:             # keep 2 attached for next turn's WW
        src.energy.remove(water[0])
        ctx.me.hand.append(water[0])
        dmg += 80
    damage_active_with_weakness(ctx, dmg)


# --- Beedrill ex (Grass swarm) — a real-meta counter to Fighting, per a live game ---
def _rumbling_bees(ctx: EffectContext) -> None:
    """Beedrill ex: 110 damage for each of your Beedrill / Beedrill ex in play.
    (Variable — engine applied 0 base.) The swarm scales hard and the deck rebuilds
    Beedrill repeatedly, which is what beats single-attacker decks."""
    n = sum(1 for m in ctx.me.all_in_play() if "Beedrill" in m.card.name)
    damage_active_with_weakness(ctx, 110 * n)


def _surprise_attack(ctx: EffectContext) -> None:
    """Weedle: flip a coin; if heads, 30 damage (if tails, nothing). Owns its damage
    so a tails really does 0 (the engine doesn't pre-apply the printed 30)."""
    if flip(ctx):
        damage_active_with_weakness(ctx, 30)


# --- Destined Rivals / Twilight Masquerade: "damage isn't affected by any effects
# on your opponent's Active Pokémon" (shield/wall bypass). These own their damage so
# the engine applies 0 base and the effect lands the whole hit with the bypass flag.
def _superb_scissors(ctx: EffectContext) -> None:
    """Crustle: 120; damage isn't affected by any effects on the opponent's Active
    (ignores shields and damage-prevention Abilities on the target). W/R still apply."""
    apply_attack_damage(ctx, ctx.opp.active, 120, owner=ctx.opp, source=ctx.source,
                        ignore_active_effects=True)


def _demolish(ctx: EffectContext) -> None:
    """Cornerstone Mask Ogerpon ex: 140; damage isn't affected by Weakness/Resistance
    or by any effects on the opponent's Active Pokémon."""
    apply_attack_damage(ctx, ctx.opp.active, 140, owner=ctx.opp, source=ctx.source,
                        ignore_active_effects=True, ignore_weakness=True,
                        ignore_resistance=True)


def _blood_moon(ctx: EffectContext) -> None:
    """Bloodmoon Ursaluna ex: 240 (engine), and during your next turn this Pokémon
    can't attack. (The Colorless cost discount lives in effective_cost / Seasoned Skill.)"""
    ctx.source.pending_cannot_attack = True
    ctx.state.emit("Blood Moon: this Pokémon can't attack next turn")


# --- Mega Starmie ex (Water, Stage 1 MEGA) — Perfect Order snipe + wall-bypass ---
def _jetting_blow(ctx: EffectContext) -> None:
    """Mega Starmie ex: 120 to the Active (engine-applied), and 50 to 1 of the
    opponent's Benched Pokémon (no Weakness/Resistance — the on_bench path in
    apply_attack_damage already skips W/R for a benched target). v0 target policy:
    the bencher closest to a KO (mirrors Break Through / Insta-Strike / gust)."""
    if ctx.opp.bench:
        victim = min(ctx.opp.bench, key=lambda m: m.remaining_hp)
        apply_attack_damage(ctx, victim, 50, owner=ctx.opp, source=ctx.source)


def _nebula_beam(ctx: EffectContext) -> None:
    """Mega Starmie ex: 210; damage isn't affected by Weakness/Resistance or by any
    effects on the opponent's Active — so it bypasses Mysterious Rock Inn (Crustle),
    Sparkling Scales (Milotic ex) and Cornerstone Stance (Cornerstone Ogerpon ex)
    via the SAME chokepoint flags Superb Scissors/Demolish use (owns its damage)."""
    apply_attack_damage(ctx, ctx.opp.active, 210, owner=ctx.opp, source=ctx.source,
                        ignore_active_effects=True, ignore_weakness=True,
                        ignore_resistance=True)


# --- Frogadier / Froakie (Water evolution line; Mega Greninja ex pre-evolutions) ---
def _numbing_water(ctx: EffectContext) -> None:
    """Frogadier: 20 (engine-applied). Flip a coin; if heads the opponent's Active
    would be Paralyzed. The flip is taken faithfully (through ctx.rng, so clone/
    determinize stay reproducible), but this engine models no Paralysis Special
    Condition (only Confusion + the can't-retreat/can't-play-Items riders exist) —
    same disclosed gap as Milotic ex's Hypno Splash Sleep. No new condition system
    is built here (out of scope); the heads branch is a logged no-op."""
    if flip(ctx):
        ctx.state.emit("Numbing Water: heads — opponent's Active would be Paralyzed "
                       "(Paralysis not modeled in this engine; no effect applied)")
    else:
        ctx.state.emit("Numbing Water: tails")


def _flock(ctx: EffectContext) -> None:
    """Froakie: search your deck for up to 2 Froakie, put them onto your Bench, then
    shuffle. (0 base damage; bench-only Basic search, respects bench space + shuffles
    via search_deck — the same primitive Call Sign / Fan Call use.)"""
    n = search_deck(ctx, [lambda c: c.name == "Froakie"] * 2, dest="bench")
    if n:
        ctx.state.emit(f"Flock: benched {n} Froakie")


# --------------------------------------------------------------------------- #
# Stellar Crown / Surging Sparks / Twilight Masquerade / Shrouded Fable line —
# Slowking (attack-copy), Ogerpon Box, Dragon toolbox, Metal/Lightning attackers.
# --------------------------------------------------------------------------- #

# Seek-value of a copyable attack: what Seek Inspiration's chooser (and the greedy
# Academy at Night top-deck policy in agents.py) believes an attack is worth. Printed
# flat damage by default; the overrides exist for attacks whose whole payoff is a
# registered effect with 0 printed damage, which the flat-damage heuristic would
# otherwise never pick. Values are HEURISTIC RANKS for deterministic selection, not
# damage claims: Destined Fight (KOs both Actives — routinely a 2-or-3-prize swing
# for a 1-prize Slowking) outranks every flat number in the current pool; Trifrost's
# 110×3 spread is ranked above its printed 110 but below the guaranteed double KO.
SEEK_VALUE_OVERRIDES: dict[tuple[str, str], int] = {
    ("Annihilape", "Destined Fight"): 400,
    ("Kyurem", "Trifrost"): 250,
}


def seek_value(card: "Card", attack: "Attack") -> int:
    return SEEK_VALUE_OVERRIDES.get((card.name, attack.name), attack.damage)


def _seek_inspiration(ctx: EffectContext) -> None:
    """Slowking: discard the top card of your deck; if it's a Pokémon WITHOUT a Rule
    Box, pick its highest-printed-damage attack and use it as this attack.

    If the copied (card, attack) has a registered ATTACK_EFFECTS entry, that effect
    is genuinely invoked (same owns_damage/base-damage sequencing as the main
    _resolve_attack dispatcher — see game.py) — so a copied Trifrost really discards
    Slowking's own Energy and hits 3 Pokémon for 110, a copied Luster Blast really
    discards 2 Energy from Slowking, etc. This is also the rules-correct reading of
    "use it as this attack": the attack's own costs/effects apply to whoever is now
    using it, not to the (discarded, out-of-play) original card. Weakness/Resistance
    still key off Slowking's own type via the chokepoint regardless.

    v0 LIMITATION (documented): if the copied attack has NO registered effect, only
    its printed base damage lands (no rider). Any non-Pokémon / Rule-Box / no-attack /
    zero-value discard is a real miss (the card is still discarded, nothing else
    happens). The attack-choice heuristic is highest SEEK VALUE (printed flat damage,
    overridable per-attack via SEEK_VALUE_OVERRIDES for attacks whose payoff lives in
    a 0-printed-damage registered effect — Destined Fight's double KO would otherwise
    lose the pick to Tantrum's flat 130 on the same card)."""
    me = ctx.me
    if not me.deck:
        ctx.state.emit("Seek Inspiration: deck is empty")
        return
    card = me.deck.pop(0)
    me.discard.append(card)
    ctx.state.emit(f"Seek Inspiration: discarded {card.name}")
    if not (card.is_pokemon and not _has_rule_box(card)) or not card.attacks:
        return                          # Trainer/Energy, Rule-Box mon, or Ability-only -> miss
    chosen = max(card.attacks, key=lambda a: seek_value(card, a))  # deterministic: fixed pool order
    key = (card.name, chosen.name)
    copied_effect = ATTACK_EFFECTS.get(key)
    owns_damage = key in ATTACK_EFFECT_OWNS_DAMAGE
    base = 0 if (copied_effect is not None
                and (chosen.damage_suffix in ("+", "×") or owns_damage)) else chosen.damage
    if base <= 0 and copied_effect is None:
        return                          # genuine miss: no effect, no positive flat damage
    if base > 0 and ctx.opp.active is not None:
        dealt = apply_attack_damage(ctx, ctx.opp.active, base, owner=ctx.opp, source=ctx.source)
        ctx.state.emit(f"Seek Inspiration: used {card.name}'s {chosen.name} for {dealt}")
    if copied_effect is not None:
        copied_effect(ctx)
        ctx.state.emit(f"  effect: {chosen.name} (via Seek Inspiration)")


def _dangle_tail(ctx: EffectContext) -> None:
    """Slowpoke: put a Pokémon from your discard pile into your hand. (0 base.)"""
    if recover_from_discard(ctx, [p_pokemon]):
        ctx.state.emit("Dangle Tail: recovered a Pokémon from discard")


def _trifrost(ctx: EffectContext) -> None:
    """Kyurem: discard all Energy from this Pokémon, then 110 damage to 3 of the
    opponent's Pokémon (no Weakness/Resistance for Benched — the chokepoint skips it).
    v0 target policy: the 3 closest to a KO."""
    src = ctx.source
    if src is not None:
        while src.energy:
            ctx.me.discard.append(src.energy.pop())
    targets = sorted(ctx.opp.all_in_play(), key=lambda m: m.remaining_hp)[:3]
    for m in targets:
        apply_attack_damage(ctx, m, 110, owner=ctx.opp, source=ctx.source)
    if targets:
        ctx.state.emit(f"Trifrost: 110 to {len(targets)} Pokémon")


def _luster_blast(ctx: EffectContext) -> None:
    """Metagross: 200 (engine), then discard 2 Energy from this Pokémon."""
    for _ in range(2):
        if ctx.source.energy:
            ctx.me.discard.append(ctx.source.energy.pop())


def _tantrum(ctx: EffectContext) -> None:
    """Annihilape: 130 (engine), then "This Pokémon is now Confused" — SELF-confuse
    (the attacker, not the Defending Pokémon), so a copied Tantrum confuses Slowking."""
    if ctx.source is not None and can_be_conditioned(ctx.state, ctx.source):
        ctx.source.confused = True
        ctx.state.emit(f"Tantrum: {ctx.source.card.name} is now Confused")


def _destined_fight(ctx: EffectContext) -> None:
    """Annihilape: "Both Active Pokémon are Knocked Out." An effect-KO, not damage —
    no Weakness/Resistance, no damage-prevention walls, no Tera/Flower Curtain bench
    logic (both targets are Active by definition), and prizes (incl. the MEGA 3-prize
    rule and the self-KO award) are the caller's process_knockouts sweep's job.

    The opponent's Active gets the shared effect-prevention gate (Hide 'n' Sneak,
    Mist Energy, ...: "prevent all effects of your opponent's attacks done to this
    Pokémon" genuinely blocks an effect-KO). Your own Active is NOT gated — those
    preventions read "your opponent's Pokémon", and this Pokémon is its own side's."""
    opp_active = ctx.opp.active
    if opp_active is not None and not effect_prevented_on(ctx, opp_active):
        opp_active.damage = opp_active.max_hp
        ctx.state.emit(f"Destined Fight: {opp_active.card.name} is Knocked Out")
    if ctx.source is not None:
        ctx.source.damage = ctx.source.max_hp
        ctx.state.emit(f"Destined Fight: {ctx.source.card.name} is Knocked Out")


def _delightful_kiss(ctx: EffectContext) -> None:
    """Smoochum: "Search your deck for up to 2 Basic Psychic Energy cards and attach
    them to 1 of your Benched Pokémon. Then, shuffle your deck." ONE benched target
    gets both cards. v0 target policy (a hook MCTS can own): the least-loaded benched
    Psychic Pokémon — that's the Slowking/Kyurem fuel this attack exists to stock —
    falling back to the least-loaded benched Pokémon of any type."""
    me = ctx.me
    if not me.bench:
        return
    found = []
    for i in range(len(me.deck) - 1, -1, -1):
        if len(found) == 2:
            break
        c = me.deck[i]
        if c.is_basic_energy and "Psychic" in c.types:
            found.append(me.deck.pop(i))
    if ctx.rng:
        ctx.rng.shuffle(me.deck)
    if not found:
        ctx.state.emit("Delightful Kiss: no Basic Psychic Energy in deck")
        return
    cands = [m for m in me.bench if "Psychic" in m.card.types] or me.bench
    target = min(cands, key=lambda m: m.energy_count())
    target.energy.extend(found)
    ctx.state.emit(f"Delightful Kiss: attached {len(found)} Basic Psychic Energy "
                   f"to benched {target.card.name}")


def _strong_volt(ctx: EffectContext) -> None:
    """Zeraora: 120 (engine), then discard an Energy from this Pokémon."""
    if ctx.source.energy:
        ctx.me.discard.append(ctx.source.energy.pop())


def _shocking_knuckle(ctx: EffectContext) -> None:
    """Zeraora: 20 (engine). Flip a coin; if heads the opponent's Active would be
    Paralyzed. The flip is taken faithfully (ctx.rng, so clone/determinize stay
    reproducible), but this engine models no Paralysis Special Condition (same disclosed
    gap as Frogadier's Numbing Water) — the heads branch is a logged no-op."""
    if flip(ctx):
        ctx.state.emit("Shocking Knuckle: heads — opponent's Active would be Paralyzed "
                       "(Paralysis not modeled in this engine; no effect applied)")
    else:
        ctx.state.emit("Shocking Knuckle: tails")


def _sob(ctx: EffectContext) -> None:
    """Wellspring Mask Ogerpon ex: 20 (engine), and during the opponent's next turn the
    Defending Pokémon can't retreat. (Same one-turn rider as Dusknoir's Shadow Bind.)"""
    ctx.opp.pending_cant_retreat = True
    ctx.state.emit("Sob: opponent can't retreat next turn")


def _torrential_pump(ctx: EffectContext) -> None:
    """Wellspring Mask Ogerpon ex: 100 (engine). You MAY shuffle 3 Energy attached to
    this Pokémon into your deck; if you do, this attack also does 120 to 1 of the
    opponent's Benched Pokémon (no W/R for Benched — the chokepoint skips it). v0: take
    the shuffle only when there IS a benched target to hit (otherwise keep the Energy —
    stripping the attacker for nothing is never the beneficial branch)."""
    src = ctx.source
    if src is not None and ctx.opp.bench and src.energy_count() >= 3:
        for _ in range(3):
            ctx.me.deck.append(src.energy.pop())
        if ctx.rng:
            ctx.rng.shuffle(ctx.me.deck)
        victim = min(ctx.opp.bench, key=lambda m: m.remaining_hp)
        apply_attack_damage(ctx, victim, 120, owner=ctx.opp, source=ctx.source)
        ctx.state.emit("Torrential Pump: shuffled 3 Energy, 120 to a benched Pokémon")


def _poison_chain(ctx: EffectContext) -> None:
    """Pecharunt: 10 (engine). The opponent's Active is Poisoned (Poison is not modeled
    in this engine — logged no-op), and during the opponent's next turn it can't retreat
    (the modeled rider)."""
    ctx.opp.pending_cant_retreat = True
    ctx.state.emit("Poison Chain: opponent can't retreat next turn "
                   "(Poison not modeled in this engine)")


def _allure(ctx: EffectContext) -> None:
    """Chi-Yu: draw 2 cards. (0 base.)"""
    draw(ctx, 2)


def _ground_melter(ctx: EffectContext) -> None:
    """Chi-Yu: 60, +60 more if a Stadium is in play; then discard that Stadium.
    (Variable '+': the engine applies 0 base and the effect lands the whole hit so
    Weakness multiplies the total once.)"""
    dmg = 60
    if current_stadium_name(ctx.state) is not None:
        dmg += 60
    damage_active_with_weakness(ctx, dmg)
    if ctx.state.stadium is not None and ctx.state.stadium_owner is not None:
        name = ctx.state.stadium.name
        ctx.state.players[ctx.state.stadium_owner].discard.append(ctx.state.stadium)
        ctx.state.stadium = None
        ctx.state.stadium_owner = None
        ctx.state.emit(f"Ground Melter: discarded Stadium {name}")


# --------------------------------------------------------------------------- #
# Pitch Black-era Metal / Mega Excadrill ex line (Beldum -> Metang -> Metagross,
# Drilbur -> Mega Excadrill ex, Genesect ex, Ethan's Pichu).
# --------------------------------------------------------------------------- #
def p_evolution_metal_pokemon(c) -> bool:
    """An "Evolution Metal Pokémon" (Genesect ex's Metallic Signal): a Metal-type
    Pokémon that evolves from something (Stage 1 or Stage 2 — both are Evolution
    Pokémon)."""
    return c.is_pokemon and c.evolves_from is not None and "Metal" in c.types


def _iron_tackle(ctx: EffectContext) -> None:
    """Beldum (TEF 113): 50 (engine-applied), "This Pokémon also does 10 damage to
    itself." Self-damage from your own attack isn't damage "done by an attack" to a
    Pokémon you're attacking — it isn't affected by Weakness/Resistance or by shields —
    so it lands directly, same as Koraidon ex's Kaiser Tackle."""
    ctx.source.damage += 10
    ctx.state.emit("Iron Tackle: 10 damage to itself")


def _metal_maker(ctx: EffectContext) -> None:
    """Metang (SVP 90) Ability: "Once during your turn, you may look at the top 4 cards
    of your deck and attach any number of Basic Metal Energy cards you find there to your
    Pokémon in any way you like. Shuffle the other cards and put them on the bottom of
    your deck."

    Every Basic Metal Energy in the window is attached ("any number" -> all of them; it
    is pure upside). v0 distribution policy ("in any way you like", a hook MCTS can own):
    load the Active — that's the attacker this deck is powering up (Maximum Drilling wants
    5 Energy on one Pokémon) — and fall back to the least-loaded Benched Pokémon when
    there is no Active. The leftovers are shuffled and go to the BOTTOM of the deck (they
    are NOT shuffled into the deck)."""
    me = ctx.me
    window = [me.deck.pop(0) for _ in range(min(4, len(me.deck)))]
    if not window:
        return
    attached = 0
    leftovers = []
    for c in window:
        if c.is_basic_energy and "Metal" in c.types:
            target = me.active or (min(me.bench, key=lambda m: m.energy_count())
                                   if me.bench else None)
            if target is not None:
                target.energy.append(c)
                attached += 1
                continue
        leftovers.append(c)
    if ctx.rng:
        ctx.rng.shuffle(leftovers)
    me.deck.extend(leftovers)          # "put them on the bottom of your deck"
    ctx.state.emit(f"Metal Maker: attached {attached} Basic Metal Energy, bottomed "
                   f"{len(leftovers)}")


def _meteor_mash(ctx: EffectContext) -> None:
    """Metagross (TEF 115): "60. During your next turn, this Pokémon's Meteor Mash attack
    does 60 more damage (before applying Weakness and Resistance)."

    Owns its damage: the printed 60 is a flat number the engine would auto-apply, but the
    real hit is 60 OR 120 depending on a flag the engine can't see — the same reason
    Mega Mawile ex's Huge Bite owns its (conditional, flat-printed) damage. The buff is
    applied BEFORE Weakness/Resistance because damage_active_with_weakness passes the
    whole total through the W/R chokepoint once.

    The +60 is then armed for the OWNER's next turn via pending_boosted_attacks (promoted
    by start_turn), and it is re-armed every time the attack is used, so consecutive
    Meteor Mashes each hit for 120 — it does NOT stack beyond +60 (the card grants a
    fixed "60 more", not a per-use increment)."""
    src = ctx.source
    dmg = 60 + src.boosted_attacks.get("Meteor Mash", 0)
    damage_active_with_weakness(ctx, dmg)
    src.pending_boosted_attacks["Meteor Mash"] = 60
    ctx.state.emit(f"Meteor Mash: {dmg} damage; +60 on this Pokémon's next Meteor Mash")


def _dig_dig_dig(ctx: EffectContext) -> None:
    """Drilbur (TEF 85) Ability, on-bench trigger: "When you play this Pokémon from your
    hand onto your Bench during your turn, you may search your deck for up to 3 Basic
    Fighting Energy cards and discard them. Then, shuffle your deck." (Discarding them is
    the point — it feeds Fighting-Energy-from-discard recursion. v0 takes the search
    whenever there is anything to find, per the optional-beneficial convention.)"""
    me = ctx.me
    found = 0
    for c in list(me.deck):
        if found >= 3:
            break
        if c.is_basic_energy and "Fighting" in c.types:
            me.deck.remove(c)
            me.discard.append(c)
            found += 1
    if ctx.rng:
        ctx.rng.shuffle(me.deck)
    if found:
        ctx.state.emit(f"Dig Dig Dig: discarded {found} Basic Fighting Energy from deck")


def _metallic_signal(ctx: EffectContext) -> None:
    """Genesect ex (Black Bolt 67) Ability: "Once during your turn, you may search your
    deck for up to 2 Evolution Metal Pokémon, reveal them, and put them into your hand.
    Then, shuffle your deck." """
    n = search_deck(ctx, [p_evolution_metal_pokemon] * 2, dest="hand")
    if n:
        ctx.state.emit(f"Metallic Signal: searched {n} Evolution Metal Pokémon")


def _protect_charge(ctx: EffectContext) -> None:
    """Genesect ex: 150 (engine-applied), "During your opponent's next turn, this Pokémon
    takes 30 less damage from attacks (after applying Weakness and Resistance)." Set
    directly on this Pokémon (like Dunsparce's Dig shield / Shellnado Spin's retaliation)
    and cleared at the start of the OWNER's next turn, so it covers exactly the
    opponent's one intervening turn. The subtraction happens after W/R inside
    apply_attack_damage."""
    ctx.source.damage_reduction = 30
    ctx.state.emit("Protect Charge: takes 30 less damage during the opponent's next turn")


def _zapping_draw(ctx: EffectContext) -> None:
    """Ethan's Pichu (DRI 71): 30 (engine-applied) for no Energy, "Draw a card." """
    draw(ctx, 1)


def _undermine(ctx: EffectContext) -> None:
    """Mega Excadrill ex (PBL 65): 90 (engine-applied), "Discard the top 2 cards of your
    opponent's deck." """
    discard_opponent_deck_top(ctx, 2)
    ctx.state.emit("Undermine: discarded the top 2 cards of the opponent's deck")


def _maximum_drilling(ctx: EffectContext) -> None:
    """Mega Excadrill ex (PBL 65): "200+ — If this Pokémon has at least 2 extra Energy
    attached (in addition to this attack's cost), this attack does 130 more damage."

    The cost is [M][M][M], so "2 extra" means 5+ Energy attached in total -> 330. Printed
    as "200+", i.e. variable damage, so the engine applies 0 base and this effect lands
    the whole hit through the W/R chokepoint once — the same shape as Regirock ex's Giant
    Rock ("140+", +140 vs a Stage 2). (Energy that provides more than one unit is not
    modeled anywhere in this engine, so "extra Energy" counts attached CARDS.)"""
    dmg = 200
    if ctx.source is not None and ctx.source.energy_count() >= 5:
        dmg += 130
    damage_active_with_weakness(ctx, dmg)


def _call_for_family(ctx: EffectContext) -> None:
    """Drilbur (PBL 46, the real tournament-list print — NOT "Drilbur (TEF)"): "Search
    your deck for up to 2 Basic Pokémon and put them onto your Bench. Then, shuffle your
    deck." Mirrors Precious Trolley's search_deck call, capped at 2 and remaining Bench
    space instead of unlimited."""
    space = min(2, bench_limit(ctx.state, ctx.me) - len(ctx.me.bench))
    if space <= 0:
        return
    n = search_deck(ctx, [p_basic_pokemon] * space, dest="bench")
    if n:
        ctx.state.emit(f"Call for Family: benched {n} Basic Pokémon")


def _bounce_back(ctx: EffectContext) -> None:
    """Metagross (CRI 61) M Bounce Back: 60 (engine-applied). "Switch out your opponent's
    Active Pokémon to the Bench. (Your opponent chooses the new Active Pokémon.)" Reuses
    _promote's healthiest-bencher v0 policy — the exact mechanism already used any time a
    KO forces a replacement, which is what "opponent chooses" models here too. The forced
    switch is an EFFECT of the attack done to that Pokémon, so it goes through
    effect_prevented_on (Sparkling Scales / Rocky Fighting Energy can block it)."""
    opp = ctx.opp
    if effect_prevented_on(ctx, opp.active):
        ctx.state.emit("M Bounce Back: the switch-out was prevented")
        return
    if opp.active is not None and opp.bench:
        victim = opp.active
        opp.bench.append(victim)
        opp.active = None
        _promote(opp)
        ctx.state.emit(f"M Bounce Back: switched {victim.card.name} to the Bench")


def _metallic_hammer(ctx: EffectContext) -> None:
    """Metagross (CRI 61) Metallic Hammer: "150+ — You may discard 3 [M] Energy from this
    Pokémon and have this attack do 150 more damage" (150+150=300 total). Printed "150+",
    so the engine applies 0 base and this effect lands the whole hit (Giant Rock /
    Maximum Drilling precedent). v0 policy: take the optional discard whenever the source
    has >= 3 Metal Energy attached — mirrors Torrential Pump's "take it when it's
    straightforwardly beneficial" (this deck's 2x Energy Recycler + Metal Maker make
    refueling cheap) — a hook MCTS will later own."""
    src = ctx.source
    dmg = 150
    if src is not None:
        metal_energy = [e for e in src.energy if "Metal" in e.types]
        if len(metal_energy) >= 3:
            for e in metal_energy[:3]:
                src.energy.remove(e)
                ctx.me.discard.append(e)
            dmg += 150
            ctx.state.emit("Metallic Hammer: discarded 3 Metal Energy for +150 damage")
    damage_active_with_weakness(ctx, dmg)


# --------------------------------------------------------------------------- #
# Mega Evolution-era Fighting: the Cynthia's Garchomp ex line (Cynthia's Gible ->
# Cynthia's Gabite -> Cynthia's Garchomp ex) plus the Cynthia's Roselia ->
# Cynthia's Roserade booster line and Cynthia's Spiritomb.
#
# Two of this archetype's pieces are NOT registry entries and live at chokepoints
# instead (see there): Cynthia's Roserade's "Cheer On to Glory" +30 (a passive, in
# apply_attack_damage next to Brave Bangle/Kieran) and Cynthia's Power Weight's
# +70 HP (a Tool, in TOOL_HP_MODIFIERS -> refresh_hp_modifiers).
# --------------------------------------------------------------------------- #
def _rock_hurl(ctx: EffectContext) -> None:
    """Cynthia's Gible (sv10 102): "[F] 20 — This attack's damage isn't affected by
    Resistance." Owns its damage: the printed 20 is flat, but it must skip the Resistance
    half of the W/R chokepoint, which the engine's auto-applied base damage cannot do.
    Weakness still applies (only Resistance is named).

    Emits the damage it actually dealt: because this attack is in
    ATTACK_EFFECT_OWNS_DAMAGE, _resolve_attack applies 0 base and therefore never prints
    its own "used Rock Hurl for N" line — without this emit the whole Resistance-skipping
    clause is invisible in game logs, which is how effect liveness is verified here."""
    dealt = apply_attack_damage(ctx, ctx.opp.active, 20, owner=ctx.opp, source=ctx.source,
                                ignore_resistance=True)
    ctx.state.emit(f"Rock Hurl: {dealt} damage (ignores Resistance)")


def _champions_call(ctx: EffectContext) -> None:
    """Cynthia's Gabite (sv10 103) Ability: "Once during your turn, you may search your
    deck for a Cynthia's Pokémon, reveal it, and put it into your hand. Then, shuffle your
    deck." One card, any Cynthia's Pokémon (Gible/Gabite/Garchomp ex/Roselia/Roserade/
    Spiritomb) — this is the line's whole consistency engine."""
    n = search_deck(ctx, [p_cynthias_pokemon], dest="hand")
    if n:
        ctx.state.emit("Champion's Call: searched a Cynthia's Pokémon")


def _corkscrew_dive(ctx: EffectContext) -> None:
    """Cynthia's Garchomp ex (sv10 104): "[F] 100 — You may draw cards until you have 6
    cards in your hand." 100 is flat and engine-applied; this only adds the refill. v0
    takes the optional draw whenever it draws at least 1 (the optional-beneficial
    convention) — with a hand of 6+ it correctly draws nothing."""
    need = 6 - len(ctx.me.hand)
    if need > 0:
        drew = draw(ctx, need)
        ctx.state.emit(f"Corkscrew Dive: drew {drew} (up to a 6-card hand)")


def _draconic_buster(ctx: EffectContext) -> None:
    """Cynthia's Garchomp ex (sv10 104): "[F][F] 260 — Discard all Energy from this
    Pokémon." 260 is flat and engine-applied; this is the pure cost. ALL Energy, not just
    Basic and not just Fighting (a Rocky Fighting Energy attached here goes too)."""
    src = ctx.source
    if src is None or not src.energy:
        return
    n = len(src.energy)
    ctx.me.discard.extend(src.energy)
    src.energy = []
    ctx.state.emit(f"Draconic Buster: discarded all {n} Energy from {src.card.name}")


def _raging_curse(ctx: EffectContext) -> None:
    """Cynthia's Spiritomb (sv10 129): "[C] 10× — This attack does 10 damage for each
    damage counter on all of your Benched Cynthia's Pokémon. This attack's damage isn't
    affected by Weakness."

    Printed "10×", so the engine applies 0 base and this effect lands the whole hit
    (Giant Rock / Maximum Drilling precedent). BENCHED only — damage on the Active
    Spiritomb itself (or on an Active Cynthia's Pokémon) never counts — and only Cynthia's
    Pokémon. Resistance still applies; only Weakness is named. A board with no counters
    means the attack does 0 damage, in which case apply_attack_damage returns early and no
    pre-W/R damage boost (Cheer On to Glory / Premium Power Pro) is added either — an
    attack that does no damage can't have damage added to it."""
    counters = sum(m.damage // 10 for m in ctx.me.bench if p_cynthias_pokemon(m.card))
    dealt = apply_attack_damage(ctx, ctx.opp.active, counters * 10, owner=ctx.opp,
                                source=ctx.source, ignore_weakness=True)
    ctx.state.emit(f"Raging Curse: {counters} counter(s) on Benched Cynthia's Pokémon "
                   f"-> {counters * 10} base, {dealt} dealt")


# --------------------------------------------------------------------------- #
# Pitch Black "Hide 'n' Sneak" line (hide_n_sneak deck) — Shuppet (PBL) /
# Banette (PBL) / Dhelmise (PBL) / Poltchageist (PBL) / Sinistcha (PBL), plus the
# Dunsparce (JTG) print, Flutter Mane and the Gwynn Supporter.
#
# The archetype's engine is its own DISCARD PILE: two payoffs count how many
# Pokémon "that have the Hide 'n' Sneak Ability" are sitting in it (Vengeful
# Anchor at 4+, Matcha Spin at 6+), which is why the list wants Gwynn / Ultra
# Ball / Prism Tower throwing its own Pokémon away.
# --------------------------------------------------------------------------- #
def p_hide_n_sneak_pokemon(c) -> bool:
    """A "Pokémon that [has] the Hide 'n' Sneak Ability" — matched on the ABILITY, not
    on a name list, exactly as the two payoff attacks are worded. Any future print with
    the Ability therefore counts automatically."""
    return c.is_pokemon and any(ab.name == "Hide 'n' Sneak" for ab in c.abilities)


def count_hide_n_sneak_in_discard(player: PlayerState) -> int:
    """How many Pokémon with the Hide 'n' Sneak Ability are in `player`'s discard pile.
    Counts CARDS, so 3 discarded Shuppet count 3."""
    return sum(1 for c in player.discard if p_hide_n_sneak_pokemon(c))


def _vengeful_anchor(ctx: EffectContext) -> None:
    """Dhelmise (PBL 39): "[P] 30+ — If you have 4 or more Pokémon that have the
    Hide 'n' Sneak Ability in your discard pile, this attack does 140 more damage."

    Printed "30+", so per the engine's variable-damage rule the engine applies 0 base and
    this effect lands the WHOLE hit (30 or 170) in one call — that way Weakness multiplies
    the real total once, instead of doubling a 30 base and adding a flat 140.
    """
    n = count_hide_n_sneak_in_discard(ctx.me)
    base = 30 + (140 if n >= 4 else 0)
    dealt = apply_attack_damage(ctx, ctx.opp.active, base, owner=ctx.opp, source=ctx.source)
    ctx.state.emit(f"Vengeful Anchor: {n} Hide 'n' Sneak Pokémon in discard -> "
                   f"{base} base, {dealt} dealt")


def _puppet_pull(ctx: EffectContext) -> None:
    """Banette (PBL 34): "[P] 80 — You may search your deck for a card and put it into
    your hand. Then, shuffle your deck."

    80 is a FLAT printed number, so the engine already applied it; this effect is only
    the search. "A card" is unrestricted — any card at all, one of them."""
    found = search_deck(ctx, [p_any])
    ctx.state.emit(f"Puppet Pull: searched deck for {found} card(s)")


def _furtive_drop(ctx: EffectContext) -> None:
    """Poltchageist (PBL 5): "[C] — Place 1 damage counter on your opponent's Active
    Pokémon."

    No printed damage at all: this is a COUNTER-placing effect, not attack damage, so it
    goes through place_counters (no Weakness/Resistance, and an opposing Battle Cage /
    Hide 'n' Sneak / Sparkling Scales can prevent it)."""
    placed = place_counters(ctx, ctx.opp.active, 1, owner=ctx.opp)
    ctx.state.emit(f"Furtive Drop: placed {placed} damage counter(s)")


def _matcha_spin(ctx: EffectContext) -> None:
    """Sinistcha (PBL 6): "[C] — If you have 6 or more Pokémon that have the Hide 'n'
    Sneak Ability in your discard pile, place 4 damage counters on each of your
    opponent's Pokémon."

    All-or-nothing: below 6 the attack does literally nothing. At 6+, 4 counters on EACH
    of the opponent's Pokémon — Active AND Bench — placed as counters (no W/R), so a
    Battle Cage protects their Bench but not their Active."""
    n = count_hide_n_sneak_in_discard(ctx.me)
    if n < 6:
        ctx.state.emit(f"Matcha Spin: only {n} Hide 'n' Sneak Pokémon in discard "
                       f"(needs 6) — no effect")
        return
    placed = 0
    for mon in list(ctx.opp.all_in_play()):
        placed += place_counters(ctx, mon, 4, owner=ctx.opp)
    ctx.state.emit(f"Matcha Spin: {n} in discard -> placed {placed} damage counter(s) "
                   f"across the opponent's Pokémon")


def _trading_places(ctx: EffectContext) -> None:
    """Dunsparce (JTG 120): "[C] — Switch this Pokémon with 1 of your Benched Pokémon."

    No damage. The ATTACKER switches ITSELF out (this is the deck's free pivot off a
    used-up opener); attacking still ends the turn. v0 target policy: promote the
    healthiest bencher, the same policy _promote / Run Away Draw already use. Special
    Conditions clear off the Active Spot, as with retreat / Switch."""
    me = ctx.me
    if ctx.source is not me.active or not me.bench:
        ctx.state.emit("Trading Places: no Benched Pokémon to switch with")
        return
    idx = max(range(len(me.bench)), key=lambda i: me.bench[i].remaining_hp)
    newcomer = me.bench.pop(idx)
    outgoing = me.active
    outgoing.confused = False
    me.bench.append(outgoing)
    me.active = newcomer
    ctx.state.emit(f"Trading Places: switched {outgoing.card.name} out for "
                   f"{newcomer.card.name}")


def _hex_hurl(ctx: EffectContext) -> None:
    """Flutter Mane (PRE 43 / svp-97): "[C][C][C] 90 — Put 2 damage counters on your
    opponent's Benched Pokémon in any way you like."

    90 is flat and already applied by the engine; the effect is the 2-counter Bench
    spread, distributed by the shared place_counters_on_bench policy (finish the
    closest-to-KO bencher first)."""
    place_counters_on_bench(ctx, counters=2, policy="maximize_ko")


def _gwynn(ctx: EffectContext) -> bool:
    """Gwynn (PBL 78, Supporter): "Discard up to 2 Pokémon that don't have a Rule Box
    from your hand, and draw 3 cards for each card you discarded in this way."

    "Up to 2", and 3 cards PER discard — so 1 Pokémon draws 3, 2 Pokémon draw 6. Only
    Pokémon WITHOUT a Rule Box are legal fuel (this list's Lillie's Clefairy ex and
    Bloodmoon Ursaluna ex can never be discarded to it). v0 policy discards the least
    valuable eligible Pokémon first, by the engine's existing `_search_value`."""
    discarded = 0
    for _ in range(2):
        idxs = [i for i, c in enumerate(ctx.me.hand)
                if c.is_pokemon and not _has_rule_box(c)]
        if not idxs:
            break
        i = min(idxs, key=lambda j: _search_value(ctx.me.hand[j]))
        ctx.me.discard.append(ctx.me.hand.pop(i))
        discarded += 1
    if discarded == 0:
        return False
    drew = draw(ctx, 3 * discarded)
    ctx.state.emit(f"Gwynn: discarded {discarded} non-Rule-Box Pokémon, drew {drew}")
    return True


def can_play_gwynn(state, me) -> bool:
    """Playable only if there is at least 1 non-Rule-Box Pokémon in hand to discard —
    discarding 0 would draw 0, and the engine never offers a Trainer that does nothing."""
    return any(c.is_pokemon and not _has_rule_box(c) for c in me.hand)


# --------------------------------------------------------------------------- #
# Pitch Black Toucannon line + its Stellar Crown / Temporal Forces support
# (the `toucannon` deck) — Pikipek / Trumbeak / Toucannon (me5 66/67/68),
# Hoothoot (SCR) / Noctowl (SCR 114/115), Iron Leaves ex (TEF 25).
#
# PRINT COLLISION: the pool's bare "Hoothoot" is sv5-126 (Temporal Forces,
# "Silent Wing"), a DIFFERENT card that raging_bolt / water already play. The
# Stellar Crown print this deck needs is pooled as "Hoothoot (SCR)" and keyed here
# under that exact name, per the Metagross (CRI) / Dunsparce (JTG) precedent.
# Pikipek / Trumbeak / Toucannon are brand new — no same-named pool entry, so they
# keep their bare names. Noctowl and Iron Leaves ex are NOT collisions: the pool's
# svp-141 / svp-128 Promo prints carry text identical to SCR 115 / TEF 25.
# --------------------------------------------------------------------------- #
def _coin_flip_damage(ctx: EffectContext, coins: int, per_heads: int) -> int:
    """Shared "flip N coins, this attack does X damage for each heads" body. Printed as
    "X×", i.e. variable damage, so the engine applies 0 base and this lands the whole
    hit through the Weakness/Resistance chokepoint exactly once. All-tails really is 0
    damage (apply_attack_damage returns early), which is the point of owning it."""
    heads = sum(1 for _ in range(coins) if flip(ctx))
    damage_active_with_weakness(ctx, per_heads * heads)
    return heads


def _double_stab(ctx: EffectContext) -> None:
    """Pikipek (me5 66): "[C] 10× — Flip 2 coins. This attack does 10 damage for each
    heads." 0-20 damage."""
    heads = _coin_flip_damage(ctx, 2, 10)
    ctx.state.emit(f"Double Stab: {heads}/2 heads -> {heads * 10} base")


def _triple_stab(ctx: EffectContext) -> None:
    """Hoothoot (SCR) (sv7-114): "[C] 10× — Flip 3 coins. This attack does 10 damage for
    each heads." 0-30 damage. NOT the pool's bare "Hoothoot" (sv5-126), whose attack is
    Silent Wing — see the section header."""
    heads = _coin_flip_damage(ctx, 3, 10)
    ctx.state.emit(f"Triple Stab: {heads}/3 heads -> {heads * 10} base")


def _silent_wing(ctx: EffectContext) -> None:
    """Hoothoot (sv5-126, Temporal Forces — the pool's BARE "Hoothoot", played by
    raging_bolt / water; NOT the Toucannon deck's "Hoothoot (SCR)"): "[C][C] 20 — Your
    opponent reveals their hand."

    20 is flat and already applied by the engine. The rider is a LOGGED NO-OP, and here
    is precisely what is and is not covered:
      - NOT COVERED: nothing changes. There is no per-player "what I have seen of my
        opponent's hand" memory in this engine — GameState carries both hands in the
        clear, and the only place hidden information exists at all is MCTS's
        determinize(), which reshuffles the opponent's hidden zones from the acting
        player's point of view. Making a reveal matter would mean adding a revealed-cards
        memory that determinize consults; that subsystem does not exist.
      - CONSEQUENCE: an opponent's information gain from this attack is worth 0 to the
        search, so Silent Wing is scored as a plain 20-damage attack.
    Registered anyway (rather than left to the vanilla fallback) so the coverage/gap
    check counts it as deliberately handled, per the _shocking_knuckle / _poison_chain
    precedent for the other faithfully-not-modeled riders."""
    ctx.state.emit("Silent Wing: opponent reveals their hand (no-op — hand information "
                   "is not modeled)")


def _fly(ctx: EffectContext) -> None:
    """Trumbeak (me5 67): "[C] 30 — Flip a coin. If tails, this attack does nothing. If
    heads, during your opponent's next turn, prevent all damage from and effects of
    attacks done to this Pokémon."

    OWNS its damage (ATTACK_EFFECT_OWNS_DAMAGE) because a tails must do literally
    nothing — if the engine pre-applied the flat 30, a tails would still hit. Same shape
    as Weedle's Surprise Attack. The heads rider is the engine's `shielded` flag, the
    exact same "prevent all damage from and effects of attacks done to this Pokémon
    during your opponent's next turn" wall that Dunsparce's Dig sets, cleared by
    game.start_turn after the opponent's one intervening turn."""
    if not flip(ctx):
        ctx.state.emit("Fly: tails — this attack does nothing")
        return
    dealt = apply_attack_damage(ctx, ctx.opp.active, 30, owner=ctx.opp, source=ctx.source)
    ctx.source.shielded = True
    ctx.state.emit(f"Fly: heads — {dealt} damage, and {ctx.source.card.name} is shielded "
                   f"during the opponent's next turn")


def _feather_rondo(ctx: EffectContext) -> None:
    """Toucannon (me5 68): "[C] 60+ — This attack does 20 more damage for each Benched
    Pokémon (both yours and your opponent's)."

    BOTH sides' Benches, combined — the deck's whole payoff, and why it wants a wide
    board and Area Zero Underdepths' 8-Bench. Printed "60+", so the engine applies 0
    base and this effect lands the whole hit once (Full Moon Rondo precedent, which is
    the same clause at 20+20). Benched only: neither Active counts."""
    benched = len(ctx.me.bench) + len(ctx.opp.bench)
    dmg = 60 + 20 * benched
    dealt = apply_attack_damage(ctx, ctx.opp.active, dmg, owner=ctx.opp, source=ctx.source)
    ctx.state.emit(f"Feather Rondo: {benched} Benched Pokémon (both sides) -> {dmg} base, "
                   f"{dealt} dealt")


def _aerial_draw(ctx: EffectContext) -> None:
    """Toucannon (me5 68) Ability: "Once during your turn, you may use this Ability.
    Draw a card." Once per turn PER TOUCANNON (the engine's per-Pokémon
    `ability_used_this_turn` budget), so a second Toucannon in play really does draw a
    second card — there is no "you can't use more than 1 Aerial Draw" clause."""
    n = draw(ctx, 1)
    ctx.state.emit(f"Aerial Draw: drew {n}")


def _jewel_seeker(ctx: EffectContext) -> None:
    """Noctowl (SCR 115 / svp-141) on-evolve trigger: "Once during your turn, when you
    play this Pokémon from your hand to evolve 1 of your Pokémon, if you have any Tera
    Pokémon in play, you may search your deck for up to 2 Trainer cards, reveal them, and
    put them into your hand. Then, shuffle your deck."

    TRIGGER PRECISION — all three gates are real:
      - "when you play this Pokémon from your hand to EVOLVE 1 of your Pokémon": an
        ON_EVOLVE_TRIGGERS entry, so it fires on the evolve action AND through Rare Candy
        (both are playing it from hand to evolve), and never on any other way a Noctowl
        reaches play.
      - "if you have any Tera Pokémon in play": checked against THIS player's board
        (Active + Bench) at trigger time. No Tera -> nothing happens at all.
      - "up to 2 Trainer cards": two p_trainer predicates through search_deck, so a deck
        holding only 1 Trainer finds 1, and an empty deck finds 0.
    "Once during your turn" scopes to this Noctowl's own trigger, which can only fire on
    the evolution that created it — evolving a SECOND Noctowl the same turn is a second
    Pokémon and legitimately triggers again. (v0: the "may" is always taken.)"""
    if not any(p_tera(m.card) for m in ctx.me.all_in_play()):
        ctx.state.emit("Jewel Seeker: no Tera Pokémon in play — no search")
        return
    found = search_deck(ctx, [p_trainer, p_trainer], dest="hand")
    ctx.state.emit(f"Jewel Seeker: searched {found} Trainer card(s) into hand")


# Energy whose provided type is a wildcard, so it can pay a typed symbol on some
# holders — consulted only by Rapid Vernier's donor PREFERENCE ordering. (Prism / Neo
# Upper Energy are conditional on the holder's stage; listing them here is a heuristic,
# never a correctness claim — `_pays` re-checks every candidate against the real
# provided_types() of the real holder.)
_WILDCARD_ENERGY = {"Legacy Energy", "Prism Energy", "Neo Upper Energy"}


def _rapid_vernier(ctx: EffectContext) -> None:
    """Iron Leaves ex (TEF 25 / svp-128) on-bench trigger: "When you play this Pokémon
    from your hand onto your Bench during your turn, you may switch it with your Active
    Pokémon. If you do, you may move any amount of Energy from your other Pokémon to this
    Pokémon."

    v0 POLICY for the two nested "may"s — stated precisely because this one is NOT the
    usual always-take-the-beneficial-option:
      - The switch is taken ONLY when the Energy move that follows it would let Iron
        Leaves ex pay Prism Edge ([G][G][C]) this turn. That is the entire reason the
        Ability exists (a surprise 180 out of nowhere), and taking the switch
        unconditionally would be a real MISPLAY — it would drag a healthy loaded
        attacker off the Active Spot and strip its Energy for nothing.
      - "Any amount of Energy from your OTHER Pokémon": exactly the units needed to pay
        Prism Edge are moved, no more, drawn from the other Pokémon in a deterministic
        order (Active first, then Bench order; within a Pokémon, attached order). Nothing
        already on Iron Leaves ex is touched, and its own attachments count toward the
        cost.
    If no such subset exists, the trigger declines the switch and nothing happens."""
    me = ctx.me
    src = ctx.source
    if src is None or me.active is None or src is me.active:
        return
    prism = next((a for a in src.card.attacks if a.name == "Prism Edge"), None)
    if prism is None:
        return
    cost = tuple(prism.cost)

    # Candidate Energy cards on the OTHER Pokémon, deterministic order.
    donors: list[tuple[InPlayPokemon, object]] = []
    for mon in [me.active] + list(me.bench):
        if mon is src:
            continue
        for e in mon.energy:
            donors.append((mon, e))

    # Greedily pick the smallest prefix (by usefulness order) that pays the cost.
    # Local import: game.py imports THIS module at load time, so a top-level import
    # here would be circular. By call time `game` is fully loaded.
    from .game import can_pay_cost

    def _pays(extra) -> bool:
        probe = InPlayPokemon(card=src.card, energy=list(src.energy) + [e for _, e in extra])
        return can_pay_cost(probe, cost)

    if _pays([]):
        chosen: list[tuple[InPlayPokemon, object]] = []
    else:
        # Prefer Energy that provides a symbol the cost actually needs (Grass here),
        # then anything else — a stable, deterministic sort.
        needed = {s for s in cost if s != "Colorless"}
        ordered = sorted(range(len(donors)),
                         key=lambda i: (0 if (set(donors[i][1].types or []) & needed
                                              or donors[i][1].name in _WILDCARD_ENERGY)
                                        else 1, i))
        chosen = []
        for i in ordered:
            chosen.append(donors[i])
            if _pays(chosen):
                break
        else:
            ctx.state.emit("Rapid Vernier: declined — not enough Energy on your other "
                           "Pokémon to pay Prism Edge")
            return

    # Take the switch: src is on the Bench, me.active goes to the Bench slot it vacates.
    idx = next((i for i, m in enumerate(me.bench) if m is src), None)
    if idx is None:
        return
    outgoing = me.active
    outgoing.confused = False          # leaving the Active Spot clears Special Conditions
    me.bench[idx] = outgoing
    me.active = src
    for mon, e in chosen:
        mon.energy.remove(e)
        src.energy.append(e)
    ctx.state.emit(f"Rapid Vernier: switched {outgoing.card.name} out for "
                   f"{src.card.name} and moved {len(chosen)} Energy to it")


def _prism_edge(ctx: EffectContext) -> None:
    """Iron Leaves ex (TEF 25 / svp-128): "[G][G][C] 180 — During your next turn, this
    Pokémon can't attack." 180 is flat and engine-applied; this is only the self-lock,
    the same `pending_cannot_attack` rider Latias ex's Eon Blade uses."""
    ctx.source.pending_cannot_attack = True
    ctx.state.emit("Prism Edge: this Pokémon can't attack next turn")


# --------------------------------------------------------------------------- #
# MEGA GARDEVOIR — Anar Guliyev's real Regional Utrecht list (gardevoir_real).
#
# The Ralts/Kirlia/Mega Gardevoir ex core and its Trainer suite were already
# implemented for the built `gardevoir` archetype; what this list adds is the
# Marill / Azumarill ex Energy-hoarding sub-engine, Zacian's prize-clock finisher,
# and Mega Diancie ex's Diamond Coat (a PASSIVE that the pool's me2-41 print has
# always had — Garland Ray was implemented, the Ability was not).
# --------------------------------------------------------------------------- #
def _ball_roll(ctx: EffectContext) -> None:
    """Marill (TEF 64 / sv5-64) "Ball Roll": [C] 10× — "Flip a coin until you get
    tails. This attack does 10 damage for each heads."

    Unbounded flip loop (geometric, so it terminates with probability 1) driven by
    ctx.rng, so it stays seed-deterministic. Printed damage carries the "×" suffix, so
    the engine applies 0 base and this effect lands the whole hit once — Weakness
    therefore multiplies the TOTAL, not each 10 (the _maximum_drilling precedent).
    """
    heads = 0
    while flip(ctx):
        heads += 1
    dealt = apply_attack_damage(ctx, ctx.opp.active, heads * 10, owner=ctx.opp)
    ctx.state.emit(f"Ball Roll: {heads} heads -> {dealt} damage")


def _bubble_gathering(ctx: EffectContext) -> None:
    """Azumarill ex (ASC 84) "Bubble Gathering": "As often as you like during your turn,
    you may use this Ability. Move an Energy from 1 of your other Pokémon to this
    Pokémon."

    "As often as you like" -> REPEATABLE_ABILITIES. It always terminates: each use
    strictly reduces the number of Energy on your OTHER Pokémon, and the can-use guard
    goes false once there are none, so a repeat-happy agent can't loop forever.

    WHICH Energy moves is a policy hook (same shape as place_counters_on_bench's
    targeting). v0 prefers a Psychic-providing Energy — that is what Energized Balloon
    counts — and prefers taking it from a BENCHED Pokémon over the Active, so the
    Ability doesn't strip the attacker that is currently paying a cost.
    """
    me, dest = ctx.me, ctx.source
    if dest is None:
        return
    best = None            # (rank, mon, energy)
    for mon in me.all_in_play():
        if mon is dest:
            continue                       # "1 of your OTHER Pokémon"
        on_bench = _on_bench(me, mon)
        for e in mon.energy:
            psychic = "Psychic" in (e.types or ())
            rank = (1 if psychic else 0, 1 if on_bench else 0)
            if best is None or rank > best[0]:
                best = (rank, mon, e)
    if best is None:
        return
    _, src, energy = best
    src.energy.remove(energy)
    dest.energy.append(energy)
    ctx.state.emit(f"Bubble Gathering: moved {energy.name} from {src.card.name} "
                   f"to {dest.card.name}")


def _energized_balloon(ctx: EffectContext) -> None:
    """Azumarill ex (ASC 84) "Energized Balloon": [C][C][C] 60+ — "This attack does 40
    more damage for each Psychic Energy attached to this Pokémon."

    Counts Energy CARDS attached to the attacker that provide Psychic (Basic Psychic
    Energy and Telepathic Psychic Energy both carry types=["Psychic"]). Prism Energy is
    deliberately NOT counted: it provides "every type of Energy" only on a BASIC holder,
    and Azumarill ex is a Stage 1, so on this Pokémon it is a plain Colorless provider.
    Printed "+" damage, so the engine applies 0 base and this lands 60 + 40×N once.
    """
    n = sum(1 for e in ctx.source.energy if "Psychic" in (e.types or ()))
    dealt = apply_attack_damage(ctx, ctx.opp.active, 60 + 40 * n, owner=ctx.opp)
    ctx.state.emit(f"Energized Balloon: {n} Psychic Energy attached -> {dealt}")


def _limit_break(ctx: EffectContext) -> None:
    """Zacian (PFL 45 / me2-45) "Limit Break": [P][C] 50+ — "If your opponent has 3 or
    fewer Prize cards remaining, this attack does 90 more damage."

    Reads the OPPONENT's remaining prize count (len(opp.prizes)), i.e. how many they
    still have to take, not how many they've taken. Printed "+" damage -> 0 engine base,
    the whole 50/140 lands here so Weakness multiplies the total once.
    """
    bonus = 90 if len(ctx.opp.prizes) <= 3 else 0
    dealt = apply_attack_damage(ctx, ctx.opp.active, 50 + bonus, owner=ctx.opp)
    ctx.state.emit(f"Limit Break: opponent has {len(ctx.opp.prizes)} Prizes left "
                   f"-> {dealt}")


# --------------------------------------------------------------------------- #
# Perfect Order Aegislash line (Honedge -> Doublade -> Aegislash) + the Destined
# Rivals Steven's Metagross ex line that supports it (doublade deck).
#
# Honedge's "Cut" (10, no text) is vanilla and deliberately has NO registry entry.
# --------------------------------------------------------------------------- #
# The Aegislash line's own names, for Weaponized Swords' reveal clause. print_base_name
# so a future disambiguated print ("Honedge (ME03)") still counts — the card names the
# PRINTED card, exactly like an evolvesFrom does.
_AEGISLASH_LINE_NAMES = ("Honedge", "Doublade", "Aegislash")


def p_aegislash_line(c) -> bool:
    """A "Honedge, Doublade, [or] Aegislash" card, by printed name."""
    return c.is_pokemon and print_base_name(c.name) in _AEGISLASH_LINE_NAMES


def _weaponized_swords(ctx: EffectContext) -> None:
    """Doublade (ME03 57) "Weaponized Swords": [C][C] 60× — "Reveal any number of
    Honedge, Doublade, and Aegislash from your hand, and this attack does 60 damage for
    each card you revealed in this way."

    REVEAL, NOT DISCARD — the single most important property of this card. Revealing is
    an INFORMATION action: the cards are shown to the opponent and then stay exactly
    where they were. This effect therefore must NOT mutate ctx.me.hand in any way: no
    pop, no remove, no reordering. The same three Honedge in hand can power a 180-damage
    Weaponized Swords on this turn, next turn, and every turn after that. (Contrast with
    Inferno X / Metallic Hammer, which pay for their damage by discarding — those move
    cards, this one does not.)

    v0 policy for "any number" (a hook MCTS could later own): reveal ALL of them. The
    reveal has no cost and no downside beyond the information itself, and damage scales
    strictly upward with the count, so revealing everything is dominant.

    Printed "60×", i.e. variable damage, so _resolve_attack applies 0 base and this
    effect lands the whole hit through the W/R chokepoint once (the Maximum Drilling /
    Raging Curse precedent — such attacks are NOT listed in ATTACK_EFFECT_OWNS_DAMAGE,
    which exists only for FLAT-printed attacks that must nonetheless own their damage).
    A hand with none of the three does 0 damage, and apply_attack_damage returns early.
    """
    revealed = [c for c in ctx.me.hand if p_aegislash_line(c)]
    hand_before = len(ctx.me.hand)
    dealt = apply_attack_damage(ctx, ctx.opp.active, 60 * len(revealed), owner=ctx.opp,
                                source=ctx.source)
    # Loud, checkable invariant: this attack may never change the hand. It is cheap and
    # it guards the one thing about this card that is easy to break later.
    assert len(ctx.me.hand) == hand_before, \
        "Weaponized Swords REVEALS from hand — it must never remove a card from it"
    names = ", ".join(sorted(c.name for c in revealed)) or "nothing"
    ctx.state.emit(f"Weaponized Swords: revealed {len(revealed)} from hand ({names}) "
                   f"-> {60 * len(revealed)} base, {dealt} dealt; revealed cards STAY "
                   f"in hand ({len(ctx.me.hand)} cards)")


def _metal_slash_lock(ctx: EffectContext) -> None:
    """Shared effect for the two printed "Metal Slash" attacks in this archetype:

      Aegislash (ME03 58): [M][C][C][C] 230 — "During your next turn, this Pokémon
        can't use attacks."
      Steven's Metang (DRI 144): [M][C] 70 — "During your next turn, this Pokémon
        can't attack."

    Different wordings, identical rule: the attacker is locked out of attacking for its
    owner's next turn only. Both damages are FLAT and engine-applied, so this effect
    adds no damage — it only arms the lock. pending_cannot_attack is promoted to
    `cannot_attack` by start_turn on the owner's NEXT turn and cleared the turn after,
    so the opponent's intervening turn is untouched (the Eon Blade lifecycle).
    """
    ctx.source.pending_cannot_attack = True
    ctx.state.emit(f"Metal Slash: {ctx.source.card.name} can't attack during your "
                   f"next turn")


def _x_boot(ctx: EffectContext) -> None:
    """Steven's Metagross ex (DRI 145) Ability "X-Boot": "Once during your turn, you may
    search your deck for a Basic Psychic Energy card, a Basic Metal Energy card, or 1 of
    each and attach them to your Psychic Pokémon and Metal Pokémon in any way you like.
    Then, shuffle your deck."

    READING (stated precisely, because the alternative is tempting): the two named
    Energy types are matched to the two named Pokémon types — the Basic [P] Energy goes
    on one of your [P] Pokémon and the Basic [M] Energy on one of your [M] Pokémon.
    "In any way you like" is the choice of WHICH of your eligible Pokémon of that type
    receives it (and it is why the two attachments need not land on the same Pokémon).
    It does NOT mean the [P] Energy may be attached to a [M] Pokémon. CONSEQUENCE, stated
    honestly: in a list with no [P] Pokémon at all, the [P] half of this Ability is dead
    and only the [M] Energy is fetched.

    "or 1 of each" makes both halves optional and independent, so each type is taken only
    when there is both a card in the deck to find AND a legal holder in play — the engine
    never takes a search it cannot complete.

    v0 distribution policy (a hook MCTS can later own), copied from Metal Maker: load the
    Active when the Active is an eligible holder — that's the attacker being powered up —
    otherwise the least-loaded eligible Benched Pokémon.

    Does NOT consume the turn's manual Energy attachment (it is an Ability, not the
    once-per-turn attach), and it shuffles the deck afterwards.
    """
    me = ctx.me
    attached = []
    for etype in ("Psychic", "Metal"):
        holders = [m for m in me.all_in_play() if etype in m.card.types]
        if not holders:
            continue
        card = next((c for c in me.deck if c.is_basic_energy and etype in c.types), None)
        if card is None:
            continue
        if me.active is not None and etype in me.active.card.types:
            target = me.active
        else:
            target = min(holders, key=lambda m: m.energy_count())
        me.deck.remove(card)
        target.energy.append(card)
        attached.append(f"{card.name} -> {target.card.name}")
    if ctx.rng:
        ctx.rng.shuffle(me.deck)          # "Then, shuffle your deck."
    if attached:
        ctx.state.emit(f"X-Boot: attached {len(attached)} Basic Energy from deck "
                       f"({'; '.join(attached)})")


def can_use_x_boot(state, me, mon) -> bool:
    """X-Boot is only offered when at least one half can actually be completed: a Basic
    Energy of that type still in the deck AND one of your Pokémon of that type in play.
    (Reading the deck here follows the Metallic Signal / Champion's Call precedent — a
    deck SEARCH is information the acting player is entitled to; contrast Metal Maker,
    whose guard must not peek because its window is the hidden TOP of the deck.)"""
    for etype in ("Psychic", "Metal"):
        if (any(etype in m.card.types for m in me.all_in_play())
                and any(c.is_basic_energy and etype in c.types for c in me.deck)):
            return True
    return False


def team_rocket_factory_active(state: GameState) -> bool:
    """Is Team Rocket's Factory the Stadium currently in play?"""
    return current_stadium_name(state) == "Team Rocket's Factory"


# Attacks where the registered EFFECT computes/places ALL the damage, so the engine
# must apply 0 base (otherwise the printed number would hit the Active a SECOND time
# on top of the effect's chosen-target damage). Variable-damage ("+"/"×") attacks
# are already handled separately.
ATTACK_EFFECT_OWNS_DAMAGE: set[tuple[str, str]] = {
    ("Mega Charizard Y ex", "Explosion Y"),   # 280 to a CHOSEN Pokémon, not the Active
    ("Fan Rotom", "Assault Landing"),          # conditional (nothing without a Stadium)
    ("Iron Crown ex", "Twin Shotels"),         # 50 to 2 CHOSEN Pokémon, not the Active
    ("Mega Mawile ex", "Huge Bite"),           # conditional base (30 vs 260) — owns it
    ("Weedle", "Surprise Attack"),             # 30 on heads, 0 on tails — owns it
    ("Crustle", "Superb Scissors"),            # 120 with active-effect bypass — owns it
    ("Cornerstone Mask Ogerpon ex", "Demolish"),  # 140, ignores W/R + active effects
    ("Mega Starmie ex", "Nebula Beam"),        # 210, ignores W/R + active effects
    ("Slowking", "Seek Inspiration"),          # copies a discarded mon's base damage (0 if a miss)
    ("Kyurem", "Trifrost"),                    # 110 to 3 CHOSEN Pokémon, not the Active
    ("Metagross", "Meteor Mash"),              # conditional base (60 vs 120 when self-buffed)
    ("Cynthia's Gible", "Rock Hurl"),           # 20, must skip Resistance — owns it
    ("Trumbeak", "Fly"),                        # 30 on heads, NOTHING on tails — owns it
}


# (card_name, attack_name) -> effect
ATTACK_EFFECTS: dict[tuple[str, str], Callable[[EffectContext], None]] = {
    ("Dragapult ex", "Phantom Dive"): _phantom_dive,
    ("Raging Bolt ex", "Bellowing Thunder"): _bellowing_thunder,
    ("Raging Bolt ex", "Burst Roar"): _burst_roar,
    ("Teal Mask Ogerpon ex", "Myriad Leaf Shower"): _myriad_leaf_shower,
    ("Mega Charizard X ex", "Inferno X"): _inferno_x,
    ("Fezandipiti ex", "Cruel Arrow"): _cruel_arrow,
    ("Mega Charizard Y ex", "Explosion Y"): _explosion_y,
    ("Munkidori", "Mind Bend"): _mind_bend,
    ("Dusknoir", "Shadow Bind"): _shadow_bind,
    ("Budew", "Itchy Pollen"): _itchy_pollen,
    ("Mega Slowbro ex", "Shellnado Spin"): _shellnado_spin,
    ("Moltres", "Fighting Wings"): _fighting_wings,
    ("Duskull", "Come and Get You"): _come_and_get_you,
    ("Dunsparce", "Dig"): _dig,
    ("Fan Rotom", "Assault Landing"): _assault_landing,
    ("Meowth ex", "Tuck Tail"): _tuck_tail,
    ("Klefki", "Stick 'n' Draw"): _stick_n_draw,
    # --- feature/more-cards ---
    ("Ralts", "Collect"): _collect,
    ("Kirlia", "Call Sign"): _call_sign,
    ("Mega Gardevoir ex", "Overflowing Wishes"): _overflowing_wishes,
    ("Mega Gardevoir ex", "Mega Symphonia"): _mega_symphonia,
    ("Mega Diancie ex", "Garland Ray"): _garland_ray,
    ("Iron Crown ex", "Twin Shotels"): _twin_shotels,
    ("Latias ex", "Eon Blade"): _eon_blade,
    ("Koraidon ex (ASC)", "Orichalcum Fang"): _orichalcum_fang,
    ("Koraidon ex (ASC)", "Impact Blow"): _impact_blow,
    ("Lugia ex", "Hyper Whirlpool"): _hyper_whirlpool,
    ("Snorlax ex", "Toss-and-Turn Press"): _toss_and_turn,
    ("Cyclizar ex", "Break Through"): _break_through,
    ("Cyclizar ex", "Zircon Road"): _zircon_road,
    ("Mega Kangaskhan ex", "Rapid-Fire Combo"): _rapid_fire_combo,
    ("Terapagos ex", "Unified Beatdown"): _unified_beatdown,
    ("Reshiram ex", "Scorching Fire"): _scorching_fire,
    ("Volcanion ex", "Scorching Cyclone"): _scorching_cyclone,
    ("Ethan's Ho-Oh ex", "Shining Feathers"): _shining_feathers,
    ("Tapu Koko ex", "Linked Lightning"): _linked_lightning,
    # --- feature/more-decks (Fighting / Dark / Metal / Water) ---
    ("Mega Lucario ex", "Aura Jab"): _aura_jab,
    ("Regirock ex", "Regi Charge"): _regi_charge,
    ("Regirock ex", "Giant Rock"): _giant_rock,
    ("Iron Boulder ex", "Power Stomp"): _power_stomp,
    ("Iron Boulder ex", "Repulsor Axe"): _repulsor_axe,
    ("Koraidon ex", "Retribution Strike"): _retribution_strike,
    ("Koraidon ex", "Kaiser Tackle"): _kaiser_tackle,
    ("Mega Absol ex", "Terminal Period"): _terminal_period,
    ("Mega Absol ex", "Claw of Darkness"): _claw_of_darkness,
    ("Mega Mawile ex", "Gobble Down"): _gobble_down,
    ("Mega Mawile ex", "Huge Bite"): _huge_bite,
    ("Hop's Zacian ex", "Insta-Strike"): _insta_strike,
    ("Dondozo ex", "Avenging Billow"): _avenging_billow,
    ("Dondozo ex", "Dynamic Dive"): _dynamic_dive,
    ("Lapras ex", "Power Splash"): _power_splash,
    ("Mega Lucario ex", "Mega Brave"): _mega_brave,
    ("Hop's Zacian ex", "Brave Slash"): _brave_slash,
    ("Mega Greninja ex", "Ninja Spinner"): _ninja_spinner,
    ("Beedrill ex", "Rumbling Bees"): _rumbling_bees,
    ("Weedle", "Surprise Attack"): _surprise_attack,
    # --- Destined Rivals / Twilight Masquerade walls + bypass attackers ---
    ("Crustle", "Superb Scissors"): _superb_scissors,
    ("Cornerstone Mask Ogerpon ex", "Demolish"): _demolish,
    ("Bloodmoon Ursaluna ex", "Blood Moon"): _blood_moon,
    # --- Journey Together / Surging Sparks / Mega Evolution ---
    ("Lillie's Clefairy ex", "Full Moon Rondo"): _full_moon_rondo,
    ("Chien-Pao", "Icicle Loop"): _icicle_loop,
    ("Alakazam", "Powerful Hand"): _powerful_hand,
    # --- Perfect Order (Mega Starmie ex line) + Froakie/Frogadier ---
    ("Mega Starmie ex", "Jetting Blow"): _jetting_blow,
    ("Mega Starmie ex", "Nebula Beam"): _nebula_beam,
    ("Frogadier", "Numbing Water"): _numbing_water,
    ("Froakie", "Flock"): _flock,
    # --- Stellar Crown / Surging Sparks / Twilight Masquerade / Shrouded Fable ---
    ("Slowking", "Seek Inspiration"): _seek_inspiration,
    ("Annihilape", "Tantrum"): _tantrum,
    ("Annihilape", "Destined Fight"): _destined_fight,
    ("Smoochum", "Delightful Kiss"): _delightful_kiss,
    ("Slowpoke", "Dangle Tail"): _dangle_tail,
    ("Kyurem", "Trifrost"): _trifrost,
    ("Metagross", "Luster Blast"): _luster_blast,
    ("Zeraora", "Strong Volt"): _strong_volt,
    ("Zeraora", "Shocking Knuckle"): _shocking_knuckle,
    ("Wellspring Mask Ogerpon ex", "Sob"): _sob,
    ("Wellspring Mask Ogerpon ex", "Torrential Pump"): _torrential_pump,
    ("Pecharunt", "Poison Chain"): _poison_chain,
    ("Chi-Yu", "Allure"): _allure,
    ("Chi-Yu", "Ground Melter"): _ground_melter,
    # --- Pitch Black-era Metal (Mega Excadrill ex line) ---
    ("Beldum", "Iron Tackle"): _iron_tackle,
    ("Metagross", "Meteor Mash"): _meteor_mash,
    ("Genesect ex", "Protect Charge"): _protect_charge,
    ("Ethan's Pichu", "Zapping Draw"): _zapping_draw,
    ("Mega Excadrill ex", "Undermine"): _undermine,
    ("Mega Excadrill ex", "Maximum Drilling"): _maximum_drilling,
    ("Drilbur", "Call for Family"): _call_for_family,   # real tournament-list print (PBL 46)
    ("Metagross (CRI)", "M Bounce Back"): _bounce_back,
    ("Metagross (CRI)", "Metallic Hammer"): _metallic_hammer,
    # --- Mega Evolution-era Fighting (Cynthia's Garchomp ex line) ---
    ("Cynthia's Gible", "Rock Hurl"): _rock_hurl,
    ("Cynthia's Garchomp ex", "Corkscrew Dive"): _corkscrew_dive,
    ("Cynthia's Garchomp ex", "Draconic Buster"): _draconic_buster,
    ("Cynthia's Spiritomb", "Raging Curse"): _raging_curse,
    # --- Pitch Black "Hide 'n' Sneak" line (hide_n_sneak) ---
    # NOTE: keyed on the SUFFIXED print names. The bare "Shuppet"/"Banette"/"Dhelmise"/
    # "Poltchageist"/"Sinistcha"/"Patrat"/"Dunsparce" pool entries are OLDER, different
    # cards and must keep falling through to vanilla — see the deck comment in decks.py.
    ("Dhelmise (PBL)", "Vengeful Anchor"): _vengeful_anchor,
    ("Banette (PBL)", "Puppet Pull"): _puppet_pull,
    ("Poltchageist (PBL)", "Furtive Drop"): _furtive_drop,
    ("Sinistcha (PBL)", "Matcha Spin"): _matcha_spin,
    ("Dunsparce (JTG)", "Trading Places"): _trading_places,
    ("Flutter Mane", "Hex Hurl"): _hex_hurl,
    # --- Pitch Black Toucannon line + its SCR/TEF support (toucannon) ---
    # NOTE: "Hoothoot (SCR)" is the SUFFIXED print (sv7-114, Triple Stab). The bare
    # "Hoothoot" below is the pool's OLDER sv5-126 Temporal Forces print (Silent Wing),
    # played by raging_bolt / water — two prints, two entries, on purpose.
    ("Pikipek", "Double Stab"): _double_stab,
    ("Trumbeak", "Fly"): _fly,
    ("Toucannon", "Feather Rondo"): _feather_rondo,
    ("Hoothoot (SCR)", "Triple Stab"): _triple_stab,
    ("Hoothoot", "Silent Wing"): _silent_wing,
    ("Iron Leaves ex", "Prism Edge"): _prism_edge,
    # --- Mega Gardevoir, Anar Guliyev's real list (gardevoir_real) ---
    # NOT print collisions: the pool's Marill (sv5-64) IS the TEF 64 print that carries
    # Ball Roll, and Zacian (me2-45) IS the PFL 45 print that carries Limit Break.
    ("Marill", "Ball Roll"): _ball_roll,
    ("Azumarill ex", "Energized Balloon"): _energized_balloon,
    ("Zacian", "Limit Break"): _limit_break,
    # --- Perfect Order Aegislash line + Steven's Metagross ex support (doublade) ---
    # NOT a print collision: "Honedge"/"Doublade"/"Aegislash" are brand-new pool names
    # (ME03 56/57/58), so the bare names ARE these cards. Honedge's Cut (10, no text) is
    # vanilla and has no entry on purpose.
    ("Doublade", "Weaponized Swords"): _weaponized_swords,
    ("Aegislash", "Metal Slash"): _metal_slash_lock,      # 230, then no attacks next turn
    ("Steven's Metang", "Metal Slash"): _metal_slash_lock,  # 70, same lock, DRI print
    # Aegislash's "Slash" (80, no additional text) is vanilla — no entry, on purpose.
}

# (card_name, ability_name) -> effect
ABILITY_EFFECTS: dict[tuple[str, str], Callable[[EffectContext], None]] = {
    ("Drakloak", "Recon Directive"): _recon_directive,
    ("Teal Mask Ogerpon ex", "Teal Dance"): _teal_dance,
    ("Dudunsparce", "Run Away Draw"): _run_away_draw,
    ("Dusclops", "Cursed Blast"): _cursed_blast_5,
    ("Dusknoir", "Cursed Blast"): _cursed_blast_13,
    ("Munkidori", "Adrena-Brain"): _adrena_brain,
    ("Fezandipiti ex", "Flip the Script"): _flip_the_script,
    ("Oricorio ex", "Excited Turbo"): _excited_turbo,
    ("Fan Rotom", "Fan Call"): _fan_call,
    ("Mega Kangaskhan ex", "Run Errand"): _run_errand,
    ("Mega Greninja ex", "Mortal Shuriken"): _mortal_shuriken,
    # --- Pitch Black-era Metal (Mega Excadrill ex line) ---
    ("Metang", "Metal Maker"): _metal_maker,
    ("Genesect ex", "Metallic Signal"): _metallic_signal,
    # --- Mega Evolution-era Fighting (Cynthia's Garchomp ex line) ---
    ("Cynthia's Gabite", "Champion's Call"): _champions_call,
    # --- Pitch Black Toucannon line (toucannon) ---
    ("Toucannon", "Aerial Draw"): _aerial_draw,
    # --- Mega Gardevoir, Anar Guliyev's real list (gardevoir_real) ---
    ("Azumarill ex", "Bubble Gathering"): _bubble_gathering,
    # --- Steven's Metagross ex support for the Aegislash line (doublade) ---
    ("Steven's Metagross ex", "X-Boot"): _x_boot,
}

# Abilities usable any number of times per turn (not gated by ability_used_this_turn).
REPEATABLE_ABILITIES: set[tuple[str, str]] = {
    ("Oricorio ex", "Excited Turbo"),
    # "As often as you like during your turn, you may use this Ability." Terminates
    # because each use moves one Energy OFF your other Pokémon and the guard below
    # requires at least one to still be there.
    ("Azumarill ex", "Bubble Gathering"),
}

# Abilities that fire when the Pokémon is played from hand onto the Bench.
# card_name -> effect(ctx with source = the new Pokémon).
ON_BENCH_TRIGGERS: dict[str, Callable[[EffectContext], None]] = {
    "Meowth ex": _last_ditch_catch,
    "Chien-Pao": _snow_sink,
    "Drilbur (TEF)": _dig_dig_dig,    # Dig Dig Dig (TEF 85) — NOT the bare "Drilbur"
                                      # used by mega_excadrill, which is the real
                                      # tournament-list print (PBL 46, no ability).
    "Iron Leaves ex": _rapid_vernier,  # Rapid Vernier (TEF 25 / svp-128)
}

# Abilities that fire when this Pokémon is played from hand to EVOLVE one of yours
# (both the normal evolve action and Rare Candy count as "playing from hand to
# evolve"). card_name -> effect(ctx with source = the just-evolved Pokémon).
ON_EVOLVE_TRIGGERS: dict[str, Callable[[EffectContext], None]] = {
    "Alakazam": _psychic_draw,
    "Noctowl": _jewel_seeker,     # Jewel Seeker (SCR 115 / svp-141)
}


def is_repeatable_ability(card_name: str, ability_name: str) -> bool:
    return (card_name, ability_name) in REPEATABLE_ABILITIES


def get_on_bench_trigger(card_name: str):
    return ON_BENCH_TRIGGERS.get(card_name)


def get_on_evolve_trigger(card_name: str):
    return ON_EVOLVE_TRIGGERS.get(card_name)


def _watchtower_suppressed(state: GameState, mon: InPlayPokemon) -> bool:
    """Team Rocket's Watchtower: Colorless Pokémon (both players) have no Abilities."""
    return ("Colorless" in mon.card.types
            and current_stadium_name(state) == "Team Rocket's Watchtower")


def _midnight_fluttering_suppressed(state: GameState, mon: InPlayPokemon) -> bool:
    """Flutter Mane's "Midnight Fluttering": "As long as this Pokémon is in the Active
    Spot, your opponent's Active Pokémon has no Abilities, except for Midnight
    Fluttering."

    Both halves are ACTIVE-only: the Flutter Mane must be in the Active Spot, and only
    the opposing ACTIVE loses its Abilities — a Benched Pokémon's Ability is untouched
    (which is why this can't switch off a Benched Hide 'n' Sneak).

    The "except for Midnight Fluttering" clause is why a mirror Flutter Mane keeps its
    own Ability, and it is also what stops this from recursing: a Pokémon that itself has
    Midnight Fluttering is never suppressed by another one, so the opposing holder's
    status is decided by the Stadium rule alone.
    """
    if any(ab.name == "Midnight Fluttering" for ab in mon.card.abilities):
        return False
    owner = owner_of(state, mon)
    if owner is None or mon is not owner.active:
        return False
    foe = next((p for p in state.players if p is not owner), None)
    if foe is None or foe.active is None:
        return False
    holder = foe.active
    return (any(ab.name == "Midnight Fluttering" for ab in holder.card.abilities)
            and not _watchtower_suppressed(state, holder))


def ability_suppressed(state: GameState, mon: InPlayPokemon) -> bool:
    """Is this Pokémon's Ability switched off right now? Two live sources:
    Team Rocket's Watchtower (Stadium, Colorless Pokémon) and an opposing Active
    Flutter Mane's Midnight Fluttering."""
    return (_watchtower_suppressed(state, mon)
            or _midnight_fluttering_suppressed(state, mon))


def _opp_of(state) -> PlayerState:
    return state.players[1 - state.active_index]


# Optional usability guards so the engine never offers an ability that would do
# nothing (and let greedy waste it). (card_name, ability_name) -> pred(state, me, mon).
ABILITY_CAN_USE: dict[tuple[str, str], Callable] = {
    # Teal Dance needs a Basic Grass Energy in hand to attach.
    ("Teal Mask Ogerpon ex", "Teal Dance"):
        lambda state, me, mon: any(c.is_basic_energy and "Grass" in c.types for c in me.hand),
    # Run Away Draw needs cards to draw, and must not remove your only Pokémon.
    ("Dudunsparce", "Run Away Draw"):
        lambda state, me, mon: len(me.deck) > 0 and (mon is not me.active or len(me.bench) > 0),
    # Cursed Blast is a self-KO: only offer it when it actually secures a KO, so
    # greedy doesn't throw the Pokémon away for nothing. (v0 policy — chip-damage
    # Cursed Blast not offered; logged in §5. MCTS could value chip later.)
    ("Dusclops", "Cursed Blast"):
        lambda state, me, mon: _pick_ko_target(_opp_of(state), 50) is not None,
    ("Dusknoir", "Cursed Blast"):
        lambda state, me, mon: _pick_ko_target(_opp_of(state), 130) is not None,
    # Adrena-Brain needs Darkness attached and a damaged Pokémon of yours to move from —
    # and no Watchful Eye in play, which would make the move do nothing.
    ("Munkidori", "Adrena-Brain"):
        lambda state, me, mon: any("Darkness" in e.types for e in mon.energy)
            and any(m.damage >= 10 for m in me.all_in_play())
            and not damage_counter_move_blocked(state),
    # Flip the Script: only if a Pokémon of yours was KO'd last turn, and you can draw.
    ("Fezandipiti ex", "Flip the Script"):
        lambda state, me, mon: me.koed_last_turn and len(me.deck) > 0,
    # Excited Turbo: a Fire MEGA ex in play, a Basic Fire Energy in hand, a Benched Fire mon.
    ("Oricorio ex", "Excited Turbo"):
        lambda state, me, mon: any("MEGA" in m.card.subtypes and "Fire" in m.card.types
                                   for m in me.all_in_play())
            and any(c.is_basic_energy and "Fire" in c.types for c in me.hand)
            and any("Fire" in m.card.types for m in me.bench),
    # Fan Call: only on your first turn, and only if there's a target to find.
    ("Fan Rotom", "Fan Call"):
        lambda state, me, mon: me.turns_taken == 1 and any(p_colorless_le100(c) for c in me.deck),
    # Run Errand: only when this Pokémon is the Active and there are cards to draw.
    ("Mega Kangaskhan ex", "Run Errand"):
        lambda state, me, mon: mon is me.active and len(me.deck) > 0,
    # Mortal Shuriken: only when Active, with a Basic Water Energy in hand to discard,
    # and the opponent has a Pokémon to snipe.
    ("Mega Greninja ex", "Mortal Shuriken"):
        lambda state, me, mon: (mon is me.active
            and any(c.is_basic_energy and "Water" in c.types for c in me.hand)
            and _opp_of(state).has_pokemon_in_play()),
    # Metal Maker: only that there ARE cards to look at, and somewhere to attach. It
    # deliberately does NOT peek at the top 4 for Metal Energy — the window is hidden
    # information, and a guard that read it would leak the deck order to the agent.
    ("Metang", "Metal Maker"):
        lambda state, me, mon: len(me.deck) > 0 and me.has_pokemon_in_play(),
    # Metallic Signal: only when there's an Evolution Metal Pokémon left to find.
    ("Genesect ex", "Metallic Signal"):
        lambda state, me, mon: any(p_evolution_metal_pokemon(c) for c in me.deck),
    # Champion's Call: only when there's a Cynthia's Pokémon left in the deck to find.
    ("Cynthia's Gabite", "Champion's Call"):
        lambda state, me, mon: any(p_cynthias_pokemon(c) for c in me.deck),
    # Bubble Gathering: only while one of your OTHER Pokémon still has an Energy to
    # move. This is also what makes the repeatable Ability terminate — every use
    # removes one Energy from that pool.
    ("Azumarill ex", "Bubble Gathering"):
        lambda state, me, mon: any(m is not mon and m.energy for m in me.all_in_play()),
    # X-Boot: only when at least one of its two halves can actually be completed
    # (a Basic [P]/[M] Energy left in the deck AND one of your Pokémon of that type).
    ("Steven's Metagross ex", "X-Boot"):
        lambda state, me, mon: can_use_x_boot(state, me, mon),
}


def get_ability_can_use(card_name: str, ability_name: str):
    return ABILITY_CAN_USE.get((card_name, ability_name))


# --------------------------------------------------------------------------- #
# TRAINER cards. Items: any number per turn. Supporters: one per turn (enforced
# by the engine). Each effect mutates state; a `can_play` predicate gates
# legality so the engine never offers a Trainer that would do nothing.
# --------------------------------------------------------------------------- #
def _evolution_chain_basic(db, stage2_card) -> Optional[str]:
    """For a Stage 2 card, return the Basic at the bottom of its line (or None).
    e.g. Dragapult ex -> Drakloak -> Dreepy ==> 'Dreepy'."""
    stage1_name = stage2_card.evolves_from
    if not stage1_name or stage1_name not in db:
        return None
    stage1 = db.get(stage1_name)
    return stage1.evolves_from


def _rare_candy(ctx: EffectContext) -> bool:
    """Skip Stage 1: evolve an in-play Basic straight to a Stage 2 in hand.
    Follows evolution timing (not first turn, not a Basic played this turn)."""
    db = ctx.state.db
    if ctx.me.turns_taken < 2:
        return False
    for hi, card in enumerate(ctx.me.hand):
        if not (card.is_pokemon and "Stage 2" in card.subtypes):
            continue
        basic_name = _evolution_chain_basic(db, card)
        if not basic_name:
            continue
        for mon in ctx.me.all_in_play():
            # print_base_name so a suffixed print of the Basic ("Dunsparce (JTG)") is
            # still a legal Rare Candy target, matching game.evolves_onto.
            if (print_base_name(mon.card.name) == basic_name
                    and not mon.played_this_turn
                    and not mon.evolved_this_turn):
                mon.evolved_from.append(mon.card)
                mon.card = ctx.me.hand.pop(hi)
                mon.evolved_this_turn = True
                mon.ability_used_this_turn = False
                ctx.state.emit(f"Rare Candy: {basic_name} -> {mon.card.name}")
                # on-evolve-from-hand trigger (Alakazam: Psychic Draw). Rare Candy still
                # "plays the Pokémon from hand to evolve," so it fires here too. Give the
                # trigger a context whose source is the just-evolved Pokémon.
                trigger = get_on_evolve_trigger(mon.card.name)
                if trigger and not ability_suppressed(ctx.state, mon):
                    evo_ctx = EffectContext(state=ctx.state, me=ctx.me, opp=ctx.opp,
                                            source=mon, db=ctx.state.db, rng=ctx.rng)
                    trigger(evo_ctx)
                # (No MEGA turn-end: current Mega Evolution Pokémon ex have no special
                # play rules — see game.py evolve branch / official rulebook p23.)
                return True
    return False


def can_play_rare_candy(state, me) -> bool:
    if me.turns_taken < 2:
        return False
    db = state.db
    for card in me.hand:
        if card.is_pokemon and "Stage 2" in card.subtypes:
            basic_name = _evolution_chain_basic(db, card)
            if basic_name and any(
                    print_base_name(m.card.name) == basic_name and not m.played_this_turn
                    and not m.evolved_this_turn for m in me.all_in_play()):
                return True
    return False


def _buddy_buddy_poffin(ctx: EffectContext) -> bool:
    """Search deck for up to 2 Basic Pokemon with <=70 HP, put on bench."""
    space = bench_limit(ctx.state, ctx.me) - len(ctx.me.bench)
    if space <= 0:
        return False
    found = 0
    # prefer Basics that are evolution fodder (have something to evolve into)
    candidates = [c for c in ctx.me.deck
                  if c.is_pokemon and c.is_basic and (c.hp or 999) <= 70]
    candidates.sort(key=lambda c: (len(c.evolves_to) == 0, c.name))  # fodder first
    for c in candidates:
        if found >= 2 or len(ctx.me.bench) >= bench_limit(ctx.state, ctx.me):
            break
        ctx.me.deck.remove(c)
        ctx.me.bench.append(InPlayPokemon(card=c, played_this_turn=True))
        found += 1
    ctx.rng.shuffle(ctx.me.deck) if ctx.rng else None
    if found:
        ctx.state.emit(f"Buddy-Buddy Poffin: benched {found} Basic(s)")
    return found > 0


def can_play_poffin(state, me) -> bool:
    if len(me.bench) >= bench_limit(state, me):
        return False
    return any(c.is_pokemon and c.is_basic and (c.hp or 999) <= 70 for c in me.deck)


def _cheren(ctx: EffectContext) -> bool:
    return draw(ctx, 3) > 0


def can_play_cheren(state, me) -> bool:
    return len(me.deck) > 0


def _boss_orders(ctx: EffectContext) -> bool:
    """Gust: switch one of the opponent's Benched Pokemon into the Active Spot.
    Target choice (v0): the benched Pokemon with the lowest remaining HP (easiest
    to KO) — a hook MCTS will later own."""
    if not ctx.opp.bench:
        return False
    victim = min(ctx.opp.bench, key=lambda m: m.remaining_hp)
    ctx.opp.bench.remove(victim)
    if ctx.opp.active:
        ctx.opp.bench.append(ctx.opp.active)
    ctx.opp.active = victim
    ctx.state.emit(f"Boss's Orders: dragged up {victim.card.name}")
    return True


def can_play_boss(state, opp_has_bench, me=None) -> bool:
    return opp_has_bench


def _prime_catcher(ctx: EffectContext) -> bool:
    """ACE SPEC Item: "Switch in 1 of your opponent's Benched Pokémon to the Active
    Spot. If you do, switch your Active Pokémon with 1 of your Benched Pokémon."
    First half is a Boss's-Orders-style gust (same lowest-HP v0 target heuristic);
    the second half only fires if you actually have a Bench to switch into (the card
    text conditions it on "if you do" the first switch, not on you having a Bench,
    but with no Bench there's nothing to switch into — silent no-op for that half,
    same as Switch with an empty Bench)."""
    if not ctx.opp.bench:
        return False
    victim = min(ctx.opp.bench, key=lambda m: m.remaining_hp)
    ctx.opp.bench.remove(victim)
    if ctx.opp.active:
        ctx.opp.bench.append(ctx.opp.active)
    ctx.opp.active = victim
    ctx.state.emit(f"Prime Catcher: dragged up {victim.card.name}")
    me = ctx.me
    if me.bench and me.active is not None:
        newcomer = max(me.bench, key=lambda m: m.remaining_hp)
        me.bench.remove(newcomer)
        me.active.confused = False
        me.bench.append(me.active)
        me.active = newcomer
        ctx.state.emit(f"Prime Catcher: switched in {newcomer.card.name}")
    return True


def can_play_prime_catcher(state, me) -> bool:
    return len(state.players[1 - state.active_index].bench) > 0


# --- §2.1 search/recovery Trainers (compose the search_deck / recover primitives) ---
def _poke_pad(ctx: EffectContext) -> bool:
    """Search deck for a Pokémon that doesn't have a Rule Box, put it into hand."""
    n = search_deck(ctx, [p_non_rule_box_pokemon], dest="hand")
    if n:
        ctx.state.emit("Poké Pad: searched a non-Rule-Box Pokémon")
    return n > 0


def _ultra_ball(ctx: EffectContext) -> bool:
    """Discard 2 other cards from hand, then search deck for any Pokémon to hand."""
    if len(ctx.me.hand) < 2 or not any(p_pokemon(c) for c in ctx.me.deck):
        return False
    # v0 discard policy: pitch the 2 lowest-value cards (energy/items before
    # Pokémon/Supporters); a hook MCTS will later own.
    order = sorted(range(len(ctx.me.hand)), key=lambda i: _search_value(ctx.me.hand[i]))
    for i in sorted(order[:2], reverse=True):
        ctx.me.discard.append(ctx.me.hand.pop(i))
    search_deck(ctx, [p_pokemon], dest="hand")
    ctx.state.emit("Ultra Ball: discarded 2, searched a Pokémon")
    return True


def _hilda(ctx: EffectContext) -> bool:
    """Search deck for an Evolution Pokémon AND an Energy, put both into hand."""
    n = search_deck(ctx, [p_evolution_pokemon, p_energy], dest="hand")
    if n:
        ctx.state.emit(f"Hilda: searched {n} card(s)")
    return n > 0


def _dawn(ctx: EffectContext) -> bool:
    """Search deck for a Basic, a Stage 1, and a Stage 2 Pokémon, put all into hand."""
    n = search_deck(ctx, [p_basic_pokemon, p_stage1, p_stage2], dest="hand")
    if n:
        ctx.state.emit(f"Dawn: searched {n} Pokémon")
    return n > 0


def _night_stretcher(ctx: EffectContext) -> bool:
    """Put a Pokémon OR a Basic Energy from the discard pile into hand."""
    n = recover_from_discard(ctx, [p_pokemon_or_basic_energy])
    if n:
        ctx.state.emit("Night Stretcher: recovered from discard")
    return n > 0


def _energy_retrieval(ctx: EffectContext) -> bool:
    """Put up to 2 Basic Energy from the discard pile into hand."""
    n = recover_from_discard(ctx, [p_basic_energy, p_basic_energy])
    if n:
        ctx.state.emit(f"Energy Retrieval: recovered {n} Basic Energy")
    return n > 0


def _switch(ctx: EffectContext) -> bool:
    """Switch your Active with a Benched Pokémon (v0: bring up the healthiest)."""
    me = ctx.me
    if not me.bench or me.active is None:
        return False
    newcomer = max(me.bench, key=lambda m: m.remaining_hp)
    me.bench.remove(newcomer)
    me.active.confused = False             # Special Conditions clear off the Active Spot
    me.bench.append(me.active)
    me.active = newcomer
    ctx.state.emit(f"Switch: brought up {newcomer.card.name}")
    return True


def _lillies_determination(ctx: EffectContext) -> bool:
    """Shuffle your hand into your deck, then draw 6 (8 if you have exactly 6 Prizes)."""
    shuffle_hand_into_deck(ctx, ctx.me)
    n = 8 if len(ctx.me.prizes) == 6 else 6
    drew = ctx.me.draw(n)
    ctx.state.emit(f"Lillie's Determination: drew {drew}")
    return True


def _judge(ctx: EffectContext) -> bool:
    """Each player shuffles their hand into their deck and draws 4 cards."""
    for pl in (ctx.me, ctx.opp):
        shuffle_hand_into_deck(ctx, pl)
        pl.draw(4)
    ctx.state.emit("Judge: both players shuffled hand and drew 4")
    return True


def _crispin(ctx: EffectContext) -> bool:
    """Search deck for up to 2 Basic Energy of DIFFERENT types; attach 1 to one of
    your Pokémon (v0: the Active), put the other into your hand."""
    me = ctx.me
    basics = [c for c in me.deck if c.is_basic_energy]
    if not basics:
        return False
    picked, seen = [], set()
    for c in sorted(basics, key=lambda c: c.name):
        t = c.types[0] if c.types else "Colorless"
        if t not in seen:
            picked.append(c)
            seen.add(t)
        if len(picked) == 2:
            break
    for c in picked:
        me.deck.remove(c)
    if ctx.rng:
        ctx.rng.shuffle(me.deck)
    target = me.active or (me.bench[0] if me.bench else None)
    if target is not None:
        target.energy.append(picked[0])          # attach 1
        for extra in picked[1:]:
            me.hand.append(extra)                 # the other -> hand
    else:                                         # no Pokémon to attach to
        me.hand.extend(picked)
    ctx.state.emit(f"Crispin: attached 1 + drew {len(picked) - 1} Basic Energy")
    return True


def _ciphermaniacs_codebreaking(ctx: EffectContext) -> bool:
    """Supporter: search your deck for 2 cards, shuffle your deck, then put those
    cards on TOP of it in any order (they become your next draws — NOT into hand)."""
    n = search_deck_to_top(ctx, 2)
    if n:
        ctx.state.emit(f"Ciphermaniac's Codebreaking: put {n} card(s) on top of deck")
    return n > 0


# --- NEW core-stabilization staples (meta-relevant search/draw/recovery/gust) ---
def _carmine(ctx: EffectContext) -> bool:
    """Discard your hand and draw 5 cards."""
    discard_hand_and_draw(ctx, 5)
    ctx.state.emit("Carmine: discarded hand, drew 5")
    return True


def _lacey(ctx: EffectContext) -> bool:
    """Shuffle your hand into your deck; draw 4 (8 if the opponent has <=3 Prizes left)."""
    shuffle_hand_into_deck(ctx, ctx.me)
    n = 8 if len(ctx.opp.prizes) <= 3 else 4
    drew = ctx.me.draw(n)
    ctx.state.emit(f"Lacey: drew {drew}")
    return True


def _kofu(ctx: EffectContext) -> bool:
    """Put 2 cards from your hand on the bottom of your deck, then draw 4."""
    me = ctx.me
    if len(me.hand) < 2:
        return False
    order = sorted(range(len(me.hand)), key=lambda i: _search_value(me.hand[i]))
    for i in sorted(order[:2], reverse=True):       # bottom the 2 lowest-value cards
        me.deck.append(me.hand.pop(i))
    me.draw(4)
    ctx.state.emit("Kofu: bottomed 2, drew 4")
    return True


def _cyrano(ctx: EffectContext) -> bool:
    """Search your deck for up to 3 Pokémon ex, put them into your hand."""
    n = search_deck(ctx, [p_pokemon_ex] * 3, dest="hand")
    if n:
        ctx.state.emit(f"Cyrano: searched {n} Pokémon ex")
    return n > 0


def _colress_tenacity(ctx: EffectContext) -> bool:
    """Search your deck for a Stadium and an Energy, put them into your hand."""
    n = search_deck(ctx, [p_stadium, p_energy], dest="hand")
    if n:
        ctx.state.emit(f"Colress's Tenacity: searched {n} card(s)")
    return n > 0


def _lanas_aid(ctx: EffectContext) -> bool:
    """Put up to 3 (non-Rule-Box Pokémon / Basic Energy) from discard into hand."""
    n = recover_from_discard(ctx, [p_non_rule_box_pkmn_or_basic_energy] * 3)
    if n:
        ctx.state.emit(f"Lana's Aid: recovered {n} from discard")
    return n > 0


def _drayton(ctx: EffectContext) -> bool:
    """Look at the top 7; take a Pokémon and a Trainer; shuffle the rest back."""
    n = look_and_take(ctx, 7, [p_pokemon, p_trainer])
    if n:
        ctx.state.emit(f"Drayton: took {n} card(s) from the top 7")
    return n > 0


def _hassel(ctx: EffectContext) -> bool:
    """If one of your Pokémon was KO'd last turn: look at top 8, take up to 3."""
    n = look_and_take(ctx, 8, [p_any] * 3)
    if n:
        ctx.state.emit(f"Hassel: took {n} card(s) from the top 8")
    return n > 0


def _poke_ball(ctx: EffectContext) -> bool:
    """Flip a coin. If heads, search your deck for a Pokémon, put it into your hand."""
    if flip(ctx):
        if search_deck(ctx, [p_pokemon], dest="hand"):
            ctx.state.emit("Poké Ball: heads — searched a Pokémon")
        else:
            ctx.state.emit("Poké Ball: heads — no Pokémon found")
    else:
        ctx.state.emit("Poké Ball: tails")
    return True            # the flip IS the effect; the card is used either way


def _master_ball(ctx: EffectContext) -> bool:
    """ACE SPEC: search your deck for a Pokémon, put it into your hand."""
    n = search_deck(ctx, [p_pokemon], dest="hand")
    if n:
        ctx.state.emit("Master Ball: searched a Pokémon")
    return n > 0


def _dusk_ball(ctx: EffectContext) -> bool:
    """Look at the bottom 7 of your deck; take a Pokémon; shuffle the rest back."""
    n = look_and_take(ctx, 7, [p_pokemon], from_bottom=True)
    if n:
        ctx.state.emit("Dusk Ball: took a Pokémon from the bottom 7")
    return n > 0


def _pokegear(ctx: EffectContext) -> bool:
    """Look at the top 7 of your deck; take a Supporter; shuffle the rest back."""
    n = look_and_take(ctx, 7, [p_supporter])
    if n:
        ctx.state.emit("Pokégear 3.0: found a Supporter")
    return n > 0


def _energy_switch(ctx: EffectContext) -> bool:
    """Move a Basic Energy from 1 of your Pokémon to another. v0: feed the Active
    from a benched Pokémon (accelerate the attacker); fall back to Active->Bench."""
    me = ctx.me
    bench_donors = [m for m in me.bench if any(e.is_basic_energy for e in m.energy)]
    if me.active is not None and bench_donors:
        donor, recip = max(bench_donors, key=lambda m: m.energy_count()), me.active
    elif me.active is not None and me.bench and any(e.is_basic_energy for e in me.active.energy):
        donor, recip = me.active, max(me.bench, key=lambda m: m.energy_count())
    else:
        return False
    for i, e in enumerate(donor.energy):
        if e.is_basic_energy:
            recip.energy.append(donor.energy.pop(i))
            ctx.state.emit(f"Energy Switch: moved {e.name} to {recip.card.name}")
            return True
    return False


def _energy_recycler(ctx: EffectContext) -> bool:
    """Shuffle up to 5 Basic Energy cards from your discard pile into your deck."""
    moved = 0
    for c in list(ctx.me.discard):
        if moved >= 5:
            break
        if c.is_basic_energy:
            ctx.me.discard.remove(c)
            ctx.me.deck.append(c)
            moved += 1
    if moved:
        if ctx.rng:
            ctx.rng.shuffle(ctx.me.deck)
        ctx.state.emit(f"Energy Recycler: shuffled {moved} Basic Energy into deck")
    return moved > 0


def _sacred_ash(ctx: EffectContext) -> bool:
    """Shuffle up to 5 Pokémon from your discard pile into your deck."""
    moved = 0
    for c in list(ctx.me.discard):
        if moved >= 5:
            break
        if c.is_pokemon:
            ctx.me.discard.remove(c)
            ctx.me.deck.append(c)
            moved += 1
    if moved:
        if ctx.rng:
            ctx.rng.shuffle(ctx.me.deck)
        ctx.state.emit(f"Sacred Ash: shuffled {moved} Pokémon into deck")
    return moved > 0


def _pokemon_catcher(ctx: EffectContext) -> bool:
    """Flip a coin. If heads, switch in 1 of the opponent's Benched Pokémon (gust)."""
    if flip(ctx):
        if ctx.opp.bench:
            victim = min(ctx.opp.bench, key=lambda m: m.remaining_hp)
            ctx.opp.bench.remove(victim)
            if ctx.opp.active:
                ctx.opp.bench.append(ctx.opp.active)
            ctx.opp.active = victim
            ctx.state.emit(f"Pokémon Catcher: heads — dragged up {victim.card.name}")
    else:
        ctx.state.emit("Pokémon Catcher: tails")
    return True            # the flip IS the effect; the card is used either way


def _p_special_energy(c) -> bool:
    """A Special Energy = an Energy card that is not a Basic Energy."""
    return c.is_energy and not c.is_basic_energy


def _enhanced_hammer(ctx: EffectContext) -> bool:
    """Item: discard a Special Energy from 1 of the opponent's Pokémon (v0: strip
    the Pokémon carrying the most Special Energy)."""
    targets = [m for m in ctx.opp.all_in_play()
               if any(_p_special_energy(e) for e in m.energy)]
    if not targets:
        return False
    victim = max(targets, key=lambda m: sum(1 for e in m.energy if _p_special_energy(e)))
    for i, e in enumerate(victim.energy):
        if _p_special_energy(e):
            ctx.opp.discard.append(victim.energy.pop(i))
            ctx.state.emit(f"Enhanced Hammer: discarded {e.name} from {victim.card.name}")
            return True
    return False


def _biancas_devotion(ctx: EffectContext) -> bool:
    """Supporter: "Heal all damage from 1 of your Pokémon that has 30 HP or less
    remaining." v0: pick the qualifying Pokémon with the LOWEST remaining HP
    (most in need of the heal) — deterministic, matches the codebase's
    lowest/highest-remaining_hp tie-breaking convention used elsewhere."""
    candidates = [m for m in ctx.me.all_in_play() if m.damage > 0 and 0 < m.remaining_hp <= 30]
    if not candidates:
        return False
    target = min(candidates, key=lambda m: m.remaining_hp)
    healed = target.damage
    heal(ctx, target, healed)
    ctx.state.emit(f"Bianca's Devotion: healed {healed} from {target.card.name}")
    return True


def _eri(ctx: EffectContext) -> bool:
    """Supporter: opponent reveals their hand; discard up to 2 Item cards from it
    (v0: the 2 highest-value Items — deterministic disruption)."""
    idxs = sorted((i for i, c in enumerate(ctx.opp.hand) if c.is_item),
                  key=lambda i: _search_value(ctx.opp.hand[i]), reverse=True)[:2]
    if not idxs:
        return False
    for i in sorted(idxs, reverse=True):
        ctx.opp.discard.append(ctx.opp.hand.pop(i))
    ctx.state.emit(f"Eri: discarded {len(idxs)} Item(s) from opponent's hand")
    return True


def _special_red_card(ctx: EffectContext) -> bool:
    """Item (only if opponent has ≤3 Prizes left): opponent shuffles their hand and
    puts it on the bottom of their deck; if they did, they draw 3."""
    opp = ctx.opp
    if not opp.hand:
        return False
    hand = opp.hand
    if ctx.rng:
        ctx.rng.shuffle(hand)
    opp.deck.extend(hand)        # bottom of the deck (draw pops from the top)
    opp.hand = []
    drew = opp.draw(3)
    ctx.state.emit(f"Special Red Card: opponent bottomed hand, drew {drew}")
    return True


def _scoop_up_cyclone(ctx: EffectContext) -> bool:
    """ACE SPEC Item: put 1 of your Pokémon and all attached cards into your hand.
    v0: pick up your most-damaged Pokémon (reset it); never leave yourself with no
    Active (only pick up the Active if there's a Bench to promote)."""
    me = ctx.me
    cands = list(me.bench)
    if me.active is not None and me.bench:
        cands.append(me.active)
    damaged = [m for m in cands if m.damage > 0]
    if not damaged:
        return False
    target = max(damaged, key=lambda m: m.damage)
    me.hand.append(target.card)
    me.hand.extend(target.energy)
    me.hand.extend(target.evolved_from)
    if target.tool is not None:
        me.hand.append(target.tool)
    if me.active is target:
        me.active = None
        me.bench.sort(key=lambda m: m.remaining_hp, reverse=True)
        me.active = me.bench.pop(0)
    else:
        me.bench = [m for m in me.bench if m is not target]
    ctx.state.emit(f"Scoop Up Cyclone: returned {target.card.name} (and attached) to hand")
    return True


def _wondrous_patch(ctx: EffectContext) -> bool:
    """Item: attach a Basic Psychic Energy from your discard pile to 1 of your Benched
    Psychic Pokémon (v0: the least-loaded bencher)."""
    benched_psychic = [m for m in ctx.me.bench if "Psychic" in m.card.types]
    if not benched_psychic:
        return False
    target = min(benched_psychic, key=lambda m: m.energy_count())
    if _attach_basic_from_discard(ctx, "Psychic", target, 1):
        ctx.state.emit(f"Wondrous Patch: attached Psychic Energy to {target.card.name}")
        return True
    return False


def _secret_box(ctx: EffectContext) -> bool:
    """ACE SPEC Item: discard 3 OTHER cards from your hand (Secret Box is already
    popped), then search your deck for an Item, a Pokémon Tool, a Supporter, and a
    Stadium; reveal them and put them into your hand."""
    me = ctx.me
    if len(me.hand) < 3:                      # need 3 OTHER cards to discard
        return False
    order = sorted(range(len(me.hand)), key=lambda i: _search_value(me.hand[i]))
    for i in sorted(order[:3], reverse=True):  # pitch the 3 lowest-value cards
        me.discard.append(me.hand.pop(i))
    n = search_deck(ctx, [p_item, p_tool, p_supporter, p_stadium], dest="hand")
    ctx.state.emit(f"Secret Box: discarded 3, searched {n} card(s)")
    return True


def _ns_plan(ctx: EffectContext) -> bool:
    """Supporter: move up to 2 Energy from your Benched Pokémon to your Active."""
    me = ctx.me
    if me.active is None:
        return False
    moved = 0
    for mon in me.bench:
        while mon.energy and moved < 2:
            me.active.energy.append(mon.energy.pop())
            moved += 1
        if moved >= 2:
            break
    if moved:
        ctx.state.emit(f"N's Plan: moved {moved} Energy to {me.active.card.name}")
    return moved > 0


def _bug_catching_set(ctx: EffectContext) -> bool:
    """Item: look at the top 7 cards; take up to 2 Grass Pokémon / Basic Grass Energy
    into your hand; shuffle the rest back into your deck."""
    n = look_and_take(ctx, 7, [p_grass_pkmn_or_basic_grass_energy] * 2)
    if n:
        ctx.state.emit(f"Bug Catching Set: took {n} card(s) from the top 7")
    return n > 0


def p_team_rocket_supporter(c) -> bool:
    """A Supporter "that has 'Team Rocket' in its name" (Team Rocket's Transceiver).
    Matched on the printed English name, which is how the card is worded."""
    return c.is_supporter and "Team Rocket" in c.name


def _team_rockets_petrel(ctx: EffectContext) -> bool:
    """Supporter: "Search your deck for a Trainer card, reveal it, and put it into your
    hand. Then, shuffle your deck." (Any Trainer — Item, Supporter, Tool or Stadium.)"""
    n = search_deck(ctx, [p_trainer], dest="hand")
    if n:
        ctx.state.emit("Team Rocket's Petrel: searched a Trainer card")
    return n > 0


def _kieran(ctx: EffectContext) -> bool:
    """Supporter, "Choose 1:
      • Switch your Active Pokémon with 1 of your Benched Pokémon.
      • During this turn, attacks used by your Pokémon do 30 more damage to your
        opponent's Active Pokémon ex and Active Pokémon V (before applying Weakness
        and Resistance)."

    v0 mode policy (a hook MCTS can later own): take the damage mode whenever the
    opponent's Active actually IS a Pokémon ex / Pokémon V — that's the only time the
    second bullet does anything at all, and +30 into a Rule-Box Active is what this deck
    plays Kieran for. Otherwise fall back to the switch."""
    if ctx.opp.active is not None and _is_ex_or_v(ctx.opp.active.card):
        ctx.me.bonus_damage_vs_ex_v = 30
        ctx.state.emit("Kieran: +30 damage to the opponent's Active ex/V this turn")
        return True
    return _switch(ctx)          # the switch mode (same v0 "bring up the healthiest")


def _team_rockets_transceiver(ctx: EffectContext) -> bool:
    """Item: "Search your deck for a Supporter card that has 'Team Rocket' in its name,
    reveal it, and put it into your hand. Then, shuffle your deck." """
    n = search_deck(ctx, [p_team_rocket_supporter], dest="hand")
    if n:
        ctx.state.emit("Team Rocket's Transceiver: searched a Team Rocket Supporter")
    return n > 0


def _jumbo_ice_cream(ctx: EffectContext) -> bool:
    """Item: "Heal 80 damage from your Active Pokémon that has 3 or more Energy
    attached." (A plain Item — NOT an ACE SPEC; verified on Bulbapedia. Requires the
    Active to have 3+ Energy AND real damage to remove, else the card would do nothing.)"""
    act = ctx.me.active
    if act is None or act.energy_count() < 3 or act.damage <= 0:
        return False
    healed = min(80, act.damage)
    heal(ctx, act, 80)
    ctx.state.emit(f"Jumbo Ice Cream: healed {healed} from {act.card.name}")
    return True


def _precious_trolley(ctx: EffectContext) -> bool:
    """ACE SPEC Item: "Search your deck for any number of Basic Pokémon and put them onto
    your Bench. Then, shuffle your deck." v0 policy for "any number": fill the Bench (a
    one-card explosion of board development is the whole reason to run it), preferring
    Basics that are evolution fodder via search_deck's value policy."""
    space = bench_limit(ctx.state, ctx.me) - len(ctx.me.bench)
    if space <= 0:
        return False
    n = search_deck(ctx, [p_basic_pokemon] * space, dest="bench")
    if n:
        ctx.state.emit(f"Precious Trolley: benched {n} Basic Pokémon")
    return n > 0


def _tera_orb(ctx: EffectContext) -> bool:
    """Item: search your deck for a Tera Pokémon, put it into your hand."""
    n = search_deck(ctx, [p_tera], dest="hand")
    if n:
        ctx.state.emit("Tera Orb: searched a Tera Pokémon")
    return n > 0


def _surfer(ctx: EffectContext) -> bool:
    """Supporter: "Switch your Active Pokémon with 1 of your Benched Pokémon. If you do,
    draw cards until you have 5 cards in your hand." The draw is CONDITIONAL on the switch
    ("if you do"), so a failed switch draws nothing and the card isn't spent. Reuses
    _switch's v0 "bring up the healthiest bencher" policy. The card itself is already out
    of hand when this runs (play_trainer pops first), so the count to 5 is correct."""
    if not _switch(ctx):
        return False
    need = 5 - len(ctx.me.hand)
    drew = draw(ctx, need) if need > 0 else 0
    ctx.state.emit(f"Surfer: switched, then drew {drew} (up to a 5-card hand)")
    return True


def _fighting_gong(ctx: EffectContext) -> bool:
    """Item: "Search your deck for a Basic [F] Energy card or a Basic [F] Pokémon, reveal
    it, and put it into your hand. Then, shuffle your deck." ONE card, either kind —
    search_deck's value policy picks (it ranks Pokémon above Energy, which is the right
    default for a deck that needs to assemble its line)."""
    n = search_deck(ctx, [p_basic_fighting_energy_or_basic_fighting_pokemon], dest="hand")
    if n:
        ctx.state.emit("Fighting Gong: searched a Basic Fighting Energy or Pokémon")
    return n > 0


def _premium_power_pro(ctx: EffectContext) -> bool:
    """Item: "During this turn, attacks used by your [F] Pokémon do 30 more damage to your
    opponent's Active Pokémon (before applying Weakness and Resistance)." Sets the
    turn-scoped player flag read in apply_attack_damage; start_turn clears it. ACCUMULATES
    so two copies in one turn really are +60 (two separate effects)."""
    ctx.me.bonus_damage_fighting_vs_active += 30
    ctx.state.emit(f"Premium Power Pro: your Fighting Pokémon do "
                   f"+{ctx.me.bonus_damage_fighting_vs_active} damage to the opponent's "
                   f"Active this turn")
    return True


def p_mega_evolution_ex(card) -> bool:
    """A "Mega Evolution Pokémon ex" — the current mark-I/J MEGA ex (Mega Gardevoir ex,
    Mega Diancie ex, ...). Both subtypes are required, matching the printed rule box that
    Wally's Compassion names."""
    subs = [s.lower() for s in card.subtypes]
    return card.is_pokemon and "mega" in subs and "ex" in subs


def _wallys_compassion(ctx: EffectContext) -> bool:
    """Wally's Compassion (MEG 132, Supporter): "Heal all damage from 1 of your Mega
    Evolution Pokémon ex. If you healed any damage in this way, put all Energy attached
    to that Pokémon into your hand."

    Both clauses, exactly as printed:
      - The heal is ALL damage, and only from a MEGA ex of YOURS.
      - The Energy bounce is CONDITIONAL on having healed something ("if you healed any
        damage in this way"), so an undamaged Mega ex is never stripped — which is also
        why can_play requires a damaged one, so greedy can't burn its Supporter for
        nothing.
      - "Put all Energy... into your HAND" — not the discard. Special Energy comes back
        too; the text says all Energy attached.
    TARGET POLICY: the most-damaged Mega ex (the one the heal is worth most on).
    """
    cands = [m for m in ctx.me.all_in_play()
             if p_mega_evolution_ex(m.card) and m.damage > 0]
    if not cands:
        return False
    mon = max(cands, key=lambda m: m.damage)
    healed = mon.damage
    heal(ctx, mon, healed)
    returned = len(mon.energy)
    ctx.me.hand.extend(mon.energy)
    mon.energy = []
    ctx.state.emit(f"Wally's Compassion: healed {healed} from {mon.card.name} and "
                   f"returned {returned} Energy to hand")
    return True


# card_name -> (effect, can_play_predicate)
# can_play takes (state, me) and returns bool.
TRAINER_EFFECTS: dict[str, Callable[[EffectContext], bool]] = {
    "Rare Candy": _rare_candy,
    "Buddy-Buddy Poffin": _buddy_buddy_poffin,
    "Cheren": _cheren,
    "Boss's Orders": _boss_orders,
    "Bianca's Devotion": _biancas_devotion,
    # §2.1 search/recovery engine
    "Poké Pad": _poke_pad,
    "Ultra Ball": _ultra_ball,
    "Hilda": _hilda,
    "Dawn": _dawn,
    "Night Stretcher": _night_stretcher,
    "Energy Retrieval": _energy_retrieval,
    "Switch": _switch,
    # §2.1/§2.3 shuffle-draw + energy search
    "Lillie's Determination": _lillies_determination,
    "Judge": _judge,
    "Crispin": _crispin,
    "Crushing Hammer": _crushing_hammer,
    "Unfair Stamp": _unfair_stamp,
    # --- core-stabilization staples ---
    "Carmine": _carmine,
    "Lacey": _lacey,
    "Kofu": _kofu,
    "Cyrano": _cyrano,
    "Colress's Tenacity": _colress_tenacity,
    "Lana's Aid": _lanas_aid,
    "Drayton": _drayton,
    "Hassel": _hassel,
    "Poké Ball": _poke_ball,
    "Master Ball": _master_ball,
    "Dusk Ball": _dusk_ball,
    "Pokégear 3.0": _pokegear,
    "Energy Switch": _energy_switch,
    "Energy Recycler": _energy_recycler,
    "Sacred Ash": _sacred_ash,
    "Pokémon Catcher": _pokemon_catcher,
    # --- Destined Rivals / Twilight Masquerade / Mega Evolution Trainers ---
    "Enhanced Hammer": _enhanced_hammer,
    "Eri": _eri,
    "Special Red Card": _special_red_card,
    "Scoop Up Cyclone": _scoop_up_cyclone,
    "Ciphermaniac's Codebreaking": _ciphermaniacs_codebreaking,
    # --- Stellar Crown / Twilight Masquerade / Black Bolt (Slowking + Ogerpon Box) ---
    "Wondrous Patch": _wondrous_patch,
    "Secret Box": _secret_box,
    "N's Plan": _ns_plan,
    "Bug Catching Set": _bug_catching_set,
    "Tera Orb": _tera_orb,
    # --- Pitch Black-era Metal (Mega Excadrill ex) Trainers ---
    "Team Rocket's Petrel": _team_rockets_petrel,
    "Kieran": _kieran,
    "Team Rocket's Transceiver": _team_rockets_transceiver,
    "Jumbo Ice Cream": _jumbo_ice_cream,
    "Precious Trolley": _precious_trolley,
    # --- Mega Evolution-era Fighting (Cynthia's Garchomp ex) Trainers ---
    "Surfer": _surfer,
    "Fighting Gong": _fighting_gong,
    "Premium Power Pro": _premium_power_pro,
    # --- Pitch Black "Hide 'n' Sneak" line ---
    "Gwynn": _gwynn,
    # --- Mega Gardevoir, Anar Guliyev's real list (gardevoir_real) ---
    "Wally's Compassion": _wallys_compassion,
    # --- Clefairy / Mega Kangaskhan ex (clefairy_stock, NAIC 2026) ---
    "Prime Catcher": _prime_catcher,
}

_TRAINER_CAN_PLAY: dict[str, Callable] = {
    "Rare Candy": can_play_rare_candy,
    "Buddy-Buddy Poffin": can_play_poffin,
    "Cheren": can_play_cheren,
    "Boss's Orders": lambda state, me: len(state.players[1 - state.active_index].bench) > 0,
    # §2.1: only offer a search/recovery card when it can actually find something.
    "Poké Pad": lambda state, me: any(p_non_rule_box_pokemon(c) for c in me.deck),
    "Ultra Ball": lambda state, me: len(me.hand) >= 3 and any(p_pokemon(c) for c in me.deck),
    "Hilda": lambda state, me: any(p_evolution_pokemon(c) or p_energy(c) for c in me.deck),
    "Dawn": lambda state, me: any(p_basic_pokemon(c) or p_stage1(c) or p_stage2(c) for c in me.deck),
    "Night Stretcher": lambda state, me: any(p_pokemon_or_basic_energy(c) for c in me.discard),
    "Energy Retrieval": lambda state, me: any(p_basic_energy(c) for c in me.discard),
    "Switch": lambda state, me: me.active is not None and len(me.bench) > 0,
    "Lillie's Determination": lambda state, me: len(me.deck) + len(me.hand) > 0,
    "Judge": lambda state, me: len(me.deck) + len(me.hand) > 0,
    "Crispin": lambda state, me: any(c.is_basic_energy for c in me.deck),
    # Crushing Hammer: only when the opponent has Energy to discard.
    "Crushing Hammer": lambda state, me: any(
        m.energy for m in state.players[1 - state.active_index].all_in_play()),
    # Unfair Stamp (ACE SPEC): only if a Pokémon of yours was KO'd last turn.
    "Unfair Stamp": lambda state, me: me.koed_last_turn,
    # --- core-stabilization staples (only offer when the card can do something) ---
    "Carmine": lambda state, me: len(me.deck) > 0,
    "Lacey": lambda state, me: len(me.deck) + len(me.hand) > 0,
    "Kofu": lambda state, me: len(me.hand) >= 2 and len(me.deck) > 0,
    "Cyrano": lambda state, me: any(p_pokemon_ex(c) for c in me.deck),
    "Colress's Tenacity": lambda state, me: any(p_stadium(c) or p_energy(c) for c in me.deck),
    "Lana's Aid": lambda state, me: any(p_non_rule_box_pkmn_or_basic_energy(c) for c in me.discard),
    "Drayton": lambda state, me: any(p_pokemon(c) or p_trainer(c) for c in me.deck),
    "Hassel": lambda state, me: me.koed_last_turn and len(me.deck) > 0,
    "Poké Ball": lambda state, me: any(p_pokemon(c) for c in me.deck),
    "Master Ball": lambda state, me: any(p_pokemon(c) for c in me.deck),
    "Dusk Ball": lambda state, me: any(p_pokemon(c) for c in me.deck),
    "Pokégear 3.0": lambda state, me: any(p_supporter(c) for c in me.deck),
    "Energy Switch": lambda state, me: (me.active is not None and len(me.bench) > 0
        and any(e.is_basic_energy for m in me.all_in_play() for e in m.energy)),
    "Energy Recycler": lambda state, me: any(p_basic_energy(c) for c in me.discard),
    "Sacred Ash": lambda state, me: any(p_pokemon(c) for c in me.discard),
    "Pokémon Catcher": lambda state, me: len(state.players[1 - state.active_index].bench) > 0,
    # --- Destined Rivals / Twilight Masquerade / Mega Evolution Trainers ---
    # Enhanced Hammer: only when the opponent has a Special Energy attached somewhere.
    "Enhanced Hammer": lambda state, me: any(
        _p_special_energy(e)
        for m in state.players[1 - state.active_index].all_in_play() for e in m.energy),
    # Eri: only when the opponent is holding at least 1 Item to discard.
    "Eri": lambda state, me: any(c.is_item for c in state.players[1 - state.active_index].hand),
    # Bianca's Devotion: only when a Pokémon of ours is at <=30 remaining HP (and alive).
    "Bianca's Devotion": lambda state, me: any(
        m.damage > 0 and 0 < m.remaining_hp <= 30 for m in me.all_in_play()),
    # Special Red Card: opponent has ≤3 Prizes left AND a hand to bottom.
    "Special Red Card": lambda state, me: (
        len(state.players[1 - state.active_index].prizes) <= 3
        and len(state.players[1 - state.active_index].hand) > 0),
    # Scoop Up Cyclone: a damaged Pokémon we can legally pick up (never orphan the Active).
    "Scoop Up Cyclone": lambda state, me: (
        any(m.damage > 0 for m in me.bench)
        or (me.active is not None and me.active.damage > 0 and len(me.bench) > 0)),
    # Ciphermaniac's Codebreaking: only when there are cards in the deck to search.
    "Ciphermaniac's Codebreaking": lambda state, me: len(me.deck) > 0,
    # --- Stellar Crown / Twilight Masquerade / Black Bolt (Slowking + Ogerpon Box) ---
    # Wondrous Patch: a Basic Psychic Energy in discard AND a Benched Psychic Pokémon.
    "Wondrous Patch": lambda state, me: (
        any(c.is_basic_energy and "Psychic" in c.types for c in me.discard)
        and any("Psychic" in m.card.types for m in me.bench)),
    # Secret Box (ACE SPEC): 3 OTHER cards in hand to discard (4 total incl. Secret Box).
    "Secret Box": lambda state, me: len(me.hand) >= 4,
    # N's Plan: an Active to move onto, and some Energy on the Bench to move.
    "N's Plan": lambda state, me: (me.active is not None
        and any(m.energy for m in me.bench)),
    # Bug Catching Set: a Grass Pokémon / Basic Grass Energy somewhere in the deck.
    "Bug Catching Set": lambda state, me: any(
        p_grass_pkmn_or_basic_grass_energy(c) for c in me.deck),
    # Tera Orb: a Tera Pokémon in the deck to fetch.
    "Tera Orb": lambda state, me: any(p_tera(c) for c in me.deck),
    # --- Pitch Black-era Metal (Mega Excadrill ex) Trainers ---
    # Team Rocket's Petrel: a Trainer left in the deck to find.
    "Team Rocket's Petrel": lambda state, me: any(p_trainer(c) for c in me.deck),
    # Kieran: either mode must be able to do something — an Active ex/V to hit for +30,
    # or an Active plus a Bench to switch with.
    "Kieran": lambda state, me: (
        (state.players[1 - state.active_index].active is not None
         and _is_ex_or_v(state.players[1 - state.active_index].active.card))
        or (me.active is not None and len(me.bench) > 0)),
    # Team Rocket's Transceiver: a "Team Rocket" Supporter left in the deck.
    "Team Rocket's Transceiver": lambda state, me: any(
        p_team_rocket_supporter(c) for c in me.deck),
    # Jumbo Ice Cream: the Active has 3+ Energy attached and damage to heal.
    "Jumbo Ice Cream": lambda state, me: (
        me.active is not None and me.active.energy_count() >= 3 and me.active.damage > 0),
    # Precious Trolley (ACE SPEC): Bench space AND a Basic Pokémon in the deck.
    "Precious Trolley": lambda state, me: (
        len(me.bench) < bench_limit(state, me) and any(p_basic_pokemon(c) for c in me.deck)),
    # --- Mega Evolution-era Fighting (Cynthia's Garchomp ex) Trainers ---
    # Surfer: the switch must be possible, else the "if you do" draw never happens.
    "Surfer": lambda state, me: me.active is not None and len(me.bench) > 0,
    # Fighting Gong: a Basic Fighting Energy or Basic Fighting Pokémon left in the deck.
    "Gwynn": can_play_gwynn,
    "Fighting Gong": lambda state, me: any(
        p_basic_fighting_energy_or_basic_fighting_pokemon(c) for c in me.deck),
    # Premium Power Pro: v0 policy — only when the buff can actually be cashed in THIS
    # turn, i.e. our Active is a Fighting Pokémon (the one that will attack) and the
    # opponent has an Active to hit. Otherwise greedy would burn it for nothing.
    "Premium Power Pro": lambda state, me: (
        me.active is not None and "Fighting" in me.active.card.types
        and state.players[1 - state.active_index].active is not None),
    # Wally's Compassion: needs a DAMAGED Mega Evolution Pokémon ex of yours — with no
    # damage the card heals nothing and its Energy-bounce clause (conditional on having
    # healed) never fires, so it would waste the turn's Supporter for zero effect.
    # v0 POLICY on top of that legality floor: require at least HALF the Pokémon's
    # maximum HP in damage. The heal is not free — it also takes every Energy off the
    # healed Pokémon — so on a chip hit greedy would disarm its own attacker to undo 10
    # damage. Same shape as Premium Power Pro's and Cursed Blast's v0 guards; a searching
    # agent can own the real timing later.
    "Wally's Compassion": lambda state, me: any(
        p_mega_evolution_ex(m.card) and m.damage * 2 >= m.max_hp
        for m in me.all_in_play()),
    "Prime Catcher": can_play_prime_catcher,
}


# --------------------------------------------------------------------------- #
# POKÉMON TOOLS (§2.8) + SPECIAL ENERGY (§2.10)
# Passive Tool modifiers (Air Balloon retreat −2) live in game.retreat_cost.
# End-of-turn Tool triggers (Powerglass) run here. Tools with NO active behavior
# (purely passive) are listed in TOOL_IMPLEMENTED so the coverage test counts them.
# --------------------------------------------------------------------------- #
TOOL_IMPLEMENTED: set[str] = {"Air Balloon", "Powerglass",
                              # Passive damage/draw Tools handled inside apply_attack_damage:
                              #   Brave Bangle (+30 to opp Active ex for a non-Rule-Box holder),
                              #   Lucky Helmet (holder draws 2 when its Active is damaged).
                              "Brave Bangle", "Lucky Helmet",
                              # Passive max-HP Tool -> TOOL_HP_MODIFIERS / refresh_hp_modifiers:
                              #   Cynthia's Power Weight (+70 HP to a Cynthia's Pokémon),
                              #   Hero's Cape (+100 HP, ACE SPEC, no holder restriction).
                              "Cynthia's Power Weight", "Hero's Cape",
                              # Passive prize-reduction-on-KO Tool -> _ko_cleanup (same
                              # chokepoint as Legacy Energy, gated on holder name "Lillie's*").
                              "Lillie's Pearl"}

# Abilities handled OUTSIDE the ATTACK/ABILITY registries (passives), but still
# faithful — the coverage test treats these as implemented. (Agile -> retreat_cost.)
# Abilities handled outside the active-use ABILITY_EFFECTS registry (passives or
# on-bench triggers), but still faithful — the coverage test counts these.
PASSIVE_ABILITIES: set[tuple[str, str]] = {
    ("Charmander", "Agile"),                 # -> retreat_cost
    ("Meowth ex", "Last-Ditch Catch"),       # -> ON_BENCH_TRIGGERS
    ("Drilbur (TEF)", "Dig Dig Dig"),         # -> ON_BENCH_TRIGGERS
    # Passive damage-prevention walls -> apply_attack_damage / place_counters.
    ("Crustle", "Mysterious Rock Inn"),
    ("Milotic ex", "Sparkling Scales"),
    ("Cornerstone Mask Ogerpon ex", "Cornerstone Stance"),
    # Passive dynamic-cost modifier -> effective_cost.
    ("Bloodmoon Ursaluna ex", "Seasoned Skill"),
    # Passive board-wide retreat modifier -> game.retreat_cost (skyliner_free_retreat).
    ("Latias ex", "Skyliner"),
    # Passive bench damage-prevention for the owner's non-Rule-Box Bench ->
    # apply_attack_damage (the bench chokepoint, next to Tera's bench immunity).
    ("Shaymin (DRI)", "Flower Curtain"),
    # Passive pre-W/R damage boost for your Cynthia's Pokémon -> apply_attack_damage
    # (same chokepoint as Brave Bangle / Kieran; copies stack).
    ("Cynthia's Roserade", "Cheer On to Glory"),
    # Passive board-wide Weakness rewrite -> _fairy_zone_active, consulted inside
    # _apply_weakness_resistance. (Was implemented at the chokepoint but never recorded
    # here, so the gap-check reported a working card as missing.)
    ("Lillie's Clefairy ex", "Fairy Zone"),
    # Passive effect-prevention on the holder -> hide_n_sneak_prevents_effect, consulted
    # in place_counters and effect_prevented_on. Damage is explicitly NOT an effect.
    ("Shuppet (PBL)", "Hide 'n' Sneak"),
    ("Banette (PBL)", "Hide 'n' Sneak"),
    ("Poltchageist (PBL)", "Hide 'n' Sneak"),
    ("Sinistcha (PBL)", "Hide 'n' Sneak"),
    # Passive board-wide ban on MOVING damage counters -> damage_counter_move_blocked,
    # consulted by Munkidori's Adrena-Brain (the engine's only counter-move effect).
    ("Patrat (CRI)", "Watchful Eye"),
    # Passive Ability lock on the opposing ACTIVE -> ability_suppressed
    # (_midnight_fluttering_suppressed).
    ("Flutter Mane", "Midnight Fluttering"),
    # On-bench-from-hand trigger -> ON_BENCH_TRIGGERS (switch + Energy move).
    ("Iron Leaves ex", "Rapid Vernier"),
    # On-evolve-from-hand trigger -> ON_EVOLVE_TRIGGERS (Tera-gated Trainer search).
    ("Noctowl", "Jewel Seeker"),
    # Passive flat −30 attack damage AFTER W/R -> flat_damage_reduction, consulted in
    # apply_attack_damage at the same point as Protect Charge's one-turn rider.
    ("Mega Diancie ex", "Diamond Coat"),
}


def end_of_turn_tools(state: GameState, player: PlayerState) -> None:
    """Run end-of-turn Pokémon Tool triggers for `player`. Powerglass: if the
    holder is in the Active Spot, attach a Basic Energy from discard to it.
    Silently does nothing while Jamming Tower is in play (Tools have no effect)."""
    if tools_disabled(state):
        return
    if player.active is not None and player.active.tool is not None \
            and player.active.tool.name == "Powerglass":
        for i, c in enumerate(player.discard):
            if c.is_basic_energy:
                player.active.energy.append(player.discard.pop(i))
                state.emit(f"Powerglass: attached {c.name} from discard")
                break


def _enriching_on_attach(ctx: EffectContext) -> None:
    """Enriching Energy: when attached from hand to a Pokémon, draw 4 cards."""
    draw(ctx, 4)
    ctx.state.emit("Enriching Energy: drew 4")


def _telepathic_on_attach(ctx: EffectContext) -> None:
    """Telepathic Psychic Energy: provides Psychic Energy (via the pool entry's
    types=['Psychic']). When attached from hand to a Psychic Pokémon, search your deck
    for up to 2 Basic Psychic Pokémon and put them onto your Bench, then shuffle."""
    if ctx.source is None or "Psychic" not in ctx.source.card.types:
        return
    n = search_deck(ctx, [p_basic_psychic_pokemon] * 2, dest="bench")
    if n:
        ctx.state.emit(f"Telepathic Psychic Energy: benched {n} Basic Psychic Pokémon")


SPECIAL_ENERGY_ON_ATTACH: dict[str, Callable[[EffectContext], None]] = {
    "Enriching Energy": _enriching_on_attach,
    "Telepathic Psychic Energy": _telepathic_on_attach,
}
# Special Energy whose behavior is PASSIVE (no on-attach trigger), handled at the
# chokepoint named against each. Listed so the coverage test counts them as implemented.
SPECIAL_ENERGY_PASSIVE: set[str] = {
    # Rocky Fighting Energy: provides [F] via its pool `types` (state.provided_types), and
    # "Prevent all effects of attacks used by your opponent's Pokémon done to the [F]
    # Pokémon this card is attached to" -> rocky_fighting_prevents_effect, consulted in
    # place_counters and effect_prevented_on. Damage is explicitly NOT an effect.
    "Rocky Fighting Energy",
    # Neo Upper Energy (ACE SPEC): "it provides Colorless Energy. If this card is attached
    # to a Stage 2 Pokémon, this card provides every type of Energy but provides only 2
    # Energy at a time." -> InPlayPokemon.provided_types emits two "Any" wildcard units on
    # a Stage 2 holder (one Colorless otherwise), and game.can_pay_cost consumes units, so
    # a lone copy on Cynthia's Garchomp ex pays Draconic Buster's [F][F].
    # PRECISE SCOPE: this covers paying ATTACK costs only. energy_count() still counts
    # CARDS, so the "2 Energy at a time" amount is NOT reflected in retreat cost or in
    # texts that count Energy attached — an uncovered edge, deliberately not claimed.
    "Neo Upper Energy",
    # Prism Energy: "it provides Colorless Energy. If this card is attached to a Basic
    # Pokémon, this card provides every type of Energy but provides only 1 Energy at a
    # time." -> one "Any" wildcard unit on a Basic holder (see provided_types), same
    # chokepoint as Neo Upper Energy and the same ATTACK-cost-only scope.
    "Prism Energy",
    # Legacy Energy (ACE SPEC): two clauses, both handled.
    #   1. "it provides every type of Energy but provides only 1 Energy at a time" ->
    #      InPlayPokemon.provided_types emits one "Any" wildcard unit, UNCONDITIONALLY
    #      (no stage clause, unlike Prism / Neo Upper Energy). Same ATTACK-cost-only
    #      scope: energy_count() still counts CARDS.
    #   2. "If the Pokémon this card is attached to is Knocked Out by damage from an
    #      attack from your opponent's Pokémon, that player takes 1 fewer Prize card.
    #      This effect of your Legacy Energy can't be applied more than once per game."
    #      -> _ko_cleanup, using the KO-cause flag set in apply_attack_damage and the
    #      per-player, per-game budget PlayerState.legacy_energy_prize_reduction_used.
    "Legacy Energy",
    # Mist Energy: provides Colorless via the default provided_types() path (its pool
    # `types` is empty, same as Rocky Fighting Energy's plain-typed cards) ->
    # mist_energy_prevents_effect, consulted in place_counters and effect_prevented_on.
    # Identical scope to Rocky Fighting Energy, just no holder-type restriction.
    "Mist Energy",
    # Spiky Energy: provides Colorless (same default path). "If the Pokémon this card is
    # attached to is in the Active Spot and is damaged by an attack from your opponent's
    # Pokémon (even if this Pokémon is Knocked Out), put 2 damage counters on the
    # Attacking Pokémon." -> checked directly in apply_attack_damage, right after the
    # Shellnado Spin retaliation block (same place_counters call, 2 counters not 12).
    "Spiky Energy",
}
SPECIAL_ENERGY_IMPLEMENTED: set[str] = set(SPECIAL_ENERGY_ON_ATTACH) | SPECIAL_ENERGY_PASSIVE


def get_special_energy_on_attach(card_name: str):
    return SPECIAL_ENERGY_ON_ATTACH.get(card_name)


def get_attack_effect(card_name: str, attack_name: str):
    return ATTACK_EFFECTS.get((card_name, attack_name))


def get_ability_effect(card_name: str, ability_name: str):
    return ABILITY_EFFECTS.get((card_name, ability_name))


def get_trainer_effect(card_name: str):
    return TRAINER_EFFECTS.get(card_name)


def can_play_trainer(state, me, card_name: str) -> bool:
    pred = _TRAINER_CAN_PLAY.get(card_name)
    return pred(state, me) if pred else (card_name in TRAINER_EFFECTS)


# ============================================================================ #
# §META-2026-08 — the three live-metagame archetypes the gauntlet couldn't see:
# Dragapult Blaziken (5.99% share), Festival Lead (6.75%), Grimmsnarl Froslass
# (4.66%). Card text sources: the live pool JSON + limitlesstcg card pages for
# the three manual-supplement additions (Seaking (PRE), Applin (SCR), Gladion's
# Final Battle). Every effect below is asserted against its real text in
# tests/test_blaziken_line.py / test_festival_lead.py / test_grimmsnarl_line.py.
# ============================================================================ #

def has_festival_lead(card) -> bool:
    """Does this card carry the Festival Lead Ability (Dipplin / Goldeen /
    Seaking (PRE))? Read off the card's own ability list, never a name table —
    a future print with the Ability works unchanged."""
    return any(a.name == "Festival Lead" for a in (card.abilities or []))


def pokemon_checkup(state: GameState) -> None:
    """The between-turns Pokémon Checkup window, called from game.end_turn.

    Resident: Froslass "Freezing Shroud" — "During Pokémon Checkup, put 1 damage
    counter on each Pokémon that has an Ability (both yours and your opponent's),
    except any Froslass." EACH un-suppressed Froslass in play triggers separately
    (two Froslass = 2 counters per ability-haver per Checkup); a suppressed one
    (Watchtower / Midnight Fluttering) does not. Checkup counters are not an
    attack, so attack-scoped walls (Battle Cage, Rocky Fighting Energy, Dig's
    shield) do NOT prevent them — damage is applied directly, then knockouts are
    processed with normal prize awards."""
    shrouds = sum(
        1 for pl in state.players for m in pl.all_in_play()
        if m.card.name == "Froslass"
        and any(a.name == "Freezing Shroud" for a in (m.card.abilities or []))
        and not ability_suppressed(state, m))
    if not shrouds:
        return
    hit = 0
    for pl in state.players:
        for m in pl.all_in_play():
            if m.card.name == "Froslass":
                continue
            if m.card.abilities:
                m.damage += 10 * shrouds
                hit += 1
    if hit:
        state.emit(f"Freezing Shroud ×{shrouds}: 1 counter on {hit} Pokémon with Abilities")
        process_knockouts(state)


def can_be_conditioned(state: GameState, mon: InPlayPokemon) -> bool:
    """Festival Grounds (Stadium): "Each Pokémon that has any Energy attached (both
    yours and your opponent's) recovers from all Special Conditions and can't be
    affected by any Special Conditions." Confusion is the engine's one modeled
    Condition, so this is the whole gate."""
    return not (current_stadium_name(state) == "Festival Grounds" and mon.energy)


# --- Dragapult Blaziken ------------------------------------------------------ #

def _seething_spirit(ctx: EffectContext) -> None:
    """Blaziken ex Ability: "Once during your turn, you may attach a Basic Energy card
    from your discard pile to 1 of your Pokémon." Policy (the '1 of your Pokémon'
    choice, a hook MCTS can own): the Active if it still needs Energy for any printed
    attack cost, else the least-loaded Benched attacker (an ex first)."""
    me = ctx.me
    pool = [c for c in me.discard if c.is_basic_energy]
    if not pool:
        return
    def needs(mon):
        if mon is None:
            return False
        need = max((len(a.cost) for a in mon.card.attacks or []), default=0)
        return len(mon.energy) < need
    target = me.active if needs(me.active) else None
    if target is None:
        cands = [m for m in me.bench if needs(m)] or list(me.bench) or ([me.active] if me.active else [])
        if not cands:
            return
        cands.sort(key=lambda m: (0 if "ex" in m.card.subtypes else 1, len(m.energy)))
        target = cands[0]
    card = pool[0]
    me.discard.remove(card)
    target.energy.append(card)
    ctx.state.emit(f"Seething Spirit: attached {card.name} from discard to {target.card.name}")


def _smolder_sault(ctx: EffectContext) -> None:
    """Blaziken ex: 200 (engine-applied). "During your next turn, this Pokémon can't
    attack." Same pending-lock hop as Metal Slash / Eon Blade."""
    ctx.source.pending_cannot_attack = True
    ctx.state.emit("Smolder-sault: Blaziken ex can't attack next turn")


# --- Grimmsnarl Froslass ----------------------------------------------------- #

def _filch(ctx: EffectContext) -> None:
    """Marnie's Impidimp: (0) Draw a card."""
    draw(ctx, 1)


def _punk_up(ctx: EffectContext) -> None:
    """Marnie's Grimmsnarl ex on-evolve Ability: "When you play this Pokémon from your
    hand to evolve 1 of your Pokémon during your turn, you may search your deck for up
    to 5 Basic Darkness Energy cards and attach them to your Marnie's Pokémon in any
    way you like. Then, shuffle your deck." Distribution policy: fill the evolving
    Grimmsnarl to Shadow Bullet's [D][D] plus retreat slack (3), then round-robin the
    rest across other Marnie's Pokémon."""
    me = ctx.me
    found = [c for c in me.deck if c.is_basic_energy and "Darkness" in c.types][:5]
    if not found:
        return
    for c in found:
        me.deck.remove(c)
    ctx.state.rng.shuffle(me.deck)
    targets = [m for m in me.all_in_play() if m.card.name.startswith("Marnie's")]
    if not targets:
        targets = [ctx.source]
    for c in found:
        # the evolved mon first, up to 3; then the least-loaded other Marnie's
        if ctx.source in targets and len(ctx.source.energy) < 3:
            tgt = ctx.source
        else:
            tgt = min(targets, key=lambda m: len(m.energy))
        tgt.energy.append(c)
    ctx.state.emit(f"Punk Up: attached {len(found)} Basic Darkness Energy from the deck")


def _shadow_bullet(ctx: EffectContext) -> None:
    """Marnie's Grimmsnarl ex: 180 (engine-applied). "This attack also does 30 damage
    to 1 of your opponent's Benched Pokémon. (Don't apply Weakness and Resistance for
    Benched Pokémon.)" Bench DAMAGE, not counters — so Tera / Flower Curtain / bench
    walls get their say at the chokepoint. Target policy: a KO if one exists, else the
    most-damaged bencher."""
    bench = [m for m in ctx.opp.bench if not m.is_knocked_out]
    if not bench:
        return
    ko = [m for m in bench if m.remaining_hp <= 30]
    target = min(ko, key=lambda m: m.remaining_hp) if ko else max(bench, key=lambda m: m.damage)
    apply_attack_damage(ctx, target, 30, owner=ctx.opp, source=ctx.source)


def _astonish(ctx: EffectContext) -> None:
    """Snorunt: 20 (engine-applied). "Choose a random card from your opponent's hand.
    Your opponent reveals that card and shuffles it into their deck." Random via the
    game RNG — deterministic per seed."""
    if not ctx.opp.hand:
        return
    i = ctx.rng.randrange(len(ctx.opp.hand))
    card = ctx.opp.hand.pop(i)
    ctx.opp.deck.append(card)
    ctx.rng.shuffle(ctx.opp.deck)
    ctx.state.emit(f"Astonish: {card.name} shuffled from the opponent's hand into their deck")


def _corrosive_winds(ctx: EffectContext) -> None:
    """Yveltal: (0) "Put 2 damage counters on each of your opponent's Pokémon that has
    any damage counters on it." Counters (an attack effect), so the counter walls
    apply per target."""
    for m in [ctx.opp.active] + list(ctx.opp.bench):
        if m is not None and m.damage > 0 and not m.is_knocked_out:
            place_counters(ctx, m, 2, owner=ctx.opp)


def _destructive_beam(ctx: EffectContext) -> None:
    """Yveltal: 100 (engine-applied). "Flip a coin. If heads, discard an Energy from
    your opponent's Active Pokémon."""
    if flip(ctx) and ctx.opp.active is not None and ctx.opp.active.energy:
        card = ctx.opp.active.energy.pop()
        ctx.opp.discard.append(card)
        ctx.state.emit(f"Destructive Beam: discarded {card.name}")


def _attract_customers(ctx: EffectContext) -> None:
    """Tatsugiri Ability (Active only — gated in ABILITY_CAN_USE): "look at the top 6
    cards of your deck, reveal a Supporter card you find there, and put it into your
    hand. Shuffle the other cards back into your deck."""
    me = ctx.me
    window = [me.deck.pop(0) for _ in range(min(6, len(me.deck)))]
    supporters = [c for c in window if p_supporter(c)]
    if supporters:
        pick = max(supporters, key=_search_value)
        window.remove(pick)
        me.hand.append(pick)
        ctx.state.emit(f"Attract Customers: took {pick.name}")
    me.deck.extend(window)
    ctx.rng.shuffle(me.deck)


def _iris_fighting_spirit(ctx: EffectContext) -> bool:
    """Supporter: "You can use this card only if you discard another card from your
    hand. Draw cards until you have 6 cards in your hand." Discard policy: the
    lowest-search-value hand card (Energy before spare Trainers before Pokémon)."""
    me = ctx.me
    if not me.hand:
        return False
    toss = min(me.hand, key=_search_value)
    me.hand.remove(toss)
    me.discard.append(toss)
    need = 6 - len(me.hand)
    drew = me.draw(need) if need > 0 else 0
    ctx.state.emit(f"Iris's Fighting Spirit: discarded {toss.name}, drew {drew}")
    return True


# --- Festival Lead ----------------------------------------------------------- #

def _do_the_wave(ctx: EffectContext) -> None:
    """Dipplin: 20× — "This attack does 20 damage for each of your Benched Pokémon."
    (Variable '×': owns its damage so Weakness multiplies the total once.)"""
    damage_active_with_weakness(ctx, 20 * len(ctx.me.bench))


def _whirlpool(ctx: EffectContext) -> None:
    """Goldeen: 10 (engine-applied). "Flip a coin. If heads, discard an Energy from
    your opponent's Active Pokémon."""
    if flip(ctx) and ctx.opp.active is not None and ctx.opp.active.energy:
        card = ctx.opp.active.energy.pop()
        ctx.opp.discard.append(card)
        ctx.state.emit(f"Whirlpool: discarded {card.name}")


def _peck_off(ctx: EffectContext) -> None:
    """Seaking (TWM): 50 (engine-applied). "Before doing damage, discard all Pokémon
    Tools from your opponent's Active Pokémon." The engine applies base damage before
    the effect hook, so 'before' ordering only matters for damage-modifying Tools —
    none of which are defender-side today; the discard itself is exact."""
    mon = ctx.opp.active
    if mon is not None and mon.tool is not None:
        ctx.opp.discard.append(mon.tool)
        ctx.state.emit(f"Peck Off: discarded {mon.tool.name}")
        mon.tool = None


def _rapid_draw(ctx: EffectContext) -> None:
    """Seaking (PRE): 60 (engine-applied). "Draw 2 cards."""
    draw(ctx, 2)


def _tumbling_attack(ctx: EffectContext) -> None:
    """Applin (TWM): 10+ — "Flip a coin. If heads, this attack does 20 more damage."""
    damage_active_with_weakness(ctx, 30 if flip(ctx) else 10)


def _slight_intrusion(ctx: EffectContext) -> None:
    """Rellor: 30 (engine-applied). "This Pokémon also does 10 damage to itself."""
    ctx.source.damage += 10


def _rabsca_psychic(ctx: EffectContext) -> None:
    """Rabsca: 10+ — "This attack does 30 more damage for each Energy attached to your
    opponent's Active Pokémon." Energy CARDS attached (energy_count counts cards)."""
    n = ctx.opp.active.energy_count() if ctx.opp.active is not None else 0
    damage_active_with_weakness(ctx, 10 + 30 * n)


def _boom_boom_groove(ctx: EffectContext) -> None:
    """Thwackey Ability: "Once during your turn, if your Active Pokémon has the
    Festival Lead Ability, you may search your deck for a card and put it into your
    hand. Then, shuffle your deck." ANY card — the deck's universal tutor."""
    if search_deck(ctx, [lambda c: True], dest="hand"):
        ctx.state.emit("Boom Boom Groove: searched a card")


def _gladions_final_battle(ctx: EffectContext) -> bool:
    """Supporter: "You can use this card only when it is the last card in your hand.
    During this turn, attacks used by your Pokémon that don't have a Rule Box do 80
    more damage to your opponent's Active Pokémon (before applying Weakness and
    Resistance)." The last-card condition lives in _TRAINER_CAN_PLAY (checked while
    the card is still in hand); by the time this effect runs the hand is empty."""
    ctx.me.bonus_damage_nonrulebox = 80
    ctx.state.emit("Gladion's Final Battle: +80 for non-Rule-Box attackers this turn")
    return True


ATTACK_EFFECTS.update({
    ("Blaziken ex", "Smolder-sault"): _smolder_sault,
    ("Marnie's Impidimp", "Filch"): _filch,
    ("Marnie's Grimmsnarl ex", "Shadow Bullet"): _shadow_bullet,
    ("Snorunt", "Astonish"): _astonish,
    ("Yveltal", "Corrosive Winds"): _corrosive_winds,
    ("Yveltal", "Destructive Beam"): _destructive_beam,
    ("Dipplin", "Do the Wave"): _do_the_wave,
    ("Goldeen", "Whirlpool"): _whirlpool,
    ("Seaking", "Peck Off"): _peck_off,
    ("Seaking (PRE)", "Rapid Draw"): _rapid_draw,
    ("Applin", "Tumbling Attack"): _tumbling_attack,
    ("Rellor", "Slight Intrusion"): _slight_intrusion,
    ("Rabsca", "Psychic"): _rabsca_psychic,
})

ATTACK_EFFECT_OWNS_DAMAGE.update({
    ("Dipplin", "Do the Wave"),
    ("Applin", "Tumbling Attack"),
    ("Rabsca", "Psychic"),
})

ABILITY_EFFECTS.update({
    ("Blaziken ex", "Seething Spirit"): _seething_spirit,
    ("Tatsugiri", "Attract Customers"): _attract_customers,
    ("Thwackey", "Boom Boom Groove"): _boom_boom_groove,
})

ABILITY_CAN_USE.update({
    ("Blaziken ex", "Seething Spirit"):
        lambda state, me, mon: any(c.is_basic_energy for c in me.discard),
    ("Tatsugiri", "Attract Customers"):
        lambda state, me, mon: mon is me.active and len(me.deck) > 0,
    ("Thwackey", "Boom Boom Groove"):
        lambda state, me, mon: (me.active is not None
                                and has_festival_lead(me.active.card)
                                and len(me.deck) > 0),
})

ON_EVOLVE_TRIGGERS.update({
    "Marnie's Grimmsnarl ex": _punk_up,
})

TRAINER_EFFECTS.update({
    "Iris's Fighting Spirit": _iris_fighting_spirit,
    "Gladion's Final Battle": _gladions_final_battle,
})

_TRAINER_CAN_PLAY.update({
    # needs another card to discard, and a deck to draw from
    "Iris's Fighting Spirit": lambda state, me: len(me.hand) >= 2 and len(me.deck) > 0,
    # "only when it is the last card in your hand" — evaluated pre-pop, so the hand
    # holds exactly this card
    "Gladion's Final Battle": lambda state, me: len(me.hand) == 1,
})
