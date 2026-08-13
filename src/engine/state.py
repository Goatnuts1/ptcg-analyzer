#!/usr/bin/env python3
"""
state.py — the mutable game state the engine reads and writes.

ELI15: a snapshot of the board. Each player has a deck, hand, an Active Pokemon,
a bench, prizes, and a discard pile. An InPlayPokemon wraps a card with the
stuff that changes during play: damage on it and energy attached to it.

This file holds DATA, not rules. The rules live in game.py.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .cards import Card


class Phase(Enum):
    SETUP = "setup"
    DRAW = "draw"
    MAIN = "main"
    ATTACK = "attack"
    BETWEEN_TURNS = "between_turns"
    GAME_OVER = "game_over"


@dataclass
class InPlayPokemon:
    """A Pokemon physically on the board, with its mutable battle state."""
    card: Card
    damage: int = 0
    energy: list[Card] = field(default_factory=list)   # attached energy cards
    # evolution stack so we know what it evolved from (for devolve effects later)
    evolved_from: list[Card] = field(default_factory=list)
    ability_used_this_turn: bool = False
    played_this_turn: bool = False     # can't evolve the turn it was played
    evolved_this_turn: bool = False    # one evolution step per Pokemon per turn
    confused: bool = False             # Special Condition (cleared off the Active Spot)
    tool: Optional[Card] = None        # attached Pokémon Tool (max 1)
    shielded: bool = False             # immune to attack damage & effects (Dunsparce Dig)
    # "During the opponent's next turn, if this Pokémon is damaged by an attack
    # (even if Knocked Out), place 12 damage counters on the attacker" (Mega Slowbro
    # ex's Shellnado Spin). Set directly (like `shielded`) on the attacker's own
    # turn, checked in apply_attack_damage, cleared the same way/same turn as
    # `shielded` — lasts exactly through the opponent's one intervening turn.
    retaliate: bool = False
    # How many counters `retaliate` places on the attacker — defaults to Shellnado
    # Spin's 12 (120 damage); Iron Boulder ex's Repulsor Axe uses 8 (80 damage). Same
    # set-and-clear lifecycle as `retaliate` itself, read alongside it.
    retaliate_counters: int = 12
    # "During your next turn, this Pokémon can't attack" (Latias ex Eon Blade, etc.).
    # pending_* is set by the attack; start_turn promotes it to the active flag on the
    # owner's NEXT turn and clears it the turn after — same one-turn pattern as cant_retreat.
    cannot_attack: bool = False
    pending_cannot_attack: bool = False
    # "During your next turn, this Pokémon can't use [Attack]" (Mega Brave, Brave
    # Slash, ...). Per-attack-name locks; same one-turn promote/clear as above.
    locked_attacks: list[str] = field(default_factory=list)
    pending_locked_attacks: list[str] = field(default_factory=list)
    # "During your NEXT turn, this Pokémon's [Attack] does N more damage" (Metagross's
    # Meteor Mash). attack name -> extra damage. Because the buff must be LIVE on the
    # owner's next turn (not on the opponent's intervening one), this uses the same
    # pending/promote lifecycle as locked_attacks — NOT the set-and-clear pattern of
    # `shielded`/`retaliate`, which are live only during the opponent's turn.
    boosted_attacks: dict[str, int] = field(default_factory=dict)
    pending_boosted_attacks: dict[str, int] = field(default_factory=dict)
    # "During your opponent's next turn, this Pokémon takes N less damage from attacks
    # (after applying Weakness and Resistance)" (Genesect ex's Protect Charge). Set
    # directly on the attacker's own turn and cleared in start_turn on the owner's next
    # turn — the same one-intervening-turn lifecycle as `shielded`/`retaliate`. Read in
    # apply_attack_damage AFTER Weakness/Resistance.
    damage_reduction: int = 0
    # Change to this Pokémon's maximum HP from the live Stadium (Gravity Mountain: −30 HP
    # for each Stage 2 in play) PLUS its attached Tool (Cynthia's Power Weight: +70 HP for
    # a Cynthia's Pokémon). Recomputed from scratch by effects.refresh_hp_modifiers(), so
    # it is always derived state, never accumulated.
    hp_modifier: int = 0
    # "If the Pokémon this card is attached to is Knocked Out BY DAMAGE FROM AN ATTACK
    # from your opponent's Pokémon..." (Legacy Energy). Set by apply_attack_damage — the
    # one path that IS "damage from an attack" — when the hit it just applied came from an
    # opposing Pokémon and left this Pokémon at or past its maximum HP. Deliberately NOT
    # set by place_counters (damage counters placed by an effect are not "damage from an
    # attack") nor by a self-KO, so effects._ko_cleanup can tell the causes apart.
    koed_by_opponent_attack_damage: bool = False

    def clone(self) -> "InPlayPokemon":
        """Copy the mutable wrapper but SHARE Card refs (Cards are frozen/immutable).
        This is what makes MCTS rollouts cheap — we don't deep-copy the card DB."""
        return InPlayPokemon(
            card=self.card,
            damage=self.damage,
            energy=list(self.energy),
            evolved_from=list(self.evolved_from),
            ability_used_this_turn=self.ability_used_this_turn,
            played_this_turn=self.played_this_turn,
            evolved_this_turn=self.evolved_this_turn,
            confused=self.confused,
            tool=self.tool,
            shielded=self.shielded,
            retaliate=self.retaliate,
            retaliate_counters=self.retaliate_counters,
            cannot_attack=self.cannot_attack,
            pending_cannot_attack=self.pending_cannot_attack,
            locked_attacks=list(self.locked_attacks),
            pending_locked_attacks=list(self.pending_locked_attacks),
            boosted_attacks=dict(self.boosted_attacks),
            pending_boosted_attacks=dict(self.pending_boosted_attacks),
            damage_reduction=self.damage_reduction,
            hp_modifier=self.hp_modifier,
            koed_by_opponent_attack_damage=self.koed_by_opponent_attack_damage,
        )

    @property
    def max_hp(self) -> Optional[int]:
        """Printed HP plus any live HP modifier (Gravity Mountain −30 on a Stage 2,
        Cynthia's Power Weight +70 on a Cynthia's Pokémon). Floored at 10 — HP can never
        be reduced to 0 or below by an HP-changing effect, the Pokémon would just be
        Knocked Out at 10."""
        if self.card.hp is None:
            return None
        return max(10, self.card.hp + self.hp_modifier)

    @property
    def remaining_hp(self) -> int:
        return (self.max_hp or 0) - self.damage

    @property
    def is_knocked_out(self) -> bool:
        return self.max_hp is not None and self.damage >= self.max_hp

    def energy_count(self) -> int:
        # Each attached energy provides at least one unit. Special energy that
        # provide multiple/typed units are a later refinement.
        return len(self.energy)

    def provided_types(self) -> list[str]:
        """The Energy UNITS this Pokémon's attachments provide, as cost symbols. One
        entry per unit, so a card that provides 2 Energy contributes 2 entries and
        `can_pay_cost` (which consumes this list) sees the real amount.

        Wildcard energy is modeled as an "Any" token that can_pay_cost matches against
        any single typed requirement, consumed once like a real unit:
          - Prism Energy: "provides Colorless Energy... If this card is attached to a
            Basic Pokémon, this card provides every type of Energy but provides only
            1 Energy at a time." -> one "Any" on a Basic, else one Colorless.
          - Neo Upper Energy (ACE SPEC): "...it provides Colorless Energy. If this card
            is attached to a Stage 2 Pokémon, this card provides every type of Energy
            but provides only 2 Energy at a time." -> TWO "Any" on a Stage 2 (so it
            alone pays Cynthia's Garchomp ex's [F][F] Draconic Buster), else one
            Colorless. Basics and Stage 1s get nothing extra — only Stage 2 is named.

        Scope note: this models the Energy-PROVISION clause, which is what attack costs
        are paid from. It deliberately does NOT change `energy_count()`, so texts that
        count "Energy attached" (retreat cost, Jumbo Ice Cream's 3-Energy gate) still
        count CARDS — an uncovered edge, not a covered one."""
        types = []
        for e in self.energy:
            if e.name == "Prism Energy" and self.card.is_basic:
                types.append("Any")
            elif e.name == "Neo Upper Energy" and "Stage 2" in self.card.subtypes:
                types.extend(["Any", "Any"])
            elif e.name == "Legacy Energy":
                # "As long as this card is attached to a Pokémon, it provides every type
                # of Energy but provides only 1 Energy at a time." UNCONDITIONAL — unlike
                # Prism / Neo Upper Energy there is no stage clause, so every holder gets
                # exactly one "Any" wildcard unit. (Its separate 1-fewer-Prize clause is a
                # KO rider, handled in effects._ko_cleanup, not an Energy-provision one.)
                types.append("Any")
            else:
                types.extend(e.types or ["Colorless"])
        return types


