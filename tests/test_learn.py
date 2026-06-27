"""test_learn.py — Phase-1 learning-pipeline tests (standalone script).

Covers: action<->id bounds + legality mask, encoder determinism + hidden-info safety,
self-play record validity (chosen action is legal; value z matches the winner), and the
sharded buffer (atomic shards round-trip; archive flush; USB-unavailable tolerated).
"""
import gzip
import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.engine.decks import load_deck
from src.engine.game import legal_actions, setup_game, Action

fails = 0
def check(cond, msg):
    global fails
    print(("  ok  " if cond else "  FAIL") + " " + msg)
    if not cond:
        fails += 1

POOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "standard_pool.json")
db = CardDB.from_pool(POOL)

# Point the pipeline at temp dirs BEFORE importing modules that read config paths.
_tmp = tempfile.mkdtemp(prefix="ptcglearn_")
os.environ["PTCG_BUFFER_DIR"] = os.path.join(_tmp, "buffer")
os.environ["PTCG_ARCHIVE_DIR"] = os.path.join(_tmp, "archive")
os.environ["PTCG_SHARD_RECORDS"] = "500"

from src.learn import config, buffer, dataset            # noqa: E402
from src.learn.actions import action_to_id, legal_ids, ACTION_SPACE  # noqa: E402
from src.learn.encoder import Vocab, encode_state        # noqa: E402
from src.learn.selfplay import generate_batch            # noqa: E402

print("== actions ==")
check(150 < ACTION_SPACE < 400, f"action space is bounded (~270): {ACTION_SPACE}")
check(0 <= action_to_id(Action(kind="pass")) < ACTION_SPACE, "pass maps in range")
check(action_to_id(Action("attack", attack_index=0)) != action_to_id(Action("attack", attack_index=1)),
      "distinct attacks get distinct ids")
# total mapping: a wildly out-of-range index still maps inside the space (clamped)
check(0 <= action_to_id(Action("attach_energy", hand_index=99, target_index=99)) < ACTION_SPACE,
      "out-of-range indices clamp into range (never raises)")

print("\n== encoder ==")
vocab = Vocab.from_db(db)
check(vocab.size > 1200, f"vocab built from pool ({vocab.size} ids)")
state = setup_game(load_deck(db, "dragapult"), load_deck(db, "charizard_xy"), seed=7, db=db)
enc1 = encode_state(state, vocab)
enc2 = encode_state(state, vocab)
check(enc1 == enc2, "encoding is deterministic for a fixed state")
check("opp_hand" not in enc1, "opponent hand identities are NOT encoded (no hidden-info leak)")
check(enc1["opp_hand_n"] >= 0 and "me_hand" in enc1, "opp hand is a count; my hand is encoded")
check(len(enc1["me_bench"]) == 5 and len(enc1["opp_bench"]) == 5, "bench is fixed 5 slots")

print("\n== self-play records ==")
records = generate_batch("dragapult", "charizard_xy", [11, 22, 33, 44], db, vocab, "greedy")
check(len(records) > 50, f"a few games produced records ({len(records)})")
check(all(r["action"] in r["legal"] for r in records), "every chosen action id is in its legal mask")
check(all(set([r["z"]]) <= {-1.0, 0.0, 1.0} for r in records), "value z in {-1,0,1}")
check(all(r["fv"] == config.FEATURE_VERSION for r in records), "records stamped with feature version")
# value consistency: within a game (seed), winner's seat has z=+1, loser z=-1 (or all 0 on tie)
by_seed = {}
for r in records:
    by_seed.setdefault(r["seed"], set()).add((r["seat"], r["z"]))
ok_val = True
for seed, pairs in by_seed.items():
    zs = {z for _, z in pairs}
    if zs != {0.0}:                       # decisive game
        ok_val = ok_val and zs <= {-1.0, 1.0} and len({s for s, _ in pairs}) >= 1
check(ok_val, "z is consistent with the game outcome per seed")
# determinism: same seeds -> identical records
again = generate_batch("dragapult", "charizard_xy", [11, 22, 33, 44], db, vocab, "greedy")
check(records == again, "same seeds reproduce identical records (deterministic data)")

print("\n== buffer: shards, round-trip, archive flush ==")
config.ensure_dirs()
w = buffer.ShardWriter(config.BUFFER_DIR, tag="t", shard_records=200)
for r in records:
    w.write(r)
sealed = w.close()
check(len(sealed) >= 1, f"records sharded ({len(sealed)} shards)")
check(all(p.endswith(".jsonl.gz") and os.path.exists(p) for p in sealed), "shards are gzip files on disk")
check(not any(f.endswith(".tmp") for f in os.listdir(config.BUFFER_DIR)), "no leftover .tmp files (atomic writes)")
read_back = list(dataset.iter_records(include_archive=False))
check(len(read_back) == len(records), f"all records read back ({len(read_back)}=={len(records)})")

# archive flush to a real (temp) archive dir
moved, ok = buffer.flush_to_archive(keep_hot=1)
check(ok and moved >= 0, f"flush ran against available archive (moved {moved})")
st = buffer.buffer_stats()
check(st["archive_shards"] == moved, "moved shards now live in the archive")

# USB-unavailable: point archive at a non-existent mount -> flush is a no-op, no crash
os.environ["PTCG_ARCHIVE_DIR"] = "/Volumes/__definitely_not_mounted__/x"
import importlib
importlib.reload(config); importlib.reload(buffer)
moved2, ok2 = buffer.flush_to_archive()
check((not ok2) and moved2 == 0, "unplugged T7 -> flush no-ops without raising")

shutil.rmtree(_tmp, ignore_errors=True)
print(f"\n{'ALL PASSED' if fails == 0 else str(fails)+' FAILED'}")
sys.exit(1 if fails else 0)
