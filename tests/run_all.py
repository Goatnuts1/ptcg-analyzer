"""run_all.py — run every tests/test_*.py as a script (the suite is stdlib, script-style:
exit 0 = pass). Reports PASS / SKIP / FAIL per file and exits non-zero on any failure.

    python3 tests/run_all.py            # all files, 4 parallel workers
    python3 tests/run_all.py -j 8 mcts  # only files whose name contains 'mcts'
"""
import argparse
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run_one(path, timeout):
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, path], cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout)
        rc, out = p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out = -9, f"TIMEOUT after {timeout}s\n{e.stdout or ''}"
    status = "FAIL" if rc != 0 else ("SKIP" if out.lstrip().startswith("SKIP")
                                     or "\nSKIP " in out else "PASS")
    return os.path.basename(path), status, time.time() - t0, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("filter", nargs="?", default="")
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    files = sorted(f for f in glob.glob(os.path.join(HERE, "test_*.py"))
                   if a.filter in os.path.basename(f))
    with ThreadPoolExecutor(a.j) as ex:
        results = list(ex.map(lambda f: run_one(f, a.timeout), files))
    counts = {"PASS": 0, "SKIP": 0, "FAIL": 0}
    for name, status, dt, out in results:
        counts[status] += 1
        print(f"{status:4}  {dt:6.1f}s  {name}")
        if status == "FAIL":
            print("      " + "\n      ".join(out.strip().splitlines()[-8:]))
    print(f"\nPASS={counts['PASS']} SKIP={counts['SKIP']} FAIL={counts['FAIL']} "
          f"of {len(results)}")
    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()