@dataclass
class PlayerState:
    name: str
    deck: list[Card] = field(default_factory=list)
    hand: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    prizes: list[Card] = field(default_factory=list)
    active: Optional[InPlayPokemon] = None
    bench: list[InPlayPokemon] = field(default_factory=list)

    # per-turn flags the rules reset
    energy_attached_this_turn: bool = False
    supporter_played_this_turn: bool = False
    stadium_played_this_turn: bool = False   # only 1 Stadium per turn
    # Surfing Beach: "Once during each player's turn, that player may switch their
    # Active [Water] Pokémon with 1 of their Benched [Water] Pokémon." Reset each turn.
    stadium_switch_used_this_turn: bool = False
    # Prism Tower: "Once during each player's turn, that player may discard 2 cards from
    # their hand in order to draw a card." A SEPARATE once-per-turn budget from
    # `stadium_switch_used_this_turn` (Surfing Beach) — the two Stadiums are never in play
    # at the same time, but keeping one flag per Stadium ability means neither can ever
    # silently consume the other's use. Reset each turn.
    stadium_draw_used_this_turn: bool = False
    # Grand Tree (Stadium, ACE SPEC): "Once during each player's turn, that player may
    # search their deck for a Stage 1 Pokémon that evolves from 1 of their Basic
    # Pokémon..." Its OWN once-per-turn budget, for the same reason Prism Tower's is
    # separate from Surfing Beach's: one flag per Stadium ability means none can ever
    # silently consume another's use. Reset each turn.
    stadium_evolve_used_this_turn: bool = False
    # Mystery Garden (Stadium): "Once during each player's turn, that player may discard
    # an Energy card from their hand in order to draw cards until they have as many cards
    # in their hand as they have Psychic Pokémon in play." Own budget, reset each turn.
    stadium_garden_used_this_turn: bool = False
    # Team Rocket's Factory (Stadium): "Once during each player's turn, if they played a
    # Supporter card that has 'Team Rocket' in its name from their hand this turn, they
    # may draw 2 cards." Own once-per-turn budget, same one-flag-per-Stadium-ability rule
    # as the four above. Reset each turn.
    stadium_factory_used_this_turn: bool = False
    # Academy at Night (Stadium): "Once during each player's turn, that player may put a
    # card from their hand on top of their deck." Own once-per-turn budget, same
    # one-flag-per-Stadium-ability rule as the five above. Reset each turn.
    stadium_academy_used_this_turn: bool = False
    # The Factory's CONDITION, tracked separately from its budget: did this player play a
    # Supporter whose name contains "Team Rocket" from hand THIS turn? Set by
    # game.apply_action when such a Supporter actually resolves (a Supporter that did
    # nothing is put back in hand and was never played), reset by start_turn. Kept on
    # PlayerState rather than derived from the discard pile because the discard says
    # nothing about WHICH turn the card was played.
    team_rocket_supporter_played_this_turn: bool = False
    # Legacy Energy: "...that player takes 1 fewer Prize card. This effect of YOUR Legacy
    # Energy can't be applied more than once per game." Per-PLAYER (the owner of the
    # Legacy Energy, i.e. the player whose Pokémon was Knocked Out) and per-GAME, so it
    # is never reset by start_turn. Consumed in effects._ko_cleanup.
    legacy_energy_prize_reduction_used: bool = False
    turns_taken: int = 0          # for the "no evolving on your first turn" rule
    # "were any of your Pokémon KO'd during your opponent's last turn?" — drives
    # Fezandipiti's Flip the Script. `koed_during_opp_turn` accumulates while it is
    # NOT your turn; start_turn snapshots it into `koed_last_turn` then resets it.
    koed_during_opp_turn: bool = False
    koed_last_turn: bool = False
    # turn-scoped debuffs applied BY the opponent, active only during this player's
    # next turn. `pending_*` is set on your opponent now; start_turn activates it
    # into the matching active flag for exactly that one turn, then it clears.
    cant_retreat: bool = False
    cant_play_items: bool = False
    pending_cant_retreat: bool = False
    pending_cant_play_items: bool = False
    # Kieran (Supporter), 2nd mode: "During THIS turn, attacks used by your Pokémon do
    # 30 more damage to your opponent's Active Pokémon ex and Active Pokémon V (before
    # applying Weakness and Resistance)." Same-turn only, so it is set by the Supporter
    # and cleared in start_turn (no pending_* hop — nothing carries to another turn).
    bonus_damage_vs_ex_v: int = 0
    # Premium Power Pro (Item): "During this turn, attacks used by your [F] Pokémon do 30
    # more damage to your opponent's Active Pokémon (before applying Weakness and
    # Resistance)." Same-turn only — set by the Item and cleared in start_turn, exactly
    # like bonus_damage_vs_ex_v. ACCUMULATES (+= 30 per copy played): two copies are two
    # separate effects, so they stack.
    bonus_damage_fighting_vs_active: int = 0

    MAX_BENCH = 5

    def all_in_play(self) -> list[InPlayPokemon]:
        return ([self.active] if self.active else []) + self.bench

    def has_pokemon_in_play(self) -> bool:
        return self.active is not None or len(self.bench) > 0

    def draw(self, n: int = 1) -> int:
        """Draw up to n cards. Returns how many were actually drawn."""
        drawn = 0
        for _ in range(n):
            if not self.deck:
                break
            self.hand.append(self.deck.pop(0))
            drawn += 1
        return drawn

    def clone(self) -> "PlayerState":
        p = PlayerState(
            name=self.name,
            deck=list(self.deck),          # Card refs shared; list copied
            hand=list(self.hand),
            discard=list(self.discard),
            prizes=list(self.prizes),
            active=self.active.clone() if self.active else None,
            bench=[m.clone() for m in self.bench],
            energy_attached_this_turn=self.energy_attached_this_turn,
            supporter_played_this_turn=self.supporter_played_this_turn,
            stadium_played_this_turn=self.stadium_played_this_turn,
            stadium_switch_used_this_turn=self.stadium_switch_used_this_turn,
            stadium_draw_used_this_turn=self.stadium_draw_used_this_turn,
            stadium_evolve_used_this_turn=self.stadium_evolve_used_this_turn,
            stadium_garden_used_this_turn=self.stadium_garden_used_this_turn,
            stadium_factory_used_this_turn=self.stadium_factory_used_this_turn,
            stadium_academy_used_this_turn=self.stadium_academy_used_this_turn,
            team_rocket_supporter_played_this_turn=self.team_rocket_supporter_played_this_turn,
            legacy_energy_prize_reduction_used=self.legacy_energy_prize_reduction_used,
            turns_taken=self.turns_taken,
            koed_during_opp_turn=self.koed_during_opp_turn,
            koed_last_turn=self.koed_last_turn,
            cant_retreat=self.cant_retreat,
            cant_play_items=self.cant_play_items,
            pending_cant_retreat=self.pending_cant_retreat,
            pending_cant_play_items=self.pending_cant_play_items,
            bonus_damage_vs_ex_v=self.bonus_damage_vs_ex_v,
            bonus_damage_fighting_vs_active=self.bonus_damage_fighting_vs_active,
        )
        return p


