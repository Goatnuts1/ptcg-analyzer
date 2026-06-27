"""config.py — paths, worker count, and schema versions for the learning pipeline.

Storage layout follows docs/LEARNING_ENGINE_PLAN.md §7a (the M5 + T7 rig):

  HOT  rolling replay buffer + active shards -> INTERNAL SSD (fast random reads)
  COLD sealed shards archive                 -> EXTERNAL T7  (bulk; USB, may detach)

All paths are env-overridable so this is portable to a fan-cooled box / cloud later.
"""
from __future__ import annotations

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# --- storage ---------------------------------------------------------------
# Hot buffer lives on the internal NVMe (several GB/s); never on the removable T7.
BUFFER_DIR = _env("PTCG_BUFFER_DIR", os.path.join(REPO_ROOT, ".selfplay", "buffer"))
# Cold archive on the external T7 (bulk). If unmounted, flushing is skipped, not fatal.
ARCHIVE_DIR = _env("PTCG_ARCHIVE_DIR", "/Volumes/OLLAMASSD/ptcg/archive")

# --- self-play -------------------------------------------------------------
# 8, not 10: the M5 Air is fanless — leave headroom so it throttles less (plan §7a).
NUM_WORKERS = int(_env("PTCG_WORKERS", "8"))
DEFAULT_POOL = os.path.join(REPO_ROOT, "data", "standard_pool.json")

# --- buffer / shards -------------------------------------------------------
SHARD_RECORDS = int(_env("PTCG_SHARD_RECORDS", "20000"))   # records per shard before rollover
ROLLING_SHARDS = int(_env("PTCG_ROLLING_SHARDS", "200"))   # hot shards to keep internal (rest archived)

# --- schema versions (bump when the on-disk format or feature spec changes) --
FEATURE_VERSION = 1     # state encoder spec (encoder.py)
ACTION_VERSION = 1      # Action<->id space (actions.py)
RECORD_VERSION = 1      # record envelope (selfplay.py)


def ensure_dirs() -> None:
    os.makedirs(BUFFER_DIR, exist_ok=True)


def archive_available() -> bool:
    """True if the external archive root is mounted and writable (T7 plugged in)."""
    parent = os.path.dirname(ARCHIVE_DIR.rstrip("/"))
    # The mount point (…/OLLAMASSD) must exist; the ptcg/archive subdir we create.
    return os.path.isdir(parent) or os.path.isdir(ARCHIVE_DIR)
