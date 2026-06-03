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


def draw(ctx: EffectContext, n: int) -> int:
    return ctx.me.draw(n)


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
STADIUM_IMPLEMENTED: set[str] = {"Battle Cage"}


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
    """Award prizes to the CURRENT player for every opposing Pokemon that is now
    knocked out, move KO'd cards to discard, and promote a new Active if needed.
    """
    scorer = state.current
    victim = state.opponent

    # bench KOs first (order doesn't affect prize count)
    survivors = []
    for m in victim.bench:
        if m.is_knocked_out:
            _ko_cleanup(state, scorer, victim, m)
        else:
            survivors.append(m)
    victim.bench = survivors

    # active KO
    if victim.active and victim.active.is_knocked_out:
        ko = victim.active
        victim.active = None
        _ko_cleanup(state, scorer, victim, ko)
        _promote(victim)


def _ko_cleanup(state, scorer, victim, mon) -> None:
    prizes = mon.card.gives_up_prizes
    victim.discard.append(mon.card)
    victim.discard.extend(mon.energy)
    victim.discard.extend(mon.evolved_from)
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


# (card_name, attack_name) -> effect
ATTACK_EFFECTS: dict[tuple[str, str], Callable[[EffectContext], None]] = {
    ("Dragapult ex", "Phantom Dive"): _phantom_dive,
    ("Raging Bolt ex", "Bellowing Thunder"): _bellowing_thunder,
    ("Raging Bolt ex", "Burst Roar"): _burst_roar,
    ("Teal Mask Ogerpon ex", "Myriad Leaf Shower"): _myriad_leaf_shower,
    ("Mega Charizard X ex", "Inferno X"): _inferno_x,
}

# (card_name, ability_name) -> effect
ABILITY_EFFECTS: dict[tuple[str, str], Callable[[EffectContext], None]] = {
    ("Drakloak", "Recon Directive"): _recon_directive,
    ("Teal Mask Ogerpon ex", "Teal Dance"): _teal_dance,
}

# Optional usability guards so the engine never offers an ability that would do
# nothing (and let greedy waste it). (card_name, ability_name) -> pred(me, mon).
ABILITY_CAN_USE: dict[tuple[str, str], Callable] = {
    # Teal Dance needs a Basic Grass Energy in hand to attach.
    ("Teal Mask Ogerpon ex", "Teal Dance"):
        lambda me, mon: any(c.is_basic_energy and "Grass" in c.types for c in me.hand),
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


# card_name -> (effect, can_play_predicate)
# can_play takes (state, me) and returns bool.
TRAINER_EFFECTS: dict[str, Callable[[EffectContext], bool]] = {
    "Rare Candy": _rare_candy,
    "Buddy-Buddy Poffin": _buddy_buddy_poffin,
    "Cheren": _cheren,
    "Boss's Orders": _boss_orders,
}

_TRAINER_CAN_PLAY: dict[str, Callable] = {
    "Rare Candy": can_play_rare_candy,
    "Buddy-Buddy Poffin": can_play_poffin,
    "Cheren": can_play_cheren,
    "Boss's Orders": lambda state, me: len(state.players[1 - state.active_index].bench) > 0,
}


def get_attack_effect(card_name: str, attack_name: str):
    return ATTACK_EFFECTS.get((card_name, attack_name))


def get_ability_effect(card_name: str, ability_name: str):
    return ABILITY_EFFECTS.get((card_name, ability_name))


def get_trainer_effect(card_name: str):
    return TRAINER_EFFECTS.get(card_name)


def can_play_trainer(state, me, card_name: str) -> bool:
    pred = _TRAINER_CAN_PLAY.get(card_name)
    return pred(state, me) if pred else (card_name in TRAINER_EFFECTS)
