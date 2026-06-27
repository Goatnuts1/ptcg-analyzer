"""test_arena.py — Phase-3 neural-agent + arena tests (run with the Trainer venv):

    .venv/bin/python tests/test_arena.py

Needs a trained artifact in .selfplay/models/ (run src.learn.train first). Checks the
neural agents play only legal moves to completion, the arena returns sane numbers, the
Wilson CI is correct, and the promotion-gate logic is right.
"""
import glob
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learn import config
from src.learn.arena import play_match, wilson_ci, promotion_gate
from src.learn.infer import Model
from src.learn.neural_agent import PolicyAgent, NeuralMCTSAgent
from src.engine.agents import GreedyAgent

fails = 0
def check(c, m):
    global fails
    print(("  ok  " if c else "  FAIL") + " " + m)
    if not c: fails += 1

models = sorted(glob.glob(os.path.join(config.REPO_ROOT, ".selfplay", "models", "*.pt")))
if not models:
    print("no model artifact — run `.venv/bin/python -m src.learn.train` first"); sys.exit(1)
model = Model(models[-1])
print(f"loaded {os.path.basename(models[-1])} | metrics={model.metrics}")

print("\n== wilson CI ==")
p, (lo, hi) = wilson_ci(55, 100)
check(abs(p - 0.55) < 1e-9 and lo < 0.55 < hi, f"wilson ci sane: {p:.2f} [{lo:.2f},{hi:.2f}]")
_, (lo0, hi0) = wilson_ci(0, 0)
check(lo0 == 0.0 and hi0 == 0.0, "wilson handles n=0")

print("\n== neural agents play legal games to completion ==")
res_pol = play_match(lambda r: PolicyAgent(model, r), lambda r: GreedyAgent(r),
                     n_games=8, base_seed=1)
check(res_pol["decided"] >= 1, f"PolicyAgent vs Greedy completed games (decided={res_pol['decided']})")
check(0.0 <= res_pol["a_rate"] <= 1.0, f"win rate in [0,1] ({res_pol['a_rate']:.2f})")
check(res_pol["a_wins"] + res_pol["b_wins"] + res_pol["ties"] == res_pol["games"], "game tally consistent")

res_mcts = play_match(lambda r: NeuralMCTSAgent(model, iterations=12, rng=r),
                      lambda r: GreedyAgent(r), n_games=4, base_seed=2)
check(res_mcts["decided"] >= 1, f"NeuralMCTSAgent vs Greedy completed games (decided={res_mcts['decided']})")

print("\n== promotion gate ==")
g_win = promotion_gate({"a_rate": 0.60, "ci": (0.55, 0.65)}, margin=0.55, run_tests=False)
check(g_win["promote"] and g_win["beats_baseline"], "gate promotes a clear winner")
g_close = promotion_gate({"a_rate": 0.52, "ci": (0.47, 0.57)}, margin=0.55, run_tests=False)
check(not g_close["promote"], "gate rejects a too-close candidate (CI touches 0.5)")
g_lose = promotion_gate({"a_rate": 0.40, "ci": (0.35, 0.45)}, margin=0.55, run_tests=False)
check(not g_lose["promote"] and "lost" in g_lose["reason"], "gate rejects a loser")

print(f"\n{'ALL PASSED' if fails == 0 else str(fails)+' FAILED'}")
sys.exit(1 if fails else 0)
