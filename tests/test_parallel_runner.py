#!/usr/bin/env python3
"""test_parallel_runner.py — the multiprocessing runner is deterministic (results do
not depend on worker count), honours --seat-order, and labels its output as a relative
bot-vs-bot signal. Run: python3 tests/test_parallel_runner.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.analysis.parallel_runner import run_parallel, LABEL  # noqa: E402


def _rows(path):
    with open(path) as f:
        return [",".join(l.strip().split(",")[:7]) for l in f]   # drop timing column


def test_parallel_runner():
    d = tempfile.mkdtemp()
    a = run_parallel("crustle_drew_v11", "basic_box_gantner", 24, workers=1,
                     out=os.path.join(d, "a.csv"), quiet=True)
    b = run_parallel("crustle_drew_v11", "basic_box_gantner", 24, workers=4,
                     out=os.path.join(d, "b.csv"), quiet=True)
    assert _rows(os.path.join(d, "a.csv")) == _rows(os.path.join(d, "b.csv")), \
        "worker count changed the results"
    assert a["overall"] == b["overall"]
    assert a["deck1_first"]["games"] == 12 and a["deck2_first"]["games"] == 12
    assert a["label"] == LABEL and "NOT a prediction" in LABEL
    c = run_parallel("crustle_drew_v11", "basic_box_gantner", 6, workers=2,
                     seat_order="deck2", quiet=True)
    assert c["deck2_first"]["games"] == 6 and c["deck1_first"]["games"] == 0


if __name__ == "__main__":
    test_parallel_runner()
    print("test_parallel_runner.py: all checks passed")
