#!/usr/bin/env python3
"""
test_mcts_negamax.py — guard the piece-2b correctness invariant: in a multi-turn
tree, a node's statistic is stored from the perspective of the player who CHOSE it,
so opponent nodes are optimized for the opponent (negamax), not for us.

The bug this catches is the dangerous one: if backprop stored every node from `me`'s
view, the search would model an opponent that HELPS us, inflating the win rate in a
way that looks believable. These checks are pure-logic (no engine needed) so they
run fast and pin the invariant precisely.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.mcts import _Node, MCTSAgent


def main():
    fails = []
    def check(c, m):
        if not c: fails.append(m)

    ME, OPP = 0, 1
    agent = MCTSAgent()

    # Build a 3-deep path: root -> A(chooser=me) -> B(chooser=opp) -> C(chooser=me)
    root = _Node(None, None, chooser=None)
    a = _Node(root, "a", chooser=ME)
    b = _Node(a, "b", chooser=OPP)
    c = _Node(b, "c", chooser=ME)

    # A leaf value of 0.8 = good for ME. Backprop it up the path.
    agent._backprop(c, 0.8, me=ME)

    # my nodes accumulate the value as-is; the opponent's node accumulates (1-v).
    check(abs(c.wins - 0.8) < 1e-9, f"my node C should store 0.8, got {c.wins}")
    check(abs(b.wins - 0.2) < 1e-9, f"opponent node B should store 1-0.8=0.2, got {b.wins}")
    check(abs(a.wins - 0.8) < 1e-9, f"my node A should store 0.8, got {a.wins}")
    check(abs(root.wins - 0.8) < 1e-9, f"root (chooser None) stores my value, got {root.wins}")
    for n in (root, a, b, c):
        check(n.visits == 1, "every node on the path visited once")

    # Decisive check: a line that's great for ME (value->1) must look BAD at the
    # opponent's node (their stored value ->0). If an inversion bug stored `value`
    # everywhere, B.wins would trend to 1.0 and the opponent would be modeled as
    # cooperating. Accumulate several decisive-for-me leaves through B.
    root2 = _Node(None, None, chooser=None)
    a2 = _Node(root2, "a", chooser=ME)
    b2 = _Node(a2, "b", chooser=OPP)
    for _ in range(10):
        leaf = _Node(b2, "c", chooser=ME)
        agent._backprop(leaf, 1.0, me=ME)
    opp_mean = b2.wins / b2.visits
    check(opp_mean < 0.05,
          f"opponent node fed me-winning leaves must score ~0 for the opponent, got {opp_mean:.3f}")

    # Symmetry: evaluating from the opponent's seat flips it.
    root3 = _Node(None, None, chooser=None)
    n3 = _Node(root3, "x", chooser=OPP)
    agent._backprop(n3, 0.3, me=ME)   # 0.3 for me == 0.7 for opp
    check(abs(n3.wins - 0.7) < 1e-9, f"opp node should store 1-0.3=0.7, got {n3.wins}")

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails: print("  -", f)
        sys.exit(1)
    print("OK — negamax backprop: opponent nodes optimized for the opponent (no inversion).")


if __name__ == "__main__":
    main()
