"""train.py — Phase 2 bootstrap training: supervised policy/value from self-play records.

Reads the replay buffer (hot + T7 archive), vectorizes, and trains the PolicyValueNet to
imitate the recorded (greedy) policy and predict the game outcome:
  policy loss = masked cross-entropy(logits, chosen action)   (illegal actions masked out)
  value  loss = MSE(tanh value, z)
Reports policy top-1 agreement, value sign-accuracy + calibration, and saves a VERSIONED
model artifact (weights + FEATURE/ACTION versions + metrics + git sha) so the app/RL loop
can pin a compatible model.

  .venv/bin/python -m src.learn.train --epochs 6 --max-records 600000
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time

import numpy as np
import torch
import torch.nn.functional as F

from . import config, dataset
from .actions import ACTION_SPACE
from .features import NUMERIC_DIM, records_to_arrays
from .net import PolicyValueNet, pick_device

MODELS_DIR = os.path.join(config.REPO_ROOT, ".selfplay", "models")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=config.REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def load_dataset(max_records: int | None, feature_version: int) -> dict:
    recs = []
    for r in dataset.iter_records(feature_version=feature_version):
        recs.append(r)
        if max_records and len(recs) >= max_records:
            break
    if not recs:
        raise SystemExit("no records in the buffer — run `python -m src.learn.generate` first.")
    return records_to_arrays(recs), len(recs)


def _to_tensors(arr: dict, idx: np.ndarray, device) -> dict:
    return {
        "card_ids": torch.from_numpy(arr["card_ids"][idx]).to(device),
        "numeric": torch.from_numpy(arr["numeric"][idx]).to(device),
        "action": torch.from_numpy(arr["action"][idx]).to(device),
        "legal": torch.from_numpy(arr["legal"][idx]).to(device),
        "value": torch.from_numpy(arr["value"][idx]).to(device),
    }


def evaluate(net, arr, idx, device, batch=4096) -> dict:
    net.eval()
    tot = len(idx)
    pol_correct = val_sign_correct = val_n = 0
    val_sqerr = 0.0
    with torch.no_grad():
        for s in range(0, tot, batch):
            b = _to_tensors(arr, idx[s:s + batch], device)
            logits, value = net(b["card_ids"], b["numeric"])
            masked = net.masked_policy_logits(logits, b["legal"])
            pred = masked.argmax(dim=1)
            pol_correct += (pred == b["action"]).sum().item()
            val_sqerr += F.mse_loss(value, b["value"], reduction="sum").item()
            decisive = b["value"] != 0
            val_sign_correct += ((torch.sign(value) == torch.sign(b["value"])) & decisive).sum().item()
            val_n += decisive.sum().item()
    return {
        "policy_top1": pol_correct / max(tot, 1),
        "value_mse": val_sqerr / max(tot, 1),
        "value_sign_acc": val_sign_correct / max(val_n, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--value-weight", type=float, default=1.0)
    ap.add_argument("--max-records", type=int, default=None)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--embed", type=int, default=24)
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool", default=config.DEFAULT_POOL)
    ap.add_argument("--archive", action="store_true", help="also copy the artifact to the T7")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = pick_device()

    # vocab size from the pool (must match the encoder used to write the records)
    from src.engine.cards import CardDB
    from .encoder import Vocab
    vocab_size = Vocab.from_db(CardDB.from_pool(args.pool)).size

    print(f"device={device} | loading records (fv={config.FEATURE_VERSION}) ...")
    arr, n = load_dataset(args.max_records, config.FEATURE_VERSION)
    print(f"  {n} records | numeric_dim={NUMERIC_DIM} action_space={ACTION_SPACE} vocab={vocab_size}")

    rng = np.random.default_rng(args.seed)
    perm = rng.permutation(n)
    n_val = max(1, int(n * args.val_frac))
    val_idx, train_idx = perm[:n_val], perm[n_val:]

    net = PolicyValueNet(vocab_size, embed=args.embed, hidden=args.hidden).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    nparams = sum(p.numel() for p in net.parameters())
    print(f"  net: {nparams/1e6:.2f}M params")

    base = evaluate(net, arr, val_idx, device)
    print(f"  baseline (untrained): policy_top1={base['policy_top1']:.3f} "
          f"value_sign_acc={base['value_sign_acc']:.3f}")

    t0 = time.time()
    for ep in range(1, args.epochs + 1):
        net.train()
        rng.shuffle(train_idx)
        ep_loss = 0.0
        nb = 0
        for s in range(0, len(train_idx), args.batch):
            b = _to_tensors(arr, train_idx[s:s + args.batch], device)
            logits, value = net(b["card_ids"], b["numeric"])
            masked = net.masked_policy_logits(logits, b["legal"])
            loss_p = F.cross_entropy(masked, b["action"])
            loss_v = F.mse_loss(value, b["value"])
            loss = loss_p + args.value_weight * loss_v
            opt.zero_grad(); loss.backward(); opt.step()
            ep_loss += loss.item(); nb += 1
        m = evaluate(net, arr, val_idx, device)
        print(f"  epoch {ep}/{args.epochs}: loss={ep_loss/nb:.3f} | "
              f"val policy_top1={m['policy_top1']:.3f} value_mse={m['value_mse']:.3f} "
              f"value_sign_acc={m['value_sign_acc']:.3f}")
    dt = time.time() - t0

    final = evaluate(net, arr, val_idx, device)
    os.makedirs(MODELS_DIR, exist_ok=True)
    sha = _git_sha()
    name = f"pvnet_fv{config.FEATURE_VERSION}_av{config.ACTION_VERSION}_{sha}.pt"
    path = os.path.join(MODELS_DIR, name)
    artifact = {
        "state_dict": net.state_dict(),
        "feature_version": config.FEATURE_VERSION,
        "action_version": config.ACTION_VERSION,
        "vocab_size": vocab_size, "numeric_dim": NUMERIC_DIM, "action_space": ACTION_SPACE,
        "embed": args.embed, "hidden": args.hidden,
        "metrics": final, "train_records": int(len(train_idx)), "git_sha": sha,
        "trained_seconds": round(dt, 1),
    }
    torch.save(artifact, path)
    print(f"saved artifact -> {path}")
    print(f"  final: policy_top1={final['policy_top1']:.3f} value_sign_acc={final['value_sign_acc']:.3f} "
          f"value_mse={final['value_mse']:.3f}  ({dt:.1f}s)")

    if args.archive and config.archive_available():
        adir = os.path.join(os.path.dirname(config.ARCHIVE_DIR.rstrip("/")), "models")
        os.makedirs(adir, exist_ok=True)
        import shutil
        shutil.copyfile(path, os.path.join(adir, name))
        print(f"  archived artifact -> {adir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
