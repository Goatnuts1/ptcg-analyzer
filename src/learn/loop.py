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
            pol = torch.from_numpy(arr["policy"][j]).to(device)
            vv = torch.from_numpy(arr["value"][j]).to(device)
            logits, value = net(ci, nm)
            # soft-target policy cross-entropy against the MCTS visit distribution:
            # -sum(target * log_softmax(masked logits)). Illegal logp is -inf but its
            # target is 0, so zero those terms (avoid 0*-inf = nan).
            logp = torch.log_softmax(net.masked_policy_logits(logits, lg), dim=1)
            logp = torch.nan_to_num(logp, neginf=0.0)
            loss_p = -(pol * logp).sum(dim=1).mean()
            loss = loss_p + F.mse_loss(value, vv)
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


def run_iteration(it: int, best_path: str | None, db, vocab, args) -> tuple[str | None, dict]:
    """One policy-iteration step. Returns (new_best_path, summary). best stays put if the
    candidate doesn't clear the gate. Self-play uses the CURRENT best so the data
    distribution co-evolves with the net (the fix for the Phase-3 distribution shift)."""
    import shutil
    seed = args.seed + it
    make_best, best_model = best_factory(best_path, args.iters)
    label = "greedy-rollout MCTS" if best_model is None else os.path.basename(best_path)
    print(f"[iter {it}] best={label} | self-play {args.games} games ...", flush=True)
    t = time.time()
    recs = selfplay(make_best, args.games, db, vocab, seed)
    sp = time.time() - t
    print(f"[iter {it}]   {len(recs)} records in {sp:.0f}s | training candidate ...", flush=True)

    net, _ = train_candidate(recs, vocab.size, args.epochs, seed=seed)
    cand_path = save_candidate(net, vocab.size, 24, 256, f"it{it}_s{args.seed}")
    cand = Model(cand_path)

    t = time.time()
    best_arena = lambda r: make_best(0, r)
    match = play_match(lambda r: NeuralMCTSAgent(cand, iterations=args.iters, rng=r),
                       best_arena, n_games=args.arena, base_seed=seed + 1000, pool=args.pool)
    # Engine is unchanged across iterations, so the rules tests can't regress here; the
    # model can't break rules by construction. Skip the (slow) suite per-iteration.
    gate = promotion_gate(match, margin=args.margin, run_tests=False)
    summary = {"it": it, "a_rate": match["a_rate"], "ci": match["ci"],
               "promote": gate["promote"], "arena_s": time.time() - t, "selfplay_s": sp}
    print(f"[iter {it}]   candidate {match['a_rate']*100:.1f}% vs best  "
          f"CI[{match['ci'][0]*100:.0f},{match['ci'][1]*100:.0f}]  -> {gate['reason'].upper()}", flush=True)

    if gate["promote"]:
        best_new = os.path.join(MODELS_DIR, f"best_it{it}_s{args.seed}.pt")
        shutil.copyfile(cand_path, best_new)
        print(f"[iter {it}]   PROMOTED -> {os.path.basename(best_new)}", flush=True)
        return best_new, summary
    return best_path, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=1, help="policy-iteration steps to run")
    ap.add_argument("--games", type=int, default=400, help="self-play games per iteration")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--arena", type=int, default=80, help="arena games for the gate")
    ap.add_argument("--iters", type=int, default=60, help="MCTS iterations per move")
    ap.add_argument("--best", default="none", help="starting best artifact path, or 'none'")
    ap.add_argument("--margin", type=float, default=0.55)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool", default=config.DEFAULT_POOL)
    args = ap.parse_args()

    db = CardDB.from_pool(args.pool)
    vocab = Vocab.from_db(db)
    best_path = None if args.best == "none" else args.best
    t0 = time.time()
    promotions = 0
    print(f"convergence run: {args.iterations} iterations · {args.games} games/iter · "
          f"arena {args.arena} · MCTS {args.iters}it · start best="
          f"{'greedy-rollout MCTS' if best_path is None else os.path.basename(best_path)}", flush=True)
    for it in range(args.iterations):
        best_path, summary = run_iteration(it, best_path, db, vocab, args)
        promotions += int(summary["promote"])
        print(f"[iter {it}] done ({(time.time()-t0)/60:.1f} min elapsed, {promotions} promotions so far)", flush=True)
    print(f"DONE: {args.iterations} iterations, {promotions} promotions, "
          f"{(time.time()-t0)/60:.1f} min. Final best="
          f"{'(none promoted)' if best_path is None else os.path.basename(best_path)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
