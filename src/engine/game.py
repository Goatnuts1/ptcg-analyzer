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


def evolves_onto(in_play_card: Card, evolution_card: Card) -> bool:
    """Does `evolution_card` (a card in hand) evolve onto `in_play_card`?

    The comparison is against the in-play card's PRINTED name, which is
    `fx.print_base_name(...)` — i.e. the disambiguating "(SETCODE)" suffix this project
    adds when a deck needs a different print of an already-pooled card is stripped first.

    WHY: the suffix is a pool-bookkeeping device, not part of the card. Without stripping
    it, a suffixed PRE-evolution silently breaks its own line — "Dunsparce (JTG)" could
    never become Dudunsparce (whose printed `evolvesFrom` is "Dunsparce"), so a deck
    running the JTG print would have a dead Stage 1. It also matches the real rule: ANY
    print of Dunsparce evolves into ANY print of Dudunsparce.
    """
    if not (evolution_card.is_pokemon and evolution_card.evolves_from):
        return False
    return fx.print_base_name(in_play_card.name) == evolution_card.evolves_from


def setup_game(deck_a: list[Card], deck_b: list[Card], seed: Optional[int] = None,
               db: Optional[object] = None, first_player: Optional[int] = None) -> GameState:
    """Shuffle, deal 7, mulligan until both have a Basic, place active + prizes.

    Coin flip decides who goes first, UNLESS `first_player` (0 or 1) is given, in
    which case the flip is skipped and that player index goes first — for
    deliberately testing the first/second-turn asymmetry rather than sampling
    over it. (The starting player skips their first attack — a real and
    measurable asymmetry.) Default (None) is unchanged: a real coin flip.
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
    state.active_index = rng.randint(0, 1) if first_player is None else first_player

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
    Colorless-providing energy as a fallback is NOT allowed for typed symbols) —
    EXCEPT the "Any" wildcard token (Prism Energy on a Basic, Neo Upper Energy on a
    Stage 2), which matches any single typed requirement, consumed once like a real
    energy unit.

    Counted in UNITS, not cards: `provided_types()` emits one entry per Energy the
    attachment provides, so a card that "provides 2 Energy at a time" (Neo Upper
    Energy on a Stage 2) really pays a two-symbol cost on its own. For every
    single-unit energy this is identical to counting cards.

    "Free" is the pool's sentinel for a genuinely 0-cost attack (e.g. Budew's
    Itchy Pollen, Tyrogue's Pow-Pow Punching) — it isn't an energy type, so it
    must never consume/require an attached energy.
    """
    cost = tuple(sym for sym in cost if sym != "Free")
    provided = list(mon.provided_types())
    if len(provided) < len(cost):
        return False
    # satisfy typed requirements first
    for sym in cost:
        if sym == "Colorless":
            continue
        if sym in provided:
            provided.remove(sym)
        elif "Any" in provided:
            provided.remove("Any")
        else:
            return False
    # remaining colorless requirements: any leftover energy counts (including
    # unused "Any" wildcards, which count as 1 unit same as any other energy)
    colorless_needed = sum(1 for s in cost if s == "Colorless")
    return len(provided) >= colorless_needed


def retreat_cost(mon: InPlayPokemon, state: "GameState" = None,
                 owner: "PlayerState" = None) -> int:
    """Effective retreat cost, accounting for Tools (Air Balloon −2) and passive
    abilities (Agile: 0 if no Energy attached; Latias ex's Skyliner: your Basic
    Pokémon retreat for free). `state`/`owner` are optional so callers without board
    context still get the Tool/Agile answer."""
    if (state is not None and owner is not None
            and fx.skyliner_free_retreat(state, owner, mon)):
        return 0
    if not mon.energy and any(ab.name == "Agile" for ab in mon.card.abilities):
        return 0
    base = mon.card.retreat_cost
    # Jamming Tower: "Pokémon Tools attached to each Pokémon (both yours and your
    # opponent's) have no effect" — so Air Balloon's −2 is off while it's the Stadium.
    if (mon.tool is not None and mon.tool.name == "Air Balloon"
            and not fx.tools_disabled(state)):
        base = max(0, base - 2)
    return base


