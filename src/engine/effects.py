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
    for _ in range(counters):
        alive = [m for m in bench if not m.is_knocked_out]
        if not alive:
            break
        if policy == "maximize_ko":
            # target the lowest remaining HP (closest to KO)
            target = min(alive, key=lambda m: m.remaining_hp)
        else:  # "spread"
            target = max(alive, key=lambda m: m.remaining_hp)
        # route through the chokepoint so Battle Cage can prevent the counter
        place_counters(ctx, target, 1, owner=ctx.opp)


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
        if dest == "bench" and len(me.bench) >= PlayerState.MAX_BENCH:
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
STADIUM_IMPLEMENTED: set[str] = {"Battle Cage", "Team Rocket's Watchtower"}


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


def can_play_stadium(state: GameState, card) -> bool:
    """A Stadium is playable unless one with the SAME name is already in play
    (a same-name Stadium can't replace itself)."""
    return state.stadium is None or state.stadium.name != card.name


def _apply_weakness_resistance(source_card, defender: InPlayPokemon, dmg: int) -> int:
    """×2 Weakness / flat Resistance based on the SOURCE's first type. (Only the
    Active takes W/R; bench-damage attacks say 'don't apply W/R for Benched'.)"""
    if dmg <= 0:
        return dmg
    stypes = source_card.types if source_card else ()
    for wtype, _ in defender.card.weaknesses:
        if stypes and wtype == stypes[0]:
            dmg *= 2
    for rtype, rval in defender.card.resistances:
        if stypes and rtype == stypes[0]:
            try:
                dmg = max(0, dmg + int(rval))
            except ValueError:
                pass
    return dmg


def apply_attack_damage(ctx: EffectContext, target: InPlayPokemon, amount: int,
                        owner: Optional[PlayerState] = None,
                        source: Optional[InPlayPokemon] = None) -> int:
    """Deal `amount` ATTACK damage to `target`. Applies Weakness/Resistance to an
    Active target, and Tera bench-immunity to a Benched one. Returns damage dealt."""
    if target is None or amount <= 0:
        return 0
    if getattr(target, "shielded", False):     # Dunsparce Dig: immune to attack damage
        ctx.state.emit(f"{target.card.name} is shielded — no attack damage")
        return 0
    owner = owner if owner is not None else owner_of(ctx.state, target)
    source = source if source is not None else ctx.source
    on_bench = owner is not None and _on_bench(owner, target)
    dmg = amount
    if not on_bench:
        dmg = _apply_weakness_resistance(source.card if source else None, target, dmg)
    # Tera: "Prevent all damage done to this Pokémon by attacks while on your Bench."
    if on_bench and "Tera" in target.card.subtypes:
        ctx.state.emit(f"Tera: prevented {dmg} attack damage to benched {target.card.name}")
        return 0
    if dmg > 0:
        target.damage += dmg
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
    owner = owner if owner is not None else owner_of(ctx.state, target)
    on_bench = owner is not None and _on_bench(owner, target)
    if (on_bench and owner is not ctx.me
            and current_stadium_name(ctx.state) == "Battle Cage"):
        ctx.state.emit(f"Battle Cage: prevented {counters} counter(s) on benched "
                       f"{target.card.name}")
        return 0
    target.damage += counters * 10
    return counters


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
    """
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


def _ko_cleanup(state, scorer, victim, mon) -> None:
    prizes = mon.card.gives_up_prizes
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
    """Munkidori: 60, and the opponent's Active is now Confused."""
    if ctx.opp.active:
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
        if placed >= 3 or len(ctx.me.bench) >= PlayerState.MAX_BENCH:
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


# Attacks where the registered EFFECT computes/places ALL the damage, so the engine
# must apply 0 base (otherwise the printed number would hit the Active a SECOND time
# on top of the effect's chosen-target damage). Variable-damage ("+"/"×") attacks
# are already handled separately.
ATTACK_EFFECT_OWNS_DAMAGE: set[tuple[str, str]] = {
    ("Mega Charizard Y ex", "Explosion Y"),   # 280 to a CHOSEN Pokémon, not the Active
    ("Fan Rotom", "Assault Landing"),          # conditional (nothing without a Stadium)
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
    ("Moltres", "Fighting Wings"): _fighting_wings,
    ("Duskull", "Come and Get You"): _come_and_get_you,
    ("Dunsparce", "Dig"): _dig,
    ("Fan Rotom", "Assault Landing"): _assault_landing,
    ("Meowth ex", "Tuck Tail"): _tuck_tail,
    ("Klefki", "Stick 'n' Draw"): _stick_n_draw,
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
}

# Abilities usable any number of times per turn (not gated by ability_used_this_turn).
REPEATABLE_ABILITIES: set[tuple[str, str]] = {("Oricorio ex", "Excited Turbo")}

