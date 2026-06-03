#!/usr/bin/env python3
"""
game.py — the deterministic rules engine. Zero LLM, zero tokens.

ELI15: this is the referee. It sets the board up, figures out which moves are
legal right now, applies the move an agent chooses, resolves attacks (including
weakness and knockouts), hands out prizes, and decides when someone has won.

SCOPE (v0 — honest about it):
  Implemented faithfully: setup + mulligan, 6 prizes, turn structure, draw,
    play Basic to bench, attach 1 energy/turn, evolve, retreat, attack with
    base damage, weakness/resistance, knockouts, prize-taking, all 3 win
    conditions, first-turn rules (no attack turn 1 by the starting player).
  Stubbed on purpose: attack EFFECT text (attacks do base damage only),
    abilities, Trainer card effects (Trainers are drawn but not played yet),
    special conditions (poison/sleep/etc.), special-energy bonus effects,
    variable damage ("×"/"+"). Each has a clean hook to fill later.

The stubs are WHY this stays token-free and fast — and why a wrong effect later
would silently corrupt results. Fidelity is added card-by-card, validated each time.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from .cards import Card, CardDB
from .state import GameState, InPlayPokemon, PlayerState, Phase
from . import effects as fx

STARTING_HAND = 7
PRIZE_COUNT = 6
MAX_TURNS = 200          # safety valve so a stalled game can't loop forever


# --------------------------------------------------------------------------- #
# Actions: the moves an agent can choose. Plain data; the engine applies them.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Action:
    kind: str                       # "attach_energy" | "play_basic" | "evolve" |
                                    # "retreat" | "attack" | "pass"
    hand_index: Optional[int] = None
    target_index: Optional[int] = None    # index into bench (or -1 for active)
    attack_index: Optional[int] = None

    def __repr__(self):
        return f"<{self.kind} h={self.hand_index} t={self.target_index} a={self.attack_index}>"


PASS = Action(kind="pass")


# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #
def _has_basic(hand: list[Card]) -> bool:
    return any(c.is_pokemon and c.is_basic for c in hand)


def setup_game(deck_a: list[Card], deck_b: list[Card], seed: Optional[int] = None,
               db: Optional[object] = None) -> GameState:
    """Shuffle, deal 7, mulligan until both have a Basic, place active + prizes.

    Coin flip decides who goes first. (The starting player skips their first
    attack — a real and measurable first/second-turn asymmetry.)
    """
    rng = random.Random(seed)
    pa = PlayerState(name="A", deck=list(deck_a))
    pb = PlayerState(name="B", deck=list(deck_b))

    for p in (pa, pb):
        # mulligan loop: reshuffle and redraw until the hand has a Basic Pokemon
        while True:
            rng.shuffle(p.deck)
            p.hand = []
            p.deck_draw_into_hand = None  # noqa (placeholder, unused)
            p.hand = [p.deck.pop(0) for _ in range(STARTING_HAND)]
            if _has_basic(p.hand):
                break
            p.deck.extend(p.hand)         # put hand back and try again

    state = GameState(players=(pa, pb), rng=rng)
    state.db = db
    state.active_index = rng.randint(0, 1)   # coin flip

    # each player puts one Basic active, then sets 6 prizes off the top
    for p in (pa, pb):
        basics = [i for i, c in enumerate(p.hand) if c.is_pokemon and c.is_basic]
        idx = basics[0]
        p.active = InPlayPokemon(card=p.hand.pop(idx))
        p.prizes = [p.deck.pop(0) for _ in range(PRIZE_COUNT)]

    state.phase = Phase.MAIN
    state.turn_number = 1
    state.emit(f"setup complete; {state.current.name} goes first")
    return state


# --------------------------------------------------------------------------- #
# Energy / cost checking
# --------------------------------------------------------------------------- #
def can_pay_cost(mon: InPlayPokemon, cost: tuple[str, ...]) -> bool:
    """Can this Pokemon's attached energy pay an attack cost?

    Colorless can be paid by anything. Typed symbols need a matching type (or a
    Colorless-providing energy as a fallback is NOT allowed for typed symbols).
    Simplified: we don't yet model special energy that provide 2+ units.
    """
    if len(mon.energy) < len(cost):
        return False
    provided = list(mon.provided_types())
    # satisfy typed requirements first
    for sym in cost:
        if sym == "Colorless":
            continue
        if sym in provided:
            provided.remove(sym)
        else:
            return False
    # remaining colorless requirements: any leftover energy counts
    colorless_needed = sum(1 for s in cost if s == "Colorless")
    return len(provided) >= colorless_needed


# --------------------------------------------------------------------------- #
# Legal action enumeration
# --------------------------------------------------------------------------- #
def legal_actions(state: GameState) -> list[Action]:
    p = state.current
    actions: list[Action] = [PASS]
    if p.active is None:
        return actions   # must promote first (handled in apply when active KO'd)

    # play a Basic Pokemon to the bench
    if len(p.bench) < PlayerState.MAX_BENCH:
        for i, c in enumerate(p.hand):
            if c.is_pokemon and c.is_basic:
                actions.append(Action("play_basic", hand_index=i))

    # attach one energy this turn (to active or any bench)
    if not p.energy_attached_this_turn:
        targets = [-1] + list(range(len(p.bench)))
        for i, c in enumerate(p.hand):
            if c.is_energy:
                for t in targets:
                    actions.append(Action("attach_energy", hand_index=i, target_index=t))

    # evolve: a hand card whose evolves_from matches an in-play Pokemon's name.
    # Timing rules: not on your first turn, not the turn the target was played,
    # and not a target that already evolved this turn.
    in_play = [(-1, p.active)] + list(enumerate(p.bench))
    if p.turns_taken >= 2:
        for i, c in enumerate(p.hand):
            if c.is_pokemon and c.evolves_from:
                for t, mon in in_play:
                    if (mon and mon.card.name == c.evolves_from
                            and not mon.played_this_turn
                            and not mon.evolved_this_turn):
                        actions.append(Action("evolve", hand_index=i, target_index=t))

    # play a Trainer (Item: any number; Supporter: one per turn; Stadium: one per
    # turn). Only offered if the card has an implemented, currently-playable effect.
    for i, c in enumerate(p.hand):
        if not c.is_trainer:
            continue
        if "Stadium" in c.subtypes:
            # Any Stadium can be played into the shared zone (its passive effect,
            # if any, is handled elsewhere); gated only by the once-per-turn and
            # same-name rules.
            if not p.stadium_played_this_turn and fx.can_play_stadium(state, c):
                actions.append(Action("play_stadium", hand_index=i))
            continue
        if c.is_supporter and p.supporter_played_this_turn:
            continue
        if fx.get_trainer_effect(c.name) and fx.can_play_trainer(state, p, c.name):
            actions.append(Action("play_trainer", hand_index=i))

    # use an activated ability (once per turn per Pokemon, if registered and able)
    for t, mon in in_play:
        if mon and not mon.ability_used_this_turn:
            for ab in mon.card.abilities:
                if fx.get_ability_effect(mon.card.name, ab.name):
                    guard = fx.get_ability_can_use(mon.card.name, ab.name)
                    if guard is None or guard(state, p, mon):
                        actions.append(Action("use_ability", target_index=t))

    # retreat (if enough energy and there's a bench Pokemon to promote)
    if p.bench and p.active.energy_count() >= p.active.card.retreat_cost:
        for t in range(len(p.bench)):
            actions.append(Action("retreat", target_index=t))

    # attack: starting player cannot attack on the very first turn
    first_turn_no_attack = (state.turn_number == 1)
    if not first_turn_no_attack:
        for ai, atk in enumerate(p.active.card.attacks):
            if can_pay_cost(p.active, atk.cost):
                actions.append(Action("attack", attack_index=ai))

    return actions


# --------------------------------------------------------------------------- #
# Applying actions
# --------------------------------------------------------------------------- #
def _resolve_attack(state: GameState, atk_index: int) -> None:
    attacker = state.current.active
    defender = state.opponent.active
    atk = attacker.card.attacks[atk_index]
    effect = fx.get_attack_effect(attacker.card.name, atk.name)
    ctx = fx.EffectContext(state=state, me=state.current, opp=state.opponent,
                           source=attacker, db=state.db, rng=state.rng)

    # Base damage handling:
    #   fixed ("")         -> engine applies atk.damage (+weakness)
    #   variable ("+"/"×") WITH a registered effect -> engine applies 0; the
    #       effect computes the full hit (so weakness multiplies the total once)
    #   variable WITHOUT an effect -> fall back to the printed base so the attack
    #       still does something sensible (e.g. Iron Thorns' Destructo-Press)
    if atk.damage_suffix in ("+", "×") and effect is not None:
        base = 0
    else:
        base = atk.damage

    # Direct attack damage goes through the chokepoint (Weakness/Resistance on the
    # Active; Tera bench-immunity for benched targets — n/a here since defender is
    # the Active, but the path is shared with bench-hitting effects).
    if base > 0 and defender is not None:
        dealt = fx.apply_attack_damage(ctx, defender, base, owner=state.opponent,
                                       source=attacker)
        state.emit(f"{attacker.card.name} used {atk.name} for {dealt}")

    # EFFECT HOOK: run the card's registered attack effect (spread, draw,
    # variable damage, etc.). Variable-damage attacks rely on this to land any hit.
    if effect:
        effect(ctx)
        state.emit(f"  effect: {atk.name}")

    # process ALL knockouts (active + bench, since effects can KO the bench)
    fx.process_knockouts(state)


def apply_action(state: GameState, action: Action) -> None:
    p = state.current

    if action.kind == "pass":
        return

    if action.kind == "play_basic":
        card = p.hand.pop(action.hand_index)
        p.bench.append(InPlayPokemon(card=card, played_this_turn=True))
        state.emit(f"benched {card.name}")
        return

    if action.kind == "attach_energy":
        card = p.hand.pop(action.hand_index)
        mon = p.active if action.target_index == -1 else p.bench[action.target_index]
        mon.energy.append(card)
        p.energy_attached_this_turn = True
        state.emit(f"attached {card.name} to {mon.card.name}")
        return

    if action.kind == "evolve":
        card = p.hand.pop(action.hand_index)
        mon = p.active if action.target_index == -1 else p.bench[action.target_index]
        mon.evolved_from.append(mon.card)
        # evolving removes special conditions (not modeled yet) and keeps damage
        mon.card = card
        mon.evolved_this_turn = True       # no second evolution step this turn
        mon.ability_used_this_turn = False  # the new stage's ability is fresh
        state.emit(f"evolved into {card.name}")
        # NOTE: current "Mega Evolution Pokémon ex" (lowercase ex; e.g. Mega Charizard
        # X/Y ex) have NO turn-ending rule — per the official 2026 rulebook (Appendix 1,
        # p23): "there are no special rules when it comes to playing Mega Evolution
        # Pokémon ex." The turn-end belonged to the rotated XY-era "Mega Evolution
        # Pokémon-EX" (uppercase). Their only drawback is the 3-prize KO (gives_up_prizes).
        return

    if action.kind == "retreat":
        # pay retreat cost: discard that many energy from the active
        cost = p.active.card.retreat_cost
        for _ in range(cost):
            if p.active.energy:
                p.discard.append(p.active.energy.pop())
        new_active = p.bench.pop(action.target_index)
        p.bench.append(p.active)
        p.active = new_active
        state.emit(f"retreated to {new_active.card.name}")
        return

    if action.kind == "play_stadium":
        card = p.hand.pop(action.hand_index)
        # discard the outgoing Stadium to whoever played it, then install the new one
        if state.stadium is not None and state.stadium_owner is not None:
            state.players[state.stadium_owner].discard.append(state.stadium)
        state.stadium = card
        state.stadium_owner = state.active_index
        p.stadium_played_this_turn = True
        state.emit(f"played Stadium {card.name}")
        return

    if action.kind == "play_trainer":
        # Pop the Trainer FIRST: its effect may mutate the hand (Rare Candy pulls
        # a Stage 2, Cheren draws), which would invalidate this index otherwise.
        card = p.hand.pop(action.hand_index)
        effect = fx.get_trainer_effect(card.name)
        ctx = fx.EffectContext(state=state, me=p, opp=state.opponent,
                               db=state.db, rng=state.rng)
        did = effect(ctx)
        if did:
            p.discard.append(card)
            if card.is_supporter:
                p.supporter_played_this_turn = True
            state.emit(f"played {card.name}")
            fx.process_knockouts(state)   # a Trainer could cause KOs
        else:
            p.hand.insert(action.hand_index, card)   # couldn't act; put it back
        return

    if action.kind == "use_ability":
        mon = p.active if action.target_index == -1 else p.bench[action.target_index]
        # find the first registered ability on this Pokemon
        for ab in mon.card.abilities:
            effect = fx.get_ability_effect(mon.card.name, ab.name)
            if effect:
                ctx = fx.EffectContext(state=state, me=p, opp=state.opponent,
                                       source=mon, db=state.db, rng=state.rng)
                effect(ctx)
                mon.ability_used_this_turn = True
                state.emit(f"{mon.card.name} used ability {ab.name}")
                # abilities can now KO (Cursed Blast places counters AND self-KOs)
                fx.process_knockouts(state)
                break
        return

    if action.kind == "attack":
        _resolve_attack(state, action.attack_index)
        # attacking always ends the turn
        state.phase = Phase.BETWEEN_TURNS
        return


# --------------------------------------------------------------------------- #
# Win conditions
# --------------------------------------------------------------------------- #
def check_win(state: GameState) -> Optional[int]:
    """Return winning player index, or None. Sets state.winner/phase on a win.

    Three ways to win:
      1. You take all your prizes.
      2. Your opponent has no Pokemon in play.
      3. Your opponent can't draw at the start of their turn (handled in turn loop).
    """
    for i, p in enumerate(state.players):
        opp = state.players[1 - i]
        if len(p.prizes) == 0:
            state.winner = i
            state.phase = Phase.GAME_OVER
            return i
        if not opp.has_pokemon_in_play() and opp.active is None:
            state.winner = i
            state.phase = Phase.GAME_OVER
            return i
    return None


# --------------------------------------------------------------------------- #
# Turn loop
# --------------------------------------------------------------------------- #
def start_turn(state: GameState) -> bool:
    """Begin the current player's turn. Returns False if they deck out (loss)."""
    p = state.current
    p.turns_taken += 1
    p.energy_attached_this_turn = False
    p.supporter_played_this_turn = False
    p.stadium_played_this_turn = False
    # snapshot "KO'd during the opponent's last turn" for Flip the Script, then
    # reset the accumulator for the cycle that starts now.
    p.koed_last_turn = p.koed_during_opp_turn
    p.koed_during_opp_turn = False
    for mon in p.all_in_play():
        mon.ability_used_this_turn = False
        mon.played_this_turn = False
        mon.evolved_this_turn = False
    # the starting player's first turn does NOT draw in some rule sets; modern
    # rules: player going first DOES draw. We follow modern: always draw.
    drawn = p.draw(1)
    if drawn == 0:
        # deck-out: this player loses immediately
        state.winner = state.opponent_index()
        state.phase = Phase.GAME_OVER
        state.emit(f"{p.name} cannot draw — loses by deck-out")
        return False
    state.phase = Phase.MAIN
    return True


def end_turn(state: GameState) -> None:
    state.active_index = state.opponent_index()
    state.turn_number += 1