# --------------------------------------------------------------------------- #
# Legal action enumeration
# --------------------------------------------------------------------------- #
def legal_actions(state: GameState) -> list[Action]:
    p = state.current
    actions: list[Action] = [PASS]
    if p.active is None:
        return actions   # must promote first (handled in apply when active KO'd)

    # play a Basic Pokemon to the bench
    # Bench cap is PER-PLAYER and DYNAMIC (Area Zero Underdepths raises it to 8 for a
    # player who has a Tera Pokémon in play), so ask fx.bench_limit — never the
    # PlayerState.MAX_BENCH constant, which is only the default.
    if len(p.bench) < fx.bench_limit(state, p):
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
        # Forest of Vitality (Stadium): "Each player's [G] Pokémon can evolve into [G]
        # Pokémon during the turn they play those Pokémon, except during their first
        # turn." Waives ONLY the played-this-turn clause, only for Grass-into-Grass,
        # and turns_taken >= 2 already encodes the first-turn exception.
        vitality = fx.current_stadium_name(state) == "Forest of Vitality"
        for i, c in enumerate(p.hand):
            if c.is_pokemon and c.evolves_from:
                for t, mon in in_play:
                    if (mon and evolves_onto(mon.card, c)
                            and (not mon.played_this_turn
                                 or (vitality and "Grass" in mon.card.types
                                     and "Grass" in c.types))
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
        if c.is_item and p.cant_play_items:    # Budew's Itchy Pollen lock
            continue
        if c.is_supporter and p.supporter_played_this_turn:
            continue
        if fx.get_trainer_effect(c.name) and fx.can_play_trainer(state, p, c.name):
            actions.append(Action("play_trainer", hand_index=i))

    # use an activated ability (once per turn per Pokemon unless repeatable; if
    # registered, not suppressed by a Stadium, and currently able)
    for t, mon in in_play:
        if not mon or fx.ability_suppressed(state, mon):
            continue
        for ab in mon.card.abilities:
            if not fx.get_ability_effect(mon.card.name, ab.name):
                continue
            if mon.ability_used_this_turn and not fx.is_repeatable_ability(mon.card.name, ab.name):
                continue
            guard = fx.get_ability_can_use(mon.card.name, ab.name)
            if guard is None or guard(state, p, mon):
                actions.append(Action("use_ability", target_index=t))

    # attach a Pokémon Tool to a Pokémon that doesn't already have one
    for i, c in enumerate(p.hand):
        if c.is_trainer and "Pokémon Tool" in c.subtypes:
            for t, mon in [(-1, p.active)] + list(enumerate(p.bench)):
                if mon is not None and mon.tool is None:
                    actions.append(Action("attach_tool", hand_index=i, target_index=t))

    # retreat (if enough energy, a bench Pokemon to promote, and not retreat-locked)
    if (p.bench and not p.cant_retreat
            and p.active.energy_count() >= retreat_cost(p.active, state, p)):
        for t in range(len(p.bench)):
            actions.append(Action("retreat", target_index=t))

    # Surfing Beach (Stadium): once per turn, switch your Active [Water] Pokémon with
    # a Benched [Water] Pokémon (free, no energy cost, doesn't end the turn). Offered
    # as a legal action whenever a valid Water bench target exists — an agent picks.
    if (fx.current_stadium_name(state) == "Surfing Beach"
            and not p.stadium_switch_used_this_turn
            and "Water" in p.active.card.types):
        for t, mon in enumerate(p.bench):
            if "Water" in mon.card.types:
                actions.append(Action("stadium_switch", target_index=t))

    # Prism Tower (Stadium): "Once during each player's turn, that player may discard 2
    # cards from their hand in order to draw a card." A free action for EITHER player
    # (whoever's turn it is) that doesn't end the turn. Offered only when the cost can
    # actually be paid (2 cards in hand) and the payoff exists (a card left to draw) —
    # the engine never offers a Trainer/ability that would do nothing, and this is the
    # same standard.
    if (fx.current_stadium_name(state) == "Prism Tower"
            and not p.stadium_draw_used_this_turn
            and len(p.hand) >= 2 and p.deck):
        actions.append(Action("stadium_draw"))

    # Grand Tree (Stadium, ACE SPEC): "Once during each player's turn, that player may
    # search their deck for a Stage 1 Pokémon that evolves from 1 of their Basic Pokémon
    # and put it onto that Pokémon to evolve it. If that Pokémon was evolved in this way,
    # that player may search their deck for a Stage 2 Pokémon that evolves from that
    # Pokémon and put it onto that Pokémon to evolve it." A free action for EITHER player,
    # enumerated PER Basic target (the Surfing Beach shape) so an agent picks which line
    # to build; the Stage 1 / Stage 2 picked out of the deck is a search policy.
    if (fx.current_stadium_name(state) == "Grand Tree"
            and not p.stadium_evolve_used_this_turn):
        for t, mon in in_play:
            if fx.grand_tree_can_evolve(state, p, mon):
                actions.append(Action("stadium_evolve", target_index=t))

    # Mystery Garden (Stadium): "Once during each player's turn, that player may discard
    # an Energy card from their hand in order to draw cards until they have as many cards
    # in their hand as they have Psychic Pokémon in play." Offered only when it actually
    # draws (see fx.mystery_garden_playable).
    if (fx.current_stadium_name(state) == "Mystery Garden"
            and not p.stadium_garden_used_this_turn
            and fx.mystery_garden_playable(state, p)):
        actions.append(Action("stadium_garden"))

    # Team Rocket's Factory (Stadium): "Once during each player's turn, if they played a
    # Supporter card that has 'Team Rocket' in its name from their hand this turn, they
    # may draw 2 cards." A free action for EITHER player (whoever's turn it is) that
    # doesn't end the turn. Three gates, all real: the Factory must be the Stadium in
    # play, this player must not have used it yet this turn, and the CONDITION — a Team
    # Rocket Supporter played from hand THIS turn — must be satisfied. The `p.deck` check
    # is the usual "never offer an action that does nothing".
    if (fx.team_rocket_factory_active(state)
            and not p.stadium_factory_used_this_turn
            and p.team_rocket_supporter_played_this_turn
            and p.deck):
        actions.append(Action("stadium_factory"))

    # Academy at Night (Stadium): "Once during each player's turn, that player may put a
    # card from their hand on top of their deck." A free action for EITHER player that
    # doesn't end the turn, enumerated PER hand card (the attach_tool shape) so an agent
    # picks WHICH card goes on top — that choice is the whole card (it feeds Slowking's
    # Seek Inspiration, which discards the top card of the deck). Always "does something"
    # as long as a hand exists.
    if (fx.current_stadium_name(state) == "Academy at Night"
            and not p.stadium_academy_used_this_turn
            and p.hand):
        for i in range(len(p.hand)):
            actions.append(Action("stadium_academy", hand_index=i))

    # Spikemuth Gym (Stadium): "Once during each player's turn, that player may search
    # their deck for a Marnie's Pokémon, reveal it, and put it into their hand. Then,
    # that player shuffles their deck." Only offered when the deck actually holds one —
    # a whiffing search is a legal no-op in paper, but enumerating it would waste
    # search-budget on a do-nothing action.
    if (fx.current_stadium_name(state) == "Spikemuth Gym"
            and not p.stadium_spikemuth_used_this_turn):
        # Enumerated per distinct NAME (sorted, so target_index is stable across
        # determinizations — deck ORDER is hidden info and must not leak into the
        # action encoding), letting the agent pick WHICH Marnie's Pokémon to fetch.
        marnies = sorted({c.name for c in p.deck
                          if c.is_pokemon and c.name.startswith("Marnie's")})
        for j in range(len(marnies)):
            actions.append(Action("stadium_spikemuth", target_index=j))

    # attack: starting player cannot attack on the very first turn, and a Pokémon
    # under a "can't attack this turn" lock (Eon Blade, etc.) can't attack either.
    first_turn_no_attack = (state.turn_number == 1)
    if not first_turn_no_attack and not p.active.cannot_attack:
        for ai, atk in enumerate(p.active.card.attacks):
            cost = fx.effective_cost(state, p.active, atk)   # Colorless discounts (Blood Moon)
            if can_pay_cost(p.active, cost) and atk.name not in p.active.locked_attacks:
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
                           source=attacker, db=state.db, rng=state.rng,
                           effect_kind="attack")

    # Confusion: flip a coin; tails -> 30 to itself and the attack does nothing.
    if attacker.confused and not fx.flip(ctx):
        attacker.damage += 30
        state.emit(f"{attacker.card.name} is Confused — tails: 30 to itself, attack fails")
        fx.process_knockouts(state)
        return

    # Base damage handling:
    #   fixed ("")         -> engine applies atk.damage (+weakness)
    #   variable ("+"/"×") WITH a registered effect -> engine applies 0; the
    #       effect computes the full hit (so weakness multiplies the total once)
    #   variable WITHOUT an effect -> fall back to the printed base so the attack
    #       still does something sensible (e.g. Iron Thorns' Destructo-Press)
    owns_damage = (attacker.card.name, atk.name) in fx.ATTACK_EFFECT_OWNS_DAMAGE
    if effect is not None and (atk.damage_suffix in ("+", "×") or owns_damage):
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

    # Festival Lead (Dipplin / Goldeen / Seaking (PRE), passive Ability): "If Festival
    # Grounds is in play, this Pokémon may use an attack it has twice. If the first
    # attack Knocks Out your opponent's Active Pokémon, you may attack again after your
    # opponent chooses a new Active Pokémon." One repeat, no extra cost. The second use
    # targets whatever is Active NOW (process_knockouts already promoted a replacement),
    # exactly the card's clause. "May" is modeled as ALWAYS — the repeat is never worse
    # for the attacker in this engine (no recoil attacks carry the Ability). The
    # attacker must still be the un-KO'd Active, and the second use is skipped if the
    # game already ended on prizes. Confusion is checked once, on the declaration —
    # both uses are the same declared attack.
    if (fx.has_festival_lead(attacker.card)
            and fx.current_stadium_name(state) == "Festival Grounds"
            and not fx.ability_suppressed(state, attacker)
            and state.winner is None
            and state.current.active is attacker
            and not attacker.is_knocked_out):
        defender2 = state.opponent.active
        if base > 0 and defender2 is not None:
            dealt = fx.apply_attack_damage(ctx, defender2, base, owner=state.opponent,
                                           source=attacker)
            state.emit(f"Festival Lead: {atk.name} again for {dealt}")
        if effect:
            effect(ctx)
            state.emit(f"  effect (Festival Lead repeat): {atk.name}")
        fx.process_knockouts(state)


