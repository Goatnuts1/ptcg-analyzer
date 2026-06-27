"""test_train.py — Phase-2 net/features tests (run with the Trainer venv):

    .venv/bin/python tests/test_train.py

Covers feature vectorizer (dims + determinism), the net (forward shapes, legal masking),
that training actually learns (policy accuracy rises over the untrained baseline), and that
a saved model artifact round-trips.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch

from src.engine.cards import CardDB

# isolate buffer/archive paths
_tmp = tempfile.mkdtemp(prefix="ptcgtrain_")
os.environ["PTCG_BUFFER_DIR"] = os.path.join(_tmp, "buffer")
os.environ["PTCG_ARCHIVE_DIR"] = os.path.join(_tmp, "archive")

from src.learn.actions import ACTION_SPACE
from src.learn.encoder import Vocab
from src.learn.features import CARD_SLOTS, NUMERIC_DIM, vectorize, records_to_arrays
from src.learn.net import PolicyValueNet, pick_device
from src.learn.train import evaluate
from src.learn.selfplay import generate_batch

fails = 0
def check(c, m):
    global fails
    print(("  ok  " if c else "  FAIL") + " " + m)
    if not c: fails += 1

POOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "standard_pool.json")
db = CardDB.from_pool(POOL)
vocab = Vocab.from_db(db)

print("== data ==")
records = generate_batch("dragapult", "charizard_xy", list(range(60)), db, vocab, "greedy")
check(len(records) > 1000, f"generated training records ({len(records)})")

print("\n== features ==")
check(CARD_SLOTS == 25, f"card slots = 25 (got {CARD_SLOTS})")
ids, num = vectorize(records[0]["state"])
check(len(ids) == CARD_SLOTS and len(num) == NUMERIC_DIM, f"vector dims ({len(ids)},{len(num)})")
ids2, num2 = vectorize(records[0]["state"])
check(ids == ids2 and num == num2, "vectorize is deterministic")
arr = records_to_arrays(records)
check(arr["card_ids"].shape == (len(records), CARD_SLOTS), "card_ids array shape")
check(arr["legal"].shape == (len(records), ACTION_SPACE) and arr["legal"].any(1).all(),
      "legal mask: every row has at least one legal action")
check(bool(arr["legal"][np.arange(len(records)), arr["action"]].all()),
      "chosen action is always inside its legal mask")

print("\n== net ==")
device = pick_device()
net = PolicyValueNet(vocab.size).to(device)
ci = torch.from_numpy(arr["card_ids"][:8]).to(device)
nm = torch.from_numpy(arr["numeric"][:8]).to(device)
logits, value = net(ci, nm)
check(tuple(logits.shape) == (8, ACTION_SPACE), f"policy logits shape {tuple(logits.shape)}")
check(tuple(value.shape) == (8,) and float(value.abs().max()) <= 1.0, "value in [-1,1]")
legal = torch.from_numpy(arr["legal"][:8]).to(device)
masked = net.masked_policy_logits(logits, legal)
probs = torch.softmax(masked, dim=1)
illegal_mass = float(probs[~legal].sum())
check(illegal_mass < 1e-4, f"illegal actions get ~0 probability (mass={illegal_mass:.2e})")

print("\n== training learns ==")
idx = np.arange(len(records))
base = evaluate(net, arr, idx, device)
opt = torch.optim.Adam(net.parameters(), lr=2e-3)
import torch.nn.functional as Fn
for _ in range(40):
    net.train()
    b_ci = torch.from_numpy(arr["card_ids"]).to(device)
    b_nm = torch.from_numpy(arr["numeric"]).to(device)
    b_lg = torch.from_numpy(arr["legal"]).to(device)
    b_ac = torch.from_numpy(arr["action"]).to(device)
    b_v = torch.from_numpy(arr["value"]).to(device)
    lo, va = net(b_ci, b_nm)
    loss = Fn.cross_entropy(net.masked_policy_logits(lo, b_lg), b_ac) + Fn.mse_loss(va, b_v)
    opt.zero_grad(); loss.backward(); opt.step()
trained = evaluate(net, arr, idx, device)
check(trained["policy_top1"] > base["policy_top1"] + 0.1,
      f"policy accuracy rose with training ({base['policy_top1']:.3f} -> {trained['policy_top1']:.3f})")
check(trained["policy_top1"] > 0.5, f"net imitates the policy ({trained['policy_top1']:.3f} top-1)")

print("\n== artifact round-trip ==")
path = os.path.join(_tmp, "m.pt")
torch.save({"state_dict": net.state_dict(), "vocab_size": vocab.size,
            "feature_version": 1, "action_version": 1}, path)
loaded = torch.load(path, map_location="cpu", weights_only=False)
net2 = PolicyValueNet(loaded["vocab_size"])
net2.load_state_dict(loaded["state_dict"])
check(loaded["feature_version"] == 1, "artifact carries feature version")
net_cpu = net.to("cpu").eval()
with torch.no_grad():
    l1, _ = net_cpu(ci.cpu(), nm.cpu())
    l2, _ = net2.eval()(ci.cpu(), nm.cpu())
check(torch.allclose(l1, l2, atol=1e-4), "reloaded net reproduces outputs")

import shutil
shutil.rmtree(_tmp, ignore_errors=True)
print(f"\n{'ALL PASSED' if fails == 0 else str(fails)+' FAILED'}")
sys.exit(1 if fails else 0)
