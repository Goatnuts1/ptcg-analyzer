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

def _skip(reason: str) -> None:
    """Bow out cleanly (exit 0). This test needs a trained artifact, and .selfplay/ is
    gitignored + generated, so 'no usable artifact' is an environment state, not a code
    defect — it must not paint the suite red on a fresh clone or after a pool change."""
    print(f"SKIP test_arena: {reason}")
    print("  remediation: retrain against the current pool "
          "(`.venv/bin/python -m src.learn.train`) — note that replay-buffer records "
          "written under the OLD vocab must be regenerated too, since card ids shift.")
    sys.exit(0)


# Newest first by mtime: the freshest artifact is the one worth testing, and lexicographic
# sort doesn't track recency (cand_it9_* sorts before pvnet_*).
models = sorted(glob.glob(os.path.join(config.REPO_ROOT, ".selfplay", "models", "*.pt")),
                key=os.path.getmtime, reverse=True)
if not models:
    _skip("no model artifact in .selfplay/models — run `.venv/bin/python -m src.learn.train` first")

# The card vocabulary is derived from the pool, so ADDING A CARD renumbers every id after
# it alphabetically. infer.py rejects an artifact whose vocab_size no longer matches the
# pool — that guard is correct and deliberate (a stale artifact would silently index the
# wrong embedding rows), so we honour it and look for a compatible artifact rather than
# loosening it. Take the newest one that actually loads.
model = None
rejected = []
for path in models:
    try:
        model = Model(path)
        break
    except ValueError as e:          # feature/action/vocab version mismatch
        rejected.append(f"{os.path.basename(path)}: {e}")
if model is None:
    _skip(f"all {len(models)} artifact(s) are incompatible with the current card pool "
          f"— e.g. {rejected[0]}")
print(f"loaded {os.path.basename(path)} | metrics={model.metrics}")

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