@dataclass
class GameState:
    players: tuple[PlayerState, PlayerState]
    rng: random.Random
    active_index: int = 0          # whose turn it is (0 or 1)
    turn_number: int = 0
    phase: Phase = Phase.SETUP
    winner: Optional[int] = None   # 0, 1, or None (None + GAME_OVER = tie)
    log: list[str] = field(default_factory=list)
    db: Optional[object] = None    # CardDB, for searches / evolution-chain lookups
    # The single shared Stadium zone. `stadium_owner` is the player index who
    # played it (for discard routing when it's replaced). Most Stadiums are
    # symmetric, but ownership matters for "discard the outgoing Stadium".
    stadium: Optional[Card] = None
    stadium_owner: Optional[int] = None

    @property
    def current(self) -> PlayerState:
        return self.players[self.active_index]

    @property
    def opponent(self) -> PlayerState:
        return self.players[1 - self.active_index]

    def opponent_index(self) -> int:
        return 1 - self.active_index

    def clone(self, fresh_rng: Optional[random.Random] = None,
              keep_log: bool = False) -> "GameState":
        """Deep-copy the mutable game state for MCTS. Card refs and the db are
        SHARED (immutable). The log is dropped by default (rollouts don't need it).
        Pass a fresh_rng so each simulated world rolls differently."""
        s = GameState(
            players=(self.players[0].clone(), self.players[1].clone()),
            rng=fresh_rng if fresh_rng is not None else random.Random(),
            active_index=self.active_index,
            turn_number=self.turn_number,
            phase=self.phase,
            winner=self.winner,
            log=list(self.log) if keep_log else [],
            db=self.db,
        )
        s.stadium = self.stadium
        s.stadium_owner = self.stadium_owner
        return s

    def emit(self, msg: str) -> None:
        self.log.append(f"T{self.turn_number} P{self.active_index}: {msg}")