# Abilities that fire when the Pokémon is played from hand onto the Bench.
# card_name -> effect(ctx with source = the new Pokémon).
ON_BENCH_TRIGGERS: dict[str, Callable[[EffectContext], None]] = {
    "Meowth ex": _last_ditch_catch,
}


def is_repeatable_ability(card_name: str, ability_name: str) -> bool:
    return (card_name, ability_name) in REPEATABLE_ABILITIES


def get_on_bench_trigger(card_name: str):
    return ON_BENCH_TRIGGERS.get(card_name)


def ability_suppressed(state: GameState, mon: InPlayPokemon) -> bool:
    """Team Rocket's Watchtower: Colorless Pokémon (both players) have no Abilities."""
    return ("Colorless" in mon.card.types
            and current_stadium_name(state) == "Team Rocket's Watchtower")


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
    # Adrena-Brain needs Darkness attached and a damaged Pokémon of yours to move from.
    ("Munkidori", "Adrena-Brain"):
        lambda state, me, mon: any("Darkness" in e.types for e in mon.energy)
            and any(m.damage >= 10 for m in me.all_in_play()),
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
            if (mon.card.name == basic_name
                    and not mon.played_this_turn
                    and not mon.evolved_this_turn):
                mon.evolved_from.append(mon.card)
                mon.card = ctx.me.hand.pop(hi)
                mon.evolved_this_turn = True
                mon.ability_used_this_turn = False
                ctx.state.emit(f"Rare Candy: {basic_name} -> {mon.card.name}")
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
                    m.card.name == basic_name and not m.played_this_turn
                    and not m.evolved_this_turn for m in me.all_in_play()):
                return True
    return False


def _buddy_buddy_poffin(ctx: EffectContext) -> bool:
    """Search deck for up to 2 Basic Pokemon with <=70 HP, put on bench."""
    space = PlayerState.MAX_BENCH - len(ctx.me.bench)
    if space <= 0:
        return False
    found = 0
    # prefer Basics that are evolution fodder (have something to evolve into)
    candidates = [c for c in ctx.me.deck
                  if c.is_pokemon and c.is_basic and (c.hp or 999) <= 70]
    candidates.sort(key=lambda c: (len(c.evolves_to) == 0, c.name))  # fodder first
    for c in candidates:
        if found >= 2 or len(ctx.me.bench) >= PlayerState.MAX_BENCH:
            break
        ctx.me.deck.remove(c)
        ctx.me.bench.append(InPlayPokemon(card=c, played_this_turn=True))
        found += 1
    ctx.rng.shuffle(ctx.me.deck) if ctx.rng else None
    if found:
        ctx.state.emit(f"Buddy-Buddy Poffin: benched {found} Basic(s)")
    return found > 0


def can_play_poffin(state, me) -> bool:
    if len(me.bench) >= PlayerState.MAX_BENCH:
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


# card_name -> (effect, can_play_predicate)
# can_play takes (state, me) and returns bool.
TRAINER_EFFECTS: dict[str, Callable[[EffectContext], bool]] = {
    "Rare Candy": _rare_candy,
    "Buddy-Buddy Poffin": _buddy_buddy_poffin,
    "Cheren": _cheren,
    "Boss's Orders": _boss_orders,
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
}


# --------------------------------------------------------------------------- #
# POKÉMON TOOLS (§2.8) + SPECIAL ENERGY (§2.10)
# Passive Tool modifiers (Air Balloon retreat −2) live in game.retreat_cost.
# End-of-turn Tool triggers (Powerglass) run here. Tools with NO active behavior
# (purely passive) are listed in TOOL_IMPLEMENTED so the coverage test counts them.
# --------------------------------------------------------------------------- #
TOOL_IMPLEMENTED: set[str] = {"Air Balloon", "Powerglass"}

# Abilities handled OUTSIDE the ATTACK/ABILITY registries (passives), but still
# faithful — the coverage test treats these as implemented. (Agile -> retreat_cost.)
# Abilities handled outside the active-use ABILITY_EFFECTS registry (passives or
# on-bench triggers), but still faithful — the coverage test counts these.
PASSIVE_ABILITIES: set[tuple[str, str]] = {
    ("Charmander", "Agile"),                 # -> retreat_cost
    ("Meowth ex", "Last-Ditch Catch"),       # -> ON_BENCH_TRIGGERS
}


def end_of_turn_tools(state: GameState, player: PlayerState) -> None:
    """Run end-of-turn Pokémon Tool triggers for `player`. Powerglass: if the
    holder is in the Active Spot, attach a Basic Energy from discard to it."""
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


SPECIAL_ENERGY_ON_ATTACH: dict[str, Callable[[EffectContext], None]] = {
    "Enriching Energy": _enriching_on_attach,
}
SPECIAL_ENERGY_IMPLEMENTED: set[str] = set(SPECIAL_ENERGY_ON_ATTACH)


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
