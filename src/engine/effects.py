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
        target.damage += 10


def heal(ctx: EffectContext, mon: InPlayPokemon, amount: int) -> None:
    mon.damage = max(0, mon.damage - amount)


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


# (card_name, attack_name) -> effect
ATTACK_EFFECTS: dict[tuple[str, str], Callable[[EffectContext], None]] = {
    ("Dragapult ex", "Phantom Dive"): _phantom_dive,
}

# (card_name, ability_name) -> effect
ABILITY_EFFECTS: dict[tuple[str, str], Callable[[EffectContext], None]] = {
    ("Drakloak", "Recon Directive"): _recon_directive,
}


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
