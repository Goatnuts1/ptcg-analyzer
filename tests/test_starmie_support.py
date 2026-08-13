#!/usr/bin/env python3
"""
test_starmie_support.py — Surfing Beach (Stadium), Ciphermaniac's Codebreaking
(Supporter), and the Mega Starmie ex Nebula Beam wall-bypass critical case.
Card text quoted inline from data/standard_pool.json (verified against
limitlesstcg.com this session per the implementer's notes).

Covers:
  - Surfing Beach (me1-129, Stadium): "Once during each player's turn, that
    player may switch their Active [Water] Pokémon with 1 of their Benched
    [Water] Pokémon."
  - Ciphermaniac's Codebreaking (sv5-145, Supporter): "Search your deck for 2
    cards, shuffle your deck, then put those cards on top of it in any order."
  - Mega Starmie ex (me3-21):
      "Jetting Blow" [W] 120 — "This attack also does 50 damage to 1 of your
      opponent's Benched Pokémon. (Don't apply Weakness and Resistance for
      Benched Pokémon.)"
      "Nebula Beam" [CCC] 210 — "This attack's damage isn't affected by
      Weakness or Resistance, or by any effects on your opponent's Active
      Pokémon." THE CRITICAL CASE: this bypasses Crustle's "Mysterious Rock
      Inn" wall (source is an opponent's Pokémon ex — Mega Starmie ex carries
      the 'ex' subtype) via the same ignore_active_effects=True,
      ignore_weakness=True chokepoint flags Superb Scissors/Demolish already
      use, while Jetting Blow (no such flags) is fully blocked by the same
      wall — proving the bypass is attack-specific, not a blanket
      wall-disable.

      NOTE ON MILOTIC EX / CORNERSTONE MASK OGERPON EX: their wall Abilities
      gate on a PROPERTY OF THE ATTACKING SOURCE — Sparkling Scales requires
      the source be Tera-typed; Cornerstone Stance requires the source HAVE
      an Ability. Mega Starmie ex's own card (subtypes Stage 1/MEGA/ex,
      abilities=[]) is neither Tera nor ability-bearing, so — as an
      established fact about this engine's real card data, not a bug —
      *neither* of those two walls is ever actually live against Mega Starmie
      ex's own attacks; only Crustle's "opponent's Pokémon ex" gate matches
      it. Both angles are covered below: (1) the real Mega Starmie ex vs
      Milotic ex / Cornerstone Ogerpon ex, showing both attacks connect in
      full because the gate is simply never triggered by this attacker, and
      (2) a direct apply_attack_damage mechanism check — using synthetic
      sources that DO satisfy each gate — proving the exact ignore-flag
      mechanism Nebula Beam uses would bypass those two wall types as well,
      for the same reason it bypasses Crustle's.

Run from project root:  python3 tests/test_starmie_support.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.state import GameState, PlayerState, InPlayPokemon
from src.engine import game, effects as fx


def fresh_state(db):
    a = PlayerState(name="A")
    b = PlayerState(name="B")
    st = GameState(players=(a, b), rng=random.Random(0))
    st.db = db
    st.turn_number = 5            # past turn-1 no-attack restriction
    st.active_index = 0
    return st, a, b


def ctx_for(st, me, opp, source=None):
    return fx.EffectContext(state=st, me=me, opp=opp, source=source,
                            db=st.db, rng=st.rng)


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    db = CardDB.from_pool("data/standard_pool.json")

    # =================================================================== #
    # SURFING BEACH (me1-129, Stadium)
    # Pool text: "Once during each player's turn, that player may switch their
    # Active Water Pokémon with 1 of their Benched Water Pokémon."
    # =================================================================== #

    # --- S1. POSITIVE: with Surfing Beach in play, the Active Water and a
    # Benched Water each qualifying, legal_actions offers "stadium_switch". ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Surfing Beach")
    st.stadium_owner = 0
    a.active = InPlayPokemon(card=db.get("Frogadier"))       # Water
    a.bench = [InPlayPokemon(card=db.get("Froakie"))]         # Water
    acts = game.legal_actions(st)
    check(any(act.kind == "stadium_switch" and act.target_index == 0 for act in acts),
          "Surfing Beach should offer stadium_switch when Active and a Bench "
          "target are both Water and the switch hasn't been used this turn")

    # --- S2. Applying stadium_switch swaps Active<->Bench, uses NO energy
    # (unlike retreat), does NOT end the turn, marks the once-per-turn flag,
    # and clears Confusion off the outgoing Active (same as retreat/Switch). ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Surfing Beach")
    st.stadium_owner = 0
    frogadier = InPlayPokemon(card=db.get("Frogadier"), confused=True)
    frogadier.energy = [db.get("Basic Water Energy"), db.get("Basic Water Energy")]
    froakie = InPlayPokemon(card=db.get("Froakie"))
    a.active = frogadier
    a.bench = [froakie]
    check(not a.stadium_switch_used_this_turn, "setup: switch not yet used")
    game.apply_action(st, game.Action(kind="stadium_switch", target_index=0))
    check(a.active is froakie, "Froakie should now be Active")
    check(any(m is frogadier for m in a.bench), "Frogadier should now be Benched")
    check(len(frogadier.energy) == 2,
          f"Surfing Beach's switch must cost NO energy (unlike retreat), "
          f"expected 2 still attached, got {len(frogadier.energy)}")
    check(frogadier.confused is False,
          "Confusion must clear off the outgoing Active on a stadium_switch, "
          "same as retreat")
    check(a.stadium_switch_used_this_turn,
          "stadium_switch_used_this_turn must be set True after use")
    check(st.active_index == 0,
          "stadium_switch must NOT end the turn (active_index unchanged)")

    # --- S3. NEGATIVE: once used this turn, it is no longer offered. ---
    acts = game.legal_actions(st)
    check(not any(act.kind == "stadium_switch" for act in acts),
          "Surfing Beach must not offer a second switch in the same turn")

    # --- S4. The once-per-turn flag resets at the start of the player's NEXT
    # turn (game.start_turn). ---
    a.deck = [db.get("Basic Fire Energy")] * 5   # so start_turn's draw succeeds
    game.start_turn(st)
    check(not a.stadium_switch_used_this_turn,
          "stadium_switch_used_this_turn must reset at start_turn")

    # --- S5. NEGATIVE: Active is not Water -> switch not offered even with a
    # valid Water Benched Pokémon. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Surfing Beach")
    st.stadium_owner = 0
    a.active = InPlayPokemon(card=db.get("Crustle"))          # Grass, not Water
    a.bench = [InPlayPokemon(card=db.get("Froakie"))]         # Water
    acts = game.legal_actions(st)
    check(not any(act.kind == "stadium_switch" for act in acts),
          "no switch should be offered when the Active is not Water")

    # --- S6. NEGATIVE: Active is Water but no Water Benched Pokémon exists ->
    # not offered. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Surfing Beach")
    st.stadium_owner = 0
    a.active = InPlayPokemon(card=db.get("Frogadier"))        # Water
    a.bench = [InPlayPokemon(card=db.get("Crustle"))]          # Grass, not Water
    acts = game.legal_actions(st)
    check(not any(act.kind == "stadium_switch" for act in acts),
          "no switch should be offered when no Benched Pokémon is Water")

    # --- S7. NEGATIVE: Surfing Beach not in play -> not offered even though
    # both sides of the gate (Water Active + Water Bench) are satisfied. ---
    st, a, b = fresh_state(db)
    st.stadium = None
    a.active = InPlayPokemon(card=db.get("Frogadier"))
    a.bench = [InPlayPokemon(card=db.get("Froakie"))]
    acts = game.legal_actions(st)
    check(not any(act.kind == "stadium_switch" for act in acts),
          "no switch should be offered without Surfing Beach in play")

    # --- S8. Only the qualifying (Water) Bench slots are offered — a mixed
    # bench with one Water and one non-Water target yields exactly one
    # stadium_switch action, at the Water slot's index. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Surfing Beach")
    st.stadium_owner = 0
    a.active = InPlayPokemon(card=db.get("Frogadier"))
    a.bench = [InPlayPokemon(card=db.get("Crustle")),          # index 0: Grass
              InPlayPokemon(card=db.get("Froakie"))]            # index 1: Water
    acts = [act for act in game.legal_actions(st) if act.kind == "stadium_switch"]
    check(len(acts) == 1 and acts[0].target_index == 1,
          f"exactly one stadium_switch action should be offered, at the Water "
          f"bench index (1); got {[(act.target_index) for act in acts]}")

    # --- S9. Per-player independence: player A having used their switch this
    # turn does not affect player B's own (separate) once-per-turn flag. ---
    st, a, b = fresh_state(db)
    st.stadium = db.get("Surfing Beach")
    st.stadium_owner = 0
    a.stadium_switch_used_this_turn = True        # A already used theirs
    b.active = InPlayPokemon(card=db.get("Frogadier"))
    b.bench = [InPlayPokemon(card=db.get("Froakie"))]
    st.active_index = 1                            # now it's B's turn
    acts = game.legal_actions(st)
    check(any(act.kind == "stadium_switch" for act in acts),
          "B's own stadium_switch_used_this_turn flag is independent of A's "
          "and should still allow B's switch")

    # =================================================================== #
    # CIPHERMANIAC'S CODEBREAKING (sv5-145, Supporter)
    # Pool text: "Search your deck for 2 cards, shuffle your deck, then put
    # those cards on top of it in any order." — TOP OF DECK, not hand.
    # =================================================================== #

    def _search_deck(a):
        """A 5-card deck with distinct _search_value tiers so the two highest
        picks are deterministic: Froakie (Basic w/ evolves_to -> 5), Feraligatr
        (Stage 2 -> 4), Picnicker (Supporter -> 3), Master Ball (Item -> 2),
        Basic Fire Energy (-> 1)."""
        a.deck = [db.get("Basic Fire Energy"), db.get("Master Ball"),
                 db.get("Picnicker"), db.get("Feraligatr"), db.get("Froakie")]

    # --- C1. can_play: True with a non-empty deck. ---
    st, a, b = fresh_state(db)
    _search_deck(a)
    check(fx._TRAINER_CAN_PLAY["Ciphermaniac's Codebreaking"](st, a),
          "can_play should be True with cards in the deck")

    # --- C2. NEGATIVE can_play: False with an empty deck. ---
    st, a, b = fresh_state(db)
    a.deck = []
    check(not fx._TRAINER_CAN_PLAY["Ciphermaniac's Codebreaking"](st, a),
          "can_play should be False with an empty deck")

    # --- C3. POSITIVE: the two highest-value cards land on TOP of the deck
    # (index 0, 1) in value order, hand is UNCHANGED (they do NOT go to hand —
    # this is the key distinction from a search-to-hand effect), and the deck's
    # total size is unchanged. ---
    st, a, b = fresh_state(db)
    _search_deck(a)
    hand_before = list(a.hand)
    ok = fx._ciphermaniacs_codebreaking(ctx_for(st, a, b))
    check(ok, "Ciphermaniac's Codebreaking should report success with cards available")
    check(len(a.deck) == 5, f"deck size must be unchanged (5), got {len(a.deck)}")
    check(a.deck[0].name == "Froakie" and a.deck[1].name == "Feraligatr",
          f"the two highest-value picks (Froakie, Feraligatr) must be stacked on "
          f"TOP of the deck in that order, got {[c.name for c in a.deck[:2]]}")
    check(a.hand == hand_before,
          f"Ciphermaniac's Codebreaking must NOT put cards into hand, got "
          f"hand={[c.name for c in a.hand]}")

    # --- C4. Confirms the "top of deck, not hand" distinction end-to-end: the
    # next 2 draws pull EXACTLY the searched cards, in the stacked order. ---
    drawn = a.draw(2)
    check(drawn == 2 and [c.name for c in a.hand] == ["Froakie", "Feraligatr"],
          f"the next 2 draws should be exactly the searched cards in order, "
          f"got {[c.name for c in a.hand]}")

    # --- C5. NEGATIVE / edge case: fewer than 2 cards remain in the deck (1
    # card) -> takes what's available (1), no crash, still ends up on top,
    # still doesn't touch hand. ---
    st, a, b = fresh_state(db)
    a.deck = [db.get("Froakie")]
    hand_before = list(a.hand)
    ok = fx._ciphermaniacs_codebreaking(ctx_for(st, a, b))
    check(ok, "should still report success with 1 available card")
    check(len(a.deck) == 1 and a.deck[0].name == "Froakie",
          "the single available card should end up back on top, deck size unchanged")
    check(a.hand == hand_before, "hand must be untouched even in the partial case")

    # --- C6. NEGATIVE: an empty deck is a true no-op — no crash, reports
    # failure, hand/deck both untouched. ---
    st, a, b = fresh_state(db)
    a.deck = []
    hand_before = list(a.hand)
    ok = fx._ciphermaniacs_codebreaking(ctx_for(st, a, b))
    check(not ok, "Ciphermaniac's Codebreaking must no-op (report failure) on an empty deck")
    check(a.deck == [] and a.hand == hand_before,
          "an empty-deck no-op must leave deck and hand untouched")

    # --- C7. Full pipeline integration via play_trainer: the card is popped
    # from hand BEFORE the effect runs (engine-wide rule), ends up in discard,
    # marks supporter_played_this_turn, and the top-of-deck effect still fires
    # correctly through the real action dispatch (not just the bare function). ---
    st, a, b = fresh_state(db)
    _search_deck(a)
    a.hand = [db.get("Ciphermaniac's Codebreaking")]
    st.active_index = 0
    game.apply_action(st, game.Action(kind="play_trainer", hand_index=0))
    check(a.hand == [], "the Supporter should be popped from hand")
    check(any(c.name == "Ciphermaniac's Codebreaking" for c in a.discard),
          "the played Supporter should land in the discard pile")
    check(a.supporter_played_this_turn,
          "playing a Supporter must set supporter_played_this_turn")
    check(a.deck[0].name == "Froakie" and a.deck[1].name == "Feraligatr",
          f"the top-of-deck effect must fire through the real play_trainer "
          f"dispatch too, got {[c.name for c in a.deck[:2]]}")

    # =================================================================== #
    # MEGA STARMIE EX (me3-21) — "Jetting Blow" and "Nebula Beam"
    # =================================================================== #

    # --- N1. Jetting Blow, no wall: 120 to the Active (Dragapult ex has no
    # printed Weakness, isolating the base number), and 50 to a Fire-type
    # Benched Pokémon that IS weak to Water (Ponyta, weak Water x2) — proving
    # the bench hit does NOT apply Weakness (else it would be 100, not 50). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))          # no Weakness
    ponyta = InPlayPokemon(card=db.get("Ponyta"))                   # weak to Water x2
    b.bench = [ponyta]
    jb_i = next(i for i, atk in enumerate(a.active.card.attacks) if atk.name == "Jetting Blow")
    game._resolve_attack(st, jb_i)
    check(b.active is not None and b.active.damage == 120,
          f"Jetting Blow should deal exactly 120 to a non-Weak Active, got "
          f"{b.active.damage if b.active else 'KO'}")
    check(ponyta.damage == 50,
          f"Jetting Blow's bench hit must be exactly 50 with NO Weakness applied "
          f"(not 100, despite Ponyta being weak to Water), got {ponyta.damage}")

    # --- N2. Jetting Blow targets the LOWEST-remaining-HP Benched Pokémon
    # (gust-style v0 policy) when more than one candidate exists. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    b.active = InPlayPokemon(card=db.get("Dragapult ex"))
    low = InPlayPokemon(card=db.get("Ponyta"))                     # 70 HP
    low.damage = 60                                                 # remaining_hp = 10
    high = InPlayPokemon(card=db.get("Crustle"))                    # 150 HP, remaining 150
    b.bench = [high, low]
    game._resolve_attack(st, jb_i)
    check(low.damage == 60 + 50 and high.damage == 0,
          f"Jetting Blow must hit the LOWEST remaining-HP bencher (low), leaving "
          f"the healthier one (high) untouched; got low.damage={low.damage}, "
          f"high.damage={high.damage}")

    # --- N3. NEGATIVE / CRITICAL SETUP: Jetting Blow's base damage IS a
    # normal attack-damage chokepoint call, so Crustle's own "Mysterious Rock
    # Inn" wall ("Prevent all damage done to this Pokémon by attacks from your
    # opponent's Pokémon ex") DOES block it — Mega Starmie ex carries the 'ex'
    # subtype, satisfying the wall's gate. The Active takes 0. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    crustle_wall = InPlayPokemon(card=db.get("Crustle"))            # Mysterious Rock Inn
    b.active = crustle_wall
    game._resolve_attack(st, jb_i)
    check(crustle_wall.damage == 0,
          f"Jetting Blow must be FULLY BLOCKED by Crustle's Mysterious Rock Inn "
          f"(Mega Starmie ex is an opponent's Pokémon ex), got damage="
          f"{crustle_wall.damage}")

    # --- N4. THE CRITICAL CASE: the SAME Crustle wall (Mysterious Rock Inn)
    # active must take the FULL 210 from Nebula Beam UNPREVENTED — Nebula
    # Beam's text ("isn't affected by ... any effects on your opponent's
    # Active Pokémon") bypasses the wall via ignore_active_effects=True (the
    # same chokepoint flag Superb Scissors/Demolish use), proving the bypass
    # is attack-specific (Jetting Blow, same matchup, was fully blocked in
    # N3), not a blanket wall-disable for this attacker. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    crustle_wall2 = InPlayPokemon(card=db.get("Crustle"))
    b.active = crustle_wall2
    nb_i = next(i for i, atk in enumerate(a.active.card.attacks) if atk.name == "Nebula Beam")
    game._resolve_attack(st, nb_i)
    check(crustle_wall2.damage == 210,
          f"Nebula Beam must deal the FULL 210, UNPREVENTED, through Crustle's "
          f"Mysterious Rock Inn wall, got damage={crustle_wall2.damage}")

    # --- N5. Nebula Beam's "isn't affected by Weakness" clause, isolated from
    # the wall question: vs Cinderace ex (320 HP, no wall Ability, weak to
    # Water x2 — high HP so a x2 hit wouldn't KO it, keeping this purely about
    # the damage number), Nebula Beam must deal exactly 210 — NOT 420.
    # Contrast: Jetting Blow on the SAME matchup (no ignore_weakness) DOES
    # apply the x2, dealing 240. ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    b.active = InPlayPokemon(card=db.get("Cinderace ex"))            # weak to Water x2
    game._resolve_attack(st, nb_i)
    check(b.active is not None and b.active.damage == 210,
          f"Nebula Beam must deal exactly 210 with NO Weakness bonus even vs a "
          f"Water-weak target, got {b.active.damage if b.active else 'KO'}")

    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    b.active = InPlayPokemon(card=db.get("Cinderace ex"))
    game._resolve_attack(st, jb_i)
    check(b.active is not None and b.active.damage == 120 * 2,
          f"Jetting Blow (no ignore_weakness) must apply the x2 Weakness on the "
          f"Active normally, expected 240, got {b.active.damage if b.active else 'KO'}")

    # --- N6. Real-data fact (not a bug): Milotic ex's "Sparkling Scales" gates
    # on the SOURCE being Tera-typed. Mega Starmie ex (subtypes Stage 1/MEGA/
    # ex) is NOT Tera, so this wall is never actually live against it — BOTH
    # Jetting Blow and Nebula Beam connect in full against a Milotic ex
    # Active. (Milotic ex's own Weakness is Lightning; Mega Starmie ex is
    # Water, so no Weakness bonus muddies the numbers either way.) ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    milotic = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic
    b.bench = [InPlayPokemon(card=db.get("Ponyta"))]
    game._resolve_attack(st, jb_i)
    check(milotic.damage == 120,
          f"Jetting Blow must connect for the full 120 vs Milotic ex — Sparkling "
          f"Scales' Tera-source gate is never met by Mega Starmie ex, got "
          f"{milotic.damage}")
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    milotic2 = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic2
    game._resolve_attack(st, nb_i)
    check(milotic2.damage == 210,
          f"Nebula Beam must also connect for the full 210 vs Milotic ex for the "
          f"same reason, got {milotic2.damage}")

    # --- N7. Same real-data fact for Cornerstone Mask Ogerpon ex's
    # "Cornerstone Stance" — it gates on the SOURCE HAVING an Ability. Mega
    # Starmie ex has abilities=[], so this wall is also never live against it.
    # Both attacks connect in full (Cornerstone Ogerpon ex is weak to Grass,
    # not Water — no Weakness bonus either way). ---
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    ogerpon = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = ogerpon
    game._resolve_attack(st, jb_i)
    check(ogerpon.damage == 120,
          f"Jetting Blow must connect for the full 120 vs Cornerstone Mask "
          f"Ogerpon ex — Cornerstone Stance's ability-source gate is never met "
          f"by Mega Starmie ex, got {ogerpon.damage}")
    st, a, b = fresh_state(db)
    a.active = InPlayPokemon(card=db.get("Mega Starmie ex"))
    ogerpon2 = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = ogerpon2
    game._resolve_attack(st, nb_i)
    check(ogerpon2.damage == 210,
          f"Nebula Beam must also connect for the full 210 vs Cornerstone Mask "
          f"Ogerpon ex for the same reason, got {ogerpon2.damage}")

    # --- N8. MECHANISM CHECK: prove the exact ignore_active_effects=True /
    # ignore_weakness=True flags Nebula Beam uses DO bypass Sparkling Scales
    # and Cornerstone Stance too, when the attacking source actually satisfies
    # each wall's own gate (unlike Mega Starmie ex itself, per N6/N7). This
    # isolates "does the mechanism work for these walls" from "does Mega
    # Starmie ex specifically trigger them" (it doesn't, and N6/N7 show that
    # honestly). ---

    # 8a. Sparkling Scales (needs a Tera source) vs Milotic ex: a plain call
    # (mirrors Jetting Blow's own un-flagged apply_attack_damage) is blocked...
    st, a, b = fresh_state(db)
    milotic3 = InPlayPokemon(card=db.get("Milotic ex"))
    b.active = milotic3
    tera_source = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))  # Tera
    a.active = tera_source
    ctx = ctx_for(st, a, b, source=tera_source)
    dealt = fx.apply_attack_damage(ctx, milotic3, 210, owner=b, source=tera_source)
    check(dealt == 0 and milotic3.damage == 0,
          f"a plain (un-flagged) call from a Tera source must be BLOCKED by "
          f"Sparkling Scales, got dealt={dealt}")
    # ...while Nebula Beam's exact ignore-flags bypass it for the full 210.
    dealt2 = fx.apply_attack_damage(ctx, milotic3, 210, owner=b, source=tera_source,
                                    ignore_active_effects=True, ignore_weakness=True)
    check(dealt2 == 210 and milotic3.damage == 210,
          f"Nebula Beam's exact ignore-flags mechanism must bypass Sparkling "
          f"Scales for the full 210, got dealt={dealt2}")

    # 8b. Cornerstone Stance (needs an ability-bearing source) vs Cornerstone
    # Mask Ogerpon ex: a plain call from an ability-holder (Crustle) is
    # blocked...
    st, a, b = fresh_state(db)
    ogerpon3 = InPlayPokemon(card=db.get("Cornerstone Mask Ogerpon ex"))
    b.active = ogerpon3
    ability_source = InPlayPokemon(card=db.get("Crustle"))       # has an Ability
    a.active = ability_source
    ctx2 = ctx_for(st, a, b, source=ability_source)
    dealt3 = fx.apply_attack_damage(ctx2, ogerpon3, 210, owner=b, source=ability_source)
    check(dealt3 == 0 and ogerpon3.damage == 0,
          f"a plain (un-flagged) call from an ability-bearing source must be "
          f"BLOCKED by Cornerstone Stance, got dealt={dealt3}")
    # ...while Nebula Beam's exact ignore-flags bypass it for the full 210.
    dealt4 = fx.apply_attack_damage(ctx2, ogerpon3, 210, owner=b, source=ability_source,
                                    ignore_active_effects=True, ignore_weakness=True)
    check(dealt4 == 210 and ogerpon3.damage == 210,
          f"Nebula Beam's exact ignore-flags mechanism must bypass Cornerstone "
          f"Stance for the full 210, got dealt={dealt4}")

    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("test_starmie_support.py: all checks passed (Surfing Beach, "
          "Ciphermaniac's Codebreaking, Mega Starmie ex Jetting Blow / Nebula "
          "Beam wall-bypass critical case)")


if __name__ == "__main__":
    main()
