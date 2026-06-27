"""loop.py — one policy-iteration step: self-play -> train -> arena-gate -> promote.

This is the engine of "smarter over time" (plan §5). Each iteration:
  1. self-play N games with the current BEST agent (the engine enforces the rules),
  2. train a candidate net on those fresh, on-distribution records,
  3. arena the candidate agent vs the best agent (mirrored, Wilson CI),
  4. promote the candidate to best iff it clears the gate (beats by margin + rules tests).

Training on the agent's OWN self-play data (not a fixed teacher's) is what fixes the
distribution shift that makes a greedy-bootstrapped value net misjudge searched states.
Run it overnight in a loop; here a single iteration is the unit. Neural self-play is slow
(value-net leaf per node), so real iterations want many games — size to the wall-clock.

  .venv/bin/python -m src.learn.loop --games 400 --epochs 4 --arena 80 --best <artifact|none>
"""
from __future__ import annotations

import argparse
import os
import random
import time

import numpy as np
import torch
import torch.nn.functional as F

from src.engine.agents import GreedyAgent
from src.engine.cards import CardDB
from src.engine.mcts import MCTSAgent

from . import config
from .arena import play_match, promotion_gate
from .encoder import Vocab
from .features import records_to_arrays
from .infer import Model
from .net import PolicyValueNet, pick_device
from .neural_agent import NeuralMCTSAgent
from .selfplay import all_deck_ids, generate_batch
from .train import MODELS_DIR, _git_sha


def best_factory(best_path: str | None, iterations: int):
    """Agent factory for the current best. No model yet -> greedy-rollout MCTS (the
    strongest hand-coded agent, ~62% vs greedy) as the bootstrap opponent."""
    if best_path and os.path.exists(best_path):
        model = Model(best_path)
        return (lambda seat, rng: NeuralMCTSAgent(model, iterations=iterations, rng=rng)), model
    return (lambda seat, rng: MCTSAgent(iterations=iterations, rollout="greedy", rng=rng)), None


def selfplay(factory, games: int, db, vocab, base_seed: int) -> list[dict]:
    rng = random.Random(base_seed)
    decks = all_deck_ids()
    recs: list[dict] = []
    for g in range(games):
        a = decks[g % len(decks)]
        b = decks[(g * 7 + 3) % len(decks)]
        recs += generate_batch(a, b, [rng.randint(0, 2**31 - 1)], db, vocab,
                               agent_factory=factory)
    return recs


def train_candidate(records, vocab_size, epochs, lr=1e-3, batch=2048,
                    embed=24, hidden=256, seed=0):
    torch.manual_seed(seed)
    device = pick_device()
    arr = records_to_arrays(records)
    n = len(records)
    net = PolicyValueNet(vocab_size, embed=embed, hidden=hidden).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    idx = np.arange(n)
    for _ in range(epochs):
        np.random.shuffle(idx)
        net.train()
        for s in range(0, n, batch):
            j = idx[s:s + batch]
            ci = torch.from_numpy(arr["card_ids"][j]).to(device)
            nm = torch.from_numpy(arr["numeric"][j]).to(device)
            lg = torch.from_numpy(arr["legal"][j]).to(device)
            ac = torch.from_numpy(arr["action"][j]).to(device)
            vv = torch.from_numpy(arr["value"][j]).to(device)
            logits, value = net(ci, nm)
            loss = F.cross_entropy(net.masked_policy_logits(logits, lg), ac) + F.mse_loss(value, vv)
            opt.zero_grad(); loss.backward(); opt.step()
    return net.to("cpu").eval(), device


def save_candidate(net, vocab_size, embed, hidden, tag: str) -> str:
    os.makedirs(MODELS_DIR, exist_ok=True)
    path = os.path.join(MODELS_DIR, f"cand_{tag}.pt")
    torch.save({"state_dict": net.state_dict(),
                "feature_version": config.FEATURE_VERSION,
                "action_version": config.ACTION_VERSION,
                "vocab_size": vocab_size, "embed": embed, "hidden": hidden,
                "git_sha": _git_sha()}, path)
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=400, help="self-play games this iteration")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--arena", type=int, default=80, help="arena games for the gate")
    ap.add_argument("--iters", type=int, default=60, help="MCTS iterations per move")
    ap.add_argument("--best", default="none", help="current best artifact path, or 'none'")
    ap.add_argument("--margin", type=float, default=0.55)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool", default=config.DEFAULT_POOL)
    args = ap.parse_args()

    db = CardDB.from_pool(args.pool)
    vocab = Vocab.from_db(db)
    best_path = None if args.best == "none" else args.best
    make_best, best_model = best_factory(best_path, args.iters)

    print(f"iteration: best={'greedy-rollout MCTS' if best_model is None else os.path.basename(best_path)} "
          f"| self-play {args.games} games ...")
    t = time.time()
    recs = selfplay(make_best, args.games, db, vocab, args.seed)
    print(f"  {len(recs)} records in {time.time()-t:.0f}s | training candidate ({args.epochs} epochs) ...")

    net, device = train_candidate(recs, vocab.size, args.epochs, seed=args.seed)
    cand_path = save_candidate(net, vocab.size, 24, 256, _git_sha() + f"_s{args.seed}")
    cand = Model(cand_path)

    print(f"  arena: candidate vs best ({args.arena} games) ...")
    t = time.time()
    best_arena = lambda r: make_best(0, r)   # arena factories take (rng); drop the seat
    match = play_match(lambda r: NeuralMCTSAgent(cand, iterations=args.iters, rng=r),
                       best_arena, n_games=args.arena, base_seed=args.seed + 99, pool=args.pool)
    gate = promotion_gate(match, margin=args.margin, run_tests=True)
    print(f"  candidate {match['a_rate']*100:.1f}% vs best  CI[{match['ci'][0]*100:.0f},"
          f"{match['ci'][1]*100:.0f}]  ({time.time()-t:.0f}s) -> {gate['reason'].upper()}")

    if gate["promote"]:
        best_new = os.path.join(MODELS_DIR, f"best_{_git_sha()}_s{args.seed}.pt")
        import shutil
        shutil.copyfile(cand_path, best_new)
        print(f"  PROMOTED -> {best_new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
