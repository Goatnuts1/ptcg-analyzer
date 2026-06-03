#!/usr/bin/env python3
"""
test_mcts_keys.py — guard against an action kind silently vanishing from MCTS search.

The play_stadium/attach_tool bug: those kinds had no `_semantic_key` case, so they
collapsed into the ("pass",) default and were dropped from `_deduped_legal` — invisible
to MCTS regardless of the evaluation. This test sweeps real games and asserts that for
EVERY legal action, its semantic key starts with the action's own kind (i.e. no kind
collapses), and that `_semantic_key` never falls through to a raising default.

Run from project root:  python3 tests/test_mcts_keys.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import load_tournament_deck, load_test_decks
from src.engine.agents import GreedyAgent
from src.engine.game import setup_game, start_turn, legal_actions, apply_action, Phase
from src.engine.mcts import _semantic_key, _deduped_legal


def main():
    fails = []
    db = CardDB.from_pool("data/standard_pool.json")
    seen_kinds = set()

    # Drive several diverse games; at every decision, check the key invariant for
    # all legal actions (these tournament decks exercise stadium/tool/ability/attack/
    # retreat/evolve/etc., the full action vocabulary).
    pairings = [("dragapult", "charizard_xy"), ("charizard_xy", "dragapult")]
    for gi in range(12):
        which = pairings[gi % 2]
        da = load_tournament_deck(db, which[0])
        dbk = load_tournament_deck(db, which[1])
        st = setup_game(da, dbk, seed=gi, db=db)
        start_turn(st)
        agent = GreedyAgent(random.Random(gi))
        guard = 0
        while st.phase != Phase.GAME_OVER and st.turn_number < 60 and guard < 4000:
            guard += 1
            if st.phase == Phase.MAIN:
                acts = legal_actions(st)
                for a in acts:
                    seen_kinds.add(a.kind)
                    try:
                        key = _semantic_key(st, a)
                    except ValueError as e:
                        fails.append(f"_semantic_key raised on kind {a.kind!r}: {e}")
                        continue
                    if key[0] != a.kind:
                        fails.append(f"action kind {a.kind!r} collapsed to key {key!r} "
                                     f"(would vanish from search)")
                # also: deduped set must not drop a distinct kind entirely
                kinds_in = {a.kind for a in acts}
                kinds_out = {k[0] for k in _deduped_legal(st)}
                missing = kinds_in - kinds_out
                if missing:
                    fails.append(f"_deduped_legal dropped whole kind(s): {missing}")
                act = agent.choose(st)
                apply_action(st, act)
                if act.kind in ("attack", "pass"):
                    st.phase = Phase.BETWEEN_TURNS
            if st.phase == Phase.BETWEEN_TURNS:
                from src.engine.game import end_turn
                end_turn(st)
                if not start_turn(st):
                    break

    # sanity: the sweep actually exercised the kinds that used to vanish
    for needed in ("play_stadium", "attach_tool"):
        if needed not in seen_kinds:
            fails.append(f"sweep never exercised {needed!r} — can't claim it's guarded")

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails[:15]:
            print("  -", f)
        return 1
    print(f"OK — every legal action kind keeps a distinct semantic key (no silent vanish). "
          f"Exercised kinds: {sorted(seen_kinds)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