def apply_action(state: GameState, action: Action) -> None:
    p = state.current

    if action.kind == "pass":
        return

    if action.kind == "play_basic":
        card = p.hand.pop(action.hand_index)
        newmon = InPlayPokemon(card=card, played_this_turn=True)
        p.bench.append(newmon)
        state.emit(f"benched {card.name}")
        # on-bench-from-hand trigger (Meowth ex: Last-Ditch Catch), unless suppressed
        trigger = fx.get_on_bench_trigger(card.name)
        if trigger and not fx.ability_suppressed(state, newmon):
            ctx = fx.EffectContext(state=state, me=p, opp=state.opponent,
                                   source=newmon, db=state.db, rng=state.rng,
                                   effect_kind="ability")
            trigger(ctx)
        return

    if action.kind == "attach_energy":
        card = p.hand.pop(action.hand_index)
        mon = p.active if action.target_index == -1 else p.bench[action.target_index]
        mon.energy.append(card)
        p.energy_attached_this_turn = True
        state.emit(f"attached {card.name} to {mon.card.name}")
        # Special Energy on-attach trigger (Enriching Energy: draw 4)
        on_attach = fx.get_special_energy_on_attach(card.name)
        if on_attach:
            ctx = fx.EffectContext(state=state, me=p, opp=state.opponent,
                                   source=mon, db=state.db, rng=state.rng,
                                   effect_kind="energy")
            on_attach(ctx)
        return

    if action.kind == "attach_tool":
        card = p.hand.pop(action.hand_index)
        mon = p.active if action.target_index == -1 else p.bench[action.target_index]
        mon.tool = card
        state.emit(f"attached Tool {card.name} to {mon.card.name}")
        # A Tool can change maximum HP (Cynthia's Power Weight: +70 to a Cynthia's
        # Pokémon), and hp_modifier is DERIVED — refresh so remaining_hp/max_hp are right
        # immediately (agents and evaluation read them before the next KO sweep). Attaching
        # can only raise HP, so no knockout sweep is needed here.
        fx.refresh_hp_modifiers(state)
        return

    if action.kind == "evolve":
        card = p.hand.pop(action.hand_index)
        mon = p.active if action.target_index == -1 else p.bench[action.target_index]
        mon.evolved_from.append(mon.card)
        # evolving removes special conditions (not modeled yet) and keeps damage
        mon.card = card
        mon.evolved_this_turn = True       # no second evolution step this turn
        mon.ability_used_this_turn = False  # the new stage's ability is fresh
        mon.confused = False               # evolving removes Special Conditions
        state.emit(f"evolved into {card.name}")
        # on-evolve-from-hand trigger (Alakazam: Psychic Draw), unless suppressed
        trigger = fx.get_on_evolve_trigger(card.name)
        if trigger and not fx.ability_suppressed(state, mon):
            ctx = fx.EffectContext(state=state, me=p, opp=state.opponent,
                                   source=mon, db=state.db, rng=state.rng,
                                   effect_kind="ability")
            trigger(ctx)
        # NOTE: current "Mega Evolution Pokémon ex" (lowercase ex; e.g. Mega Charizard
        # X/Y ex) have NO turn-ending rule — per the official 2026 rulebook (Appendix 1,
        # p23): "there are no special rules when it comes to playing Mega Evolution
        # Pokémon ex." The turn-end belonged to the rotated XY-era "Mega Evolution
        # Pokémon-EX" (uppercase). Their only drawback is the 3-prize KO (gives_up_prizes).
        # Evolving can change maximum HP (evolving INTO a Stage 2 under Gravity Mountain),
        # and damage carries over — so refresh + sweep. (Rare Candy's evolve goes through
        # play_trainer, which already calls process_knockouts after the effect.)
        fx.process_knockouts(state)
        return

    if action.kind == "retreat":
        # pay retreat cost: discard that many energy from the active
        cost = retreat_cost(p.active, state, p)
        for _ in range(cost):
            if p.active.energy:
                p.discard.append(p.active.energy.pop())
        p.active.confused = False          # Special Conditions clear off the Active Spot
        new_active = p.bench.pop(action.target_index)
        p.bench.append(p.active)
        p.active = new_active
        state.emit(f"retreated to {new_active.card.name}")
        return

    if action.kind == "stadium_switch":
        # Surfing Beach's free once-per-turn Water switch. Mirrors retreat minus the
        # energy cost and minus ending the turn; Special Conditions clear off the
        # Active Spot (same as retreat / Switch).
        newcomer = p.bench.pop(action.target_index)
        p.active.confused = False
        p.bench.append(p.active)
        p.active = newcomer
        p.stadium_switch_used_this_turn = True
        state.emit(f"Surfing Beach: switched in {newcomer.card.name}")
        return

    if action.kind == "stadium_draw":
        # Prism Tower: discard 2 cards from hand, then draw 1. Free action, once per
        # turn per player, doesn't end the turn.
        #
        # WHICH 2 to discard is a policy hook, exactly like place_counters_on_bench's
        # targeting. v0 uses the engine's existing `_search_value` desirability, lowest
        # first, so the least useful cards go — a neutral, deck-agnostic default. It is
        # deliberately NOT tuned toward decks that WANT specific cards in the discard
        # (this list's Hide 'n' Sneak Pokémon fuel Vengeful Anchor / Matcha Spin); a
        # searching agent can own the real choice later.
        for _ in range(2):
            if not p.hand:
                break
            i = min(range(len(p.hand)), key=lambda j: fx._search_value(p.hand[j]))
            p.discard.append(p.hand.pop(i))
        p.draw(1)
        p.stadium_draw_used_this_turn = True
        state.emit("Prism Tower: discarded 2 cards from hand, drew 1")
        return

    if action.kind == "stadium_evolve":
        # Grand Tree: evolve the chosen Basic with a Stage 1 FROM THE DECK, then (if that
        # worked) a Stage 2 from the deck on top of it, then shuffle. Free action, once
        # per turn per player, doesn't end the turn.
        #
        # These cards come from the DECK, not the hand, so the "when you play this Pokémon
        # from your hand to evolve" triggers (ON_EVOLVE_TRIGGERS: Alakazam's Psychic Draw,
        # Noctowl's Jewel Seeker) deliberately do NOT fire — that clause is what Rare Candy
        # satisfies and Grand Tree does not.
        p.stadium_evolve_used_this_turn = True
        mon = p.active if action.target_index == -1 else p.bench[action.target_index]
        stage1 = fx.grand_tree_stage1_for(state, p, mon)
        if stage1 is None:
            return
        p.deck.remove(stage1)
        mon.evolved_from.append(mon.card)
        mon.card = stage1
        mon.evolved_this_turn = True
        mon.ability_used_this_turn = False
        mon.confused = False               # evolving removes Special Conditions
        state.emit(f"Grand Tree: evolved into {stage1.name}")
        stage2 = fx.grand_tree_stage2_for(state, p, stage1)
        if stage2 is not None:
            p.deck.remove(stage2)
            mon.evolved_from.append(mon.card)
            mon.card = stage2
            mon.ability_used_this_turn = False
            state.emit(f"Grand Tree: evolved into {stage2.name}")
        if state.rng:
            state.rng.shuffle(p.deck)      # "Then, that player shuffles their deck."
        # Evolving can change maximum HP (into a Stage 2 under Gravity Mountain) and
        # damage carries over, so sweep — process_knockouts refreshes the modifiers.
        fx.process_knockouts(state)
        return

    if action.kind == "stadium_garden":
        # Mystery Garden: discard an Energy card from hand, then draw until your hand
        # holds as many cards as you have Psychic Pokémon in play. Free action, once per
        # turn per player, doesn't end the turn.
        #
        # WHICH Energy is discarded is a policy hook (the Prism Tower precedent): the
        # least desirable by the engine's existing `_search_value`, so a Special Energy
        # is kept over a Basic one where they differ.
        energy_idx = [i for i, c in enumerate(p.hand) if c.is_energy]
        if not energy_idx:
            return
        i = min(energy_idx, key=lambda j: fx._search_value(p.hand[j]))
        p.discard.append(p.hand.pop(i))
        target = fx.mystery_garden_target(state, p)
        drew = p.draw(max(0, target - len(p.hand)))
        p.stadium_garden_used_this_turn = True
        state.emit(f"Mystery Garden: discarded an Energy, drew {drew} "
                   f"(hand target {target})")
        return

    if action.kind == "stadium_factory":
        # Team Rocket's Factory: draw 2. Free action, once per turn per player, doesn't
        # end the turn. No cost and no choices — the whole card is its condition, which
        # legal_actions has already checked.
        drew = p.draw(2)
        p.stadium_factory_used_this_turn = True
        state.emit(f"Team Rocket's Factory: drew {drew}")
        return

    if action.kind == "stadium_academy":
        # Academy at Night: put a card from your hand on top of your deck. Free action,
        # once per turn per player, doesn't end the turn. The hand card is chosen by the
        # agent via hand_index (see legal_actions).
        card = p.hand.pop(action.hand_index)
        p.deck.insert(0, card)
        p.stadium_academy_used_this_turn = True
        state.emit(f"Academy at Night: put {card.name} on top of the deck")
        return

    if action.kind == "stadium_spikemuth":
        # Spikemuth Gym: search the deck for the CHOSEN Marnie's Pokémon (target_index
        # into the sorted distinct-name list — the same encoding legal_actions used),
        # put it into hand, shuffle. Free action, once per turn, doesn't end the turn.
        marnies = sorted({c.name for c in p.deck
                          if c.is_pokemon and c.name.startswith("Marnie's")})
        p.stadium_spikemuth_used_this_turn = True
        if marnies:
            name = marnies[min(action.target_index, len(marnies) - 1)]
            idx = next(i for i, c in enumerate(p.deck) if c.name == name)
            card = p.deck.pop(idx)
            p.hand.append(card)
            state.rng.shuffle(p.deck)
            state.emit(f"Spikemuth Gym: searched {card.name}")
        return

    if action.kind == "play_stadium":
        card = p.hand.pop(action.hand_index)
        # discard the outgoing Stadium to whoever played it, then install the new one
        outgoing_owner = state.stadium_owner
        if state.stadium is not None and state.stadium_owner is not None:
            state.players[state.stadium_owner].discard.append(state.stadium)
        state.stadium = card
        state.stadium_owner = state.active_index
        p.stadium_played_this_turn = True
        state.emit(f"played Stadium {card.name}")
        # A Stadium can change the BENCH CAP (Area Zero Underdepths: 8 for a player with
        # a Tera Pokémon in play). Replacing Area Zero is exactly its "when this card
        # leaves play, both players discard Pokémon from their Bench until they have 5,
        # and the player who played this card discards first" clause — hence
        # `outgoing_owner`, captured BEFORE state.stadium_owner was overwritten.
        # This runs BEFORE the knockout sweep because process_knockouts ends with its own
        # enforce_bench_limits(state) in DEFAULT order; letting that one go first would
        # silently discard in the wrong order.
        fx.enforce_bench_limits(state, first_index=outgoing_owner)
        # A Stadium can also change maximum HP (Gravity Mountain: −30 HP per Stage 2).
        # Sweep so a Pokémon whose HP just dropped to at-or-below its damage is Knocked
        # Out immediately — process_knockouts refreshes the modifiers itself.
        fx.process_knockouts(state)
        return

    if action.kind == "play_trainer":
        # Pop the Trainer FIRST: its effect may mutate the hand (Rare Candy pulls
        # a Stage 2, Cheren draws), which would invalidate this index otherwise.
        card = p.hand.pop(action.hand_index)
        effect = fx.get_trainer_effect(card.name)
        ctx = fx.EffectContext(state=state, me=p, opp=state.opponent,
                               db=state.db, rng=state.rng, effect_kind="trainer")
        did = effect(ctx)
        if did:
            p.discard.append(card)
            if card.is_supporter:
                p.supporter_played_this_turn = True
                # Team Rocket's Factory's condition: "if they played a Supporter card
                # that has 'Team Rocket' in its name from their hand this turn". Recorded
                # here — the one point where a Supporter has actually RESOLVED (a
                # Supporter whose effect did nothing is put back in hand below and was
                # never played). Independent of whether the Factory is in play right now,
                # because the Stadium can arrive later in the same turn.
                if fx.p_team_rocket_supporter(card):
                    p.team_rocket_supporter_played_this_turn = True
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
                                       source=mon, db=state.db, rng=state.rng,
                                       effect_kind="ability")
                effect(ctx)
                if not fx.is_repeatable_ability(mon.card.name, ab.name):
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
    p.stadium_switch_used_this_turn = False   # Surfing Beach: once per turn
    p.stadium_draw_used_this_turn = False     # Prism Tower: once per turn
    p.stadium_evolve_used_this_turn = False   # Grand Tree: once per turn
    p.stadium_garden_used_this_turn = False   # Mystery Garden: once per turn
    p.stadium_factory_used_this_turn = False  # Team Rocket's Factory: once per turn
    p.stadium_academy_used_this_turn = False  # Academy at Night: once per turn
    p.stadium_spikemuth_used_this_turn = False  # Spikemuth Gym: once per turn
    # ...and its CONDITION resets too — "played ... this turn" means THIS turn only.
    p.team_rocket_supporter_played_this_turn = False
    # snapshot "KO'd during the opponent's last turn" for Flip the Script, then
    # reset the accumulator for the cycle that starts now.
    p.koed_last_turn = p.koed_during_opp_turn
    p.koed_during_opp_turn = False
    # activate turn-scoped debuffs the opponent applied for this turn, then clear
    # the pending slots (so each lasts exactly one turn).
    p.cant_retreat = p.pending_cant_retreat
    p.cant_play_items = p.pending_cant_play_items
    p.pending_cant_retreat = False
    p.pending_cant_play_items = False
    # Kieran's / Premium Power Pro's "during this turn" damage bonuses expire with the
    # turn that set them.
    p.bonus_damage_vs_ex_v = 0
    p.bonus_damage_fighting_vs_active = 0
    p.bonus_damage_nonrulebox = 0     # Gladion's Final Battle expires with its turn
    for mon in p.all_in_play():
        mon.ability_used_this_turn = False
        mon.played_this_turn = False
        mon.evolved_this_turn = False
        mon.shielded = False           # Dig's protection lasted through the opponent's turn
        mon.retaliate = False          # Shellnado Spin's retaliation lasted through the opponent's turn
        mon.retaliate_counters = 12    # reset to the default amount alongside the flag
        mon.damage_reduction = 0       # Protect Charge's −30 lasted through the opponent's turn
        # promote a pending "can't attack next turn" lock to active for THIS turn,
        # then clear pending; a turn later this clears the active flag too.
        mon.cannot_attack = mon.pending_cannot_attack
        mon.pending_cannot_attack = False
        mon.locked_attacks = list(mon.pending_locked_attacks)   # per-attack cooldowns
        mon.pending_locked_attacks = []
        # same promote-then-clear hop for "during your next turn this attack does more
        # damage" self-buffs (Meteor Mash), so the buff is live on THIS turn only.
        mon.boosted_attacks = dict(mon.pending_boosted_attacks)
        mon.pending_boosted_attacks = {}
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
    # end-of-turn Pokémon Tool triggers (Powerglass) for the player whose turn ends
    fx.end_of_turn_tools(state, state.current)
    # Pokémon Checkup (the between-turns window). The engine has no separate phase; the
    # checkup after player A's turn is processed here, before the hand-off. Currently
    # hosts one resident: Froslass's Freezing Shroud (see fx.pokemon_checkup).
    fx.pokemon_checkup(state)
    state.active_index = state.opponent_index()
    state.turn_number += 1
