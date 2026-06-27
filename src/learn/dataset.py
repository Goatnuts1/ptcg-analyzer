"""dataset.py — read records back out of the sharded buffer (hot + archive).

Phase 1 keeps this minimal: iterate decoded records across all shards, with optional
feature-version filtering. Phase 2 (the net) adds tensor batching on top of this.
"""
from __future__ import annotations

import gzip
import json
import os
from typing import Iterator, Optional

from . import config


def _shards(dirs: list[str]) -> list[str]:
    out: list[str] = []
    for d in dirs:
        if os.path.isdir(d):
            out += sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl.gz"))
    return out


def iter_records(include_archive: bool = True,
                 feature_version: Optional[int] = None) -> Iterator[dict]:
    """Yield every record from the hot buffer (and the archive, if mounted/requested)."""
    dirs = [config.BUFFER_DIR]
    if include_archive and config.archive_available():
        dirs.append(config.ARCHIVE_DIR)
    for shard in _shards(dirs):
        try:
            with gzip.open(shard, "rt", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if feature_version is not None and rec.get("fv") != feature_version:
                        continue
                    yield rec
        except (OSError, EOFError):
            # a shard mid-write or a vanished USB drive — skip it, don't crash the reader
            continue


def count_records(include_archive: bool = True) -> int:
    return sum(1 for _ in iter_records(include_archive=include_archive))
