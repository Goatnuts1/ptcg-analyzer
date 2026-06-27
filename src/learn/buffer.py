"""buffer.py — sharded, gzip-compressed, atomic record buffer + archive flush.

Records are written as gzipped JSONL shards. Writes are atomic (temp file + os.replace),
so a crash or an unplugged drive never leaves a half-written shard. The hot buffer lives
on the internal SSD (config.BUFFER_DIR); sealed shards are flushed to the external T7
archive (config.ARCHIVE_DIR) when it's mounted, and the hot buffer is pruned to the last
ROLLING_SHARDS — so internal disk stays bounded no matter how many games are played.

If the T7 is unplugged, flush() is a no-op that returns False (logged by the caller) and
shards simply accumulate internally until it returns — the producer never crashes.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil

from . import config


class ShardWriter:
    """Append records to gzipped JSONL shards under `directory`, rolling at `shard_records`.

    `tag` namespaces shard filenames so parallel workers don't collide
    (e.g. tag='w03' -> w03-000001.jsonl.gz).
    """

    def __init__(self, directory: str, tag: str = "s", shard_records: int = config.SHARD_RECORDS):
        self.dir = directory
        self.tag = tag
        self.shard_records = max(1, shard_records)
        os.makedirs(directory, exist_ok=True)
        self._n = 0                 # records in the current shard
        self._seq = 0
        self._fh = None
        self._tmp = None
        self._sealed: list[str] = []

    def _open_new(self) -> None:
        self._seq += 1
        self._final = os.path.join(self.dir, f"{self.tag}-{self._seq:06d}.jsonl.gz")
        self._tmp = self._final + ".tmp"
        self._fh = gzip.open(self._tmp, "wt", encoding="utf-8")
        self._n = 0

    def write(self, record: dict) -> None:
        if self._fh is None:
            self._open_new()
        self._fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._n += 1
        if self._n >= self.shard_records:
            self._seal()

    def _seal(self) -> None:
        if self._fh is None:
            return
        self._fh.close()
        os.replace(self._tmp, self._final)   # atomic: temp -> final
        self._sealed.append(self._final)
        self._fh = None
        self._tmp = None

    def close(self) -> list[str]:
        """Seal any partial shard and return the list of sealed shard paths."""
        self._seal()
        return list(self._sealed)


def _shards_in(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, f) for f in os.listdir(directory)
                  if f.endswith(".jsonl.gz"))


def flush_to_archive(keep_hot: int = config.ROLLING_SHARDS) -> tuple[int, bool]:
    """Move all but the newest `keep_hot` hot shards to the T7 archive (atomic copies).

    Returns (n_archived, archive_was_available). If the T7 is unplugged, returns (0, False)
    and leaves every shard in the hot buffer — never raises.
    """
    if not config.archive_available():
        return 0, False
    try:
        os.makedirs(config.ARCHIVE_DIR, exist_ok=True)
    except OSError:
        return 0, False

    hot = _shards_in(config.BUFFER_DIR)
    to_move = hot[:-keep_hot] if keep_hot > 0 else hot
    moved = 0
    for src in to_move:
        name = os.path.basename(src)
        dst = os.path.join(config.ARCHIVE_DIR, name)
        tmp = dst + ".tmp"
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)            # atomic publish into the archive
            os.remove(src)                  # only drop the hot copy after a clean archive
            moved += 1
        except OSError:
            # T7 vanished mid-flush (USB) or transient error — stop, keep the rest hot.
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            break
    return moved, True


def buffer_stats() -> dict:
    hot = _shards_in(config.BUFFER_DIR)
    arch = _shards_in(config.ARCHIVE_DIR)
    hot_bytes = sum(os.path.getsize(p) for p in hot)
    arch_bytes = sum(os.path.getsize(p) for p in arch) if arch else 0
    return {
        "hot_shards": len(hot), "hot_bytes": hot_bytes,
        "archive_shards": len(arch), "archive_bytes": arch_bytes,
        "archive_available": config.archive_available(),
    }
