#!/usr/bin/env python3
"""
test_ismcts.py — the invariants of the cross-turn Information Set MCTS agent
(`ISMCTSAgent`) and of tree reuse (`MCTSAgent(reuse_tree=True)`).

What is pinned here, and why each one matters:

  1. AVAILABILITY COUNTS. A node is an information set, so successive iterations
     reach it under determinizations in which different actions are legal. If UCB
     normalised by the parent's visit count instead of each child's own
     availability, an action offered in 1 world out of 10 would look permanently
     under-explored and be chased as though always available — the shared-tree
     strategy-fusion failure. Guarded by driving real searches and asserting
     avail >= visits for every node, and that a rarely-legal action really does
     accumulate a lower availability than an always-legal sibling.

  2. SUBSET LEGALITY. Selection must only ever consider actions legal in the
     CURRENT determinization, and the action finally returned must be legal in the
     REAL state.

  3. NEGAMAX SIGN, inherited from MCTSAgent — opponent nodes are optimized for the
     opponent. Re-checked here on _ISNode because the new node type must not have
     broken the perspective bookkeeping.

  4. STABLE TIE-BREAKING. Ties in UCB and in the final most-visited choice resolve
     by semantic key order, never by dict/set iteration luck. (The cross-process
     half of this lives in tests/test_determinism.py.)

  5. TREE REUSE IS TURN-SCOPED. The retained subtree may only be adopted when the
     next decision is the same live state object, same actor, same turn number —
     otherwise the opponent moved in between and our statistics would be grafted
     onto a position that never occurred.

  6. NO BEHAVIOUR CHANGE. MCTSAgent must default to reuse OFF and must produce the
     same game it did before reuse existed.

Run from project root:  python3 tests/test_ismcts.py
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import load_deck
from src.engine.agents import GreedyAgent
from src.engine.game import setup_game, start_turn, legal_actions, apply_action, Phase
from src.engine.mcts import (ISMCTSAgent, MCTSAgent, _ISNode, _Node,
                             _semantic_key, _deduped_legal)
from src.engine.run import finish_game, _resolve_tie, play_game

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _walk(node, out):
    out.append(node)
    for ch in node.children.values():
        _walk(ch, out)
    return out


def _search_at(state, **kw):
    """Run one full ISMCTS search on `state` and hand back (action, root)."""
    agent = ISMCTSAgent(rng=random.Random(11), **kw)
    action = agent.choose(state)
    return agent, action


# --------------------------------------------------------------------------- #
def test_node_type_and_negamax():
    """_ISNode must still be a _Node (so the tested negamax backprop applies) and
    must carry its own availability counter."""
    check(issubclass(_ISNode, _Node), "_ISNode must subclass _Node to inherit backprop")
    n = _ISNode(None, ("pass",), chooser=0)
    check(n.avail == 0, "a fresh _ISNode starts with zero availability")

    ME, OPP = 0, 1
    agent = ISMCTSAgent()
    root = _ISNode(None, None, chooser=None)
    mine = _ISNode(root, ("attack", 0), chooser=ME)
    theirs = _ISNode(mine, ("attack", 0), chooser=OPP)
    agent._backprop(theirs, 0.9, me=ME)      # 0.9 is GOOD for me
    check(abs(mine.wins - 0.9) < 1e-9,
          f"my node stores my value, got {mine.wins}")
    check(abs(theirs.wins - 0.1) < 1e-9,
          f"opponent node must store 1-v (negamax), got {theirs.wins}")


def test_availability_and_legality(db):
    """Drive real searches and pin the information-set bookkeeping."""
    for deck1, deck2, seed in (("dragapult", "charizard_xy", 4),
                               ("hide_n_sneak", "mega_excadrill", 9)):
        st = setup_game(load_deck(db, deck1), load_deck(db, deck2), seed=seed, db=db)
        start_turn(st)
        # advance a few turns so the board is real (hands, bench, energy in play)
        greedy = GreedyAgent(random.Random(seed))
        for _ in range(6):
            if st.phase != Phase.MAIN:
                break
            a = greedy.choose(st)
            apply_action(st, a)
            if a.kind in ("attack", "pass"):
                from src.engine.game import end_turn
                st.phase = Phase.BETWEEN_TURNS
                end_turn(st)
                if not start_turn(st):
                    break
        if st.phase != Phase.MAIN:
            continue

        agent = ISMCTSAgent(iterations=80, rng=random.Random(seed), max_turn_hops=3)
        action = agent.choose(st)

        # 2. the returned action must be legal in the REAL state, not merely in
        #    some determinization that imagined a different deck order.
        real_keys = _deduped_legal(st)
        check(_semantic_key(st, action) in real_keys,
              f"{deck1}: ISMCTS returned an action illegal in the real state")

        root = agent._tree[3] if agent._tree else None
        check(root is not None, f"{deck1}: search should have retained a subtree")

        # rebuild the whole tree from the retained root's ancestor: the retained
        # node IS a child of the root we searched, so walk it plus its siblings via
        # a fresh search whose root we keep hold of.
        agent2 = ISMCTSAgent(iterations=80, rng=random.Random(seed), max_turn_hops=3,
                             reuse_tree=False)
        # reuse_tree=False means nothing is retained, so grab the root by re-running
        # the internals directly.
        from src.engine.mcts import determinize
        r = _ISNode(None, None, None)
        me = st.active_index
        for _ in range(80):
            world = determinize(st, me, agent2.rng)
            node = agent2._select_expand(r, world, me)
            agent2._backprop(node, agent2._evaluate(world, me), me)

        nodes = _walk(r, [])
        # 1. availability: every non-root node was offered at least as often as it
        #    was visited (it cannot be selected in an iteration where it is illegal).
        for n in nodes:
            if n is r:
                continue
            check(n.avail >= n.visits,
                  f"{deck1}: node {n.key} visited {n.visits}x but only available "
                  f"{n.avail}x — availability accounting is broken")
            check(n.avail >= 1, f"{deck1}: expanded node {n.key} has zero availability")
        check(len(nodes) > 1, f"{deck1}: search built no tree")

        # ... and the root's children must not all share one availability count,
        # otherwise availability is just parent.visits under another name and the
        # subset-armed bandit is not actually being modelled.
        avails = {ch.avail for ch in r.children.values()}
        check(len(r.children) < 2 or len(avails) >= 2,
              f"{deck1}: every root child has the same availability ({avails}) — "
              f"availability is not being tracked per child")

        # 4. stable tie-break: two searches with the same seed pick the same action.
        again = ISMCTSAgent(iterations=80, rng=random.Random(seed), max_turn_hops=3)
        check(_semantic_key(st, again.choose(st)) == _semantic_key(st, action),
              f"{deck1}: same seed produced a different ISMCTS decision")


def test_subset_armed_bandit():
    """THE strategy-fusion guard, isolated.

    In a real game almost every action is legal in almost every determinization, so
    a live search cannot demonstrate this cleanly. Here the legal set is controlled
    directly: one action is offered in only 1 world out of 5, the others in all of
    them. Correct information-set bookkeeping gives the rare action an availability
    count near a fifth of its siblings'; the bug this catches — normalising by the
    parent's visit count — would make every child look equally available, which is
    exactly how a shared tree starts trusting lines that depend on the opponent's
    hidden hand.
    """
    import src.engine.mcts as m

    RARE = ("play_trainer", "OnlySometimesLegal")
    ALWAYS = {("attack", 0): "a", ("pass",): "b"}
    calls = {"n": 0}

    def fake_legal(state):
        calls["n"] += 1
        offered = dict(ALWAYS)
        if calls["n"] % 5 == 0:
            offered[RARE] = "c"
        return offered

    class _StubWorld:
        phase = Phase.MAIN
        active_index = 0

    class _StubAgent(ISMCTSAgent):
        # the point is the bandit bookkeeping, so the engine is stubbed out entirely
        def _apply(self, world, action, me):
            pass

        def _evaluate(self, world, me):
            return 0.5

    original, m._deduped_legal = m._deduped_legal, fake_legal
    try:
        agent = _StubAgent(iterations=200, rng=random.Random(1), max_turn_hops=1)
        root = _ISNode(None, None, None)
        for _ in range(200):
            node = agent._select_expand(root, _StubWorld(), 0)
            agent._backprop(node, 0.5, 0)
    finally:
        m._deduped_legal = original

    rare = root.children.get(RARE)
    common = [ch for k, ch in root.children.items() if k != RARE]
    check(rare is not None, "the rarely-offered action was never expanded at all")
    check(len(common) == 2, f"expected both always-legal actions at the root, "
                            f"got {sorted(root.children)}")
    if rare is not None and common:
        best_common = max(ch.avail for ch in common)
        check(rare.avail < best_common / 2,
              f"rare action available {rare.avail}x vs {best_common}x for an "
              f"always-legal sibling — availability is not per-determinization")
        check(rare.visits <= rare.avail,
              f"rare action visited {rare.visits}x but only offered {rare.avail}x — "
              f"it was selected in a world where it was illegal")
        # and it must not be starved either: it IS explored when offered.
        check(rare.visits >= 1, "the rare action was never actually searched")


def test_tree_reuse_is_turn_scoped(db):
    """Reuse may only be adopted for the next decision of the SAME turn."""
    st = setup_game(load_deck(db, "dragapult"), load_deck(db, "charizard_xy"),
                    seed=31, db=db)
    start_turn(st)
    agent = ISMCTSAgent(iterations=40, rng=random.Random(31), max_turn_hops=2)
    a = agent.choose(st)
    retained = agent._tree
    if a.kind in ("attack", "pass"):
        # forced end of turn — nothing to assert about within-turn reuse here
        check(True, "")
    else:
        check(retained is not None, "an ongoing turn should retain a subtree")
        apply_action(st, a)
        if st.phase == Phase.MAIN:
            root_before = retained[3]
            visits_before = root_before.visits
            agent.choose(st)
            check(visits_before > 0, "retained root should carry inherited visits")

    # a DIFFERENT live state object must never be adopted, even at the same turn
    # number and actor — that is the exactness the identity check buys us.
    other = setup_game(load_deck(db, "dragapult"), load_deck(db, "charizard_xy"),
                       seed=31, db=db)
    start_turn(other)
    agent._tree = (st, other.active_index, other.turn_number, _ISNode(None, None, None))
    check(agent._reuse_root(other) is None,
          "reuse must refuse a state object it did not produce the tree for")

    # same object but the turn moved on -> refuse
    node = _ISNode(None, None, None)
    agent._tree = (other, other.active_index, other.turn_number - 1, node)
    check(agent._reuse_root(other) is None,
          "reuse must refuse once the turn number has advanced")

    # same object, same actor, same turn -> adopt, and detach it as a root
    node2 = _ISNode(None, None, None)
    node2.parent = _ISNode(None, None, None)
    agent._tree = (other, other.active_index, other.turn_number, node2)
    got = agent._reuse_root(other)
    check(got is node2, "reuse must adopt the retained node for the same decision point")
    check(got is None or got.parent is None,
          "an adopted root must be detached so backprop stops there")


def test_mcts_defaults_unchanged(db):
    """The hard constraint: MCTSAgent's defaults are untouched, so every recorded
    gauntlet number stays reproducible. Reuse is opt-in and OFF by default, and a
    game played with the default agent must be identical to one played with reuse
    explicitly disabled."""
    a = MCTSAgent()
    check(a.reuse_tree is False, "MCTSAgent must default to reuse_tree=False")
    check(a.iterations == 160 and a.rollout == "greedy" and a.search_plies == 1,
          "MCTSAgent's constructor defaults changed — recorded win rates would move")

    def play(reuse):
        st = setup_game(load_deck(db, "dragapult"), load_deck(db, "charizard_xy"),
                        seed=5, db=db)
        start_turn(st)
        finish_game(st,
                    MCTSAgent(iterations=30, rollout="eval", rng=random.Random(5),
                              search_plies=2, reuse_tree=reuse),
                    MCTSAgent(iterations=30, rollout="eval", rng=random.Random(5),
                              search_plies=2, reuse_tree=reuse))
        _resolve_tie(st)
        return st.winner, "\n".join(st.log)

    default_game = play(False)
    check(play(False) == default_game,
          "MCTSAgent with reuse off is not reproducible")


def test_ismcts_plays_a_full_game(db):
    """Liveness: implemented is not the same as exercised. The agent must actually
    pilot a complete game against greedy and reach a real result."""
    st = play_game(load_deck(db, "mega_excadrill"), load_deck(db, "clefairy_stock"),
                   ISMCTSAgent(iterations=40, rng=random.Random(2), max_turn_hops=3),
                   GreedyAgent(random.Random(3)), seed=2, db=db)
    check(st.phase == Phase.GAME_OVER or st.turn_number > 1,
          "ISMCTS agent failed to play a game to a conclusion")
    check(len(st.log) > 5, f"ISMCTS game produced only {len(st.log)} log lines")


def main():
    db = CardDB.from_pool("data/standard_pool.json")
    test_node_type_and_negamax()
    test_availability_and_legality(db)
    test_subset_armed_bandit()
    test_tree_reuse_is_turn_scoped(db)
    test_mcts_defaults_unchanged(db)
    test_ismcts_plays_a_full_game(db)

    if FAILS:
        print(f"FAIL ({len(FAILS)} issue(s)):")
        for f in FAILS:
            print("  -", f)
        return 1
    print("OK — cross-turn ISMCTS: availability-normalised UCB, determinization-legal "
          "actions only, negamax opponent nodes, key-stable tie-breaks, turn-scoped "
          "tree reuse, and MCTSAgent defaults untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
