#!/usr/bin/env python3
"""
test_web.py — the local web UI (src/web/server.py).

Tests the pure page-render functions, then a live smoke: start the server on an
ephemeral port, hit the real endpoints over HTTP, and check status + content.

Run from project root:  python3 tests/test_web.py
"""

import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.web import server
from src.engine.decks import DECKS


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # --- pure render functions ---
    home = server.render_home()
    check("Run matchup" in home and "Who would win" in home, "home has the matchup controls")
    check("/matrix" in home, "home links the meta matrix")
    for d in ("dragapult", "gardevoir", "fighting"):
        check(d in home, f"home lists deck {d}")

    m = server.render_matchup("dragapult", "fire", {"d1_wins": 60, "d2_wins": 40, "ties": 0}, 100)
    check("60%" in m and "class=\"bar\"" in m, "matchup page shows win % and a bar")

    w = server.render_whowins("a", "b", "🏆  a wins about 8 out of 10")
    check("wins about 8 out of 10" in w, "whowins page wraps the friendly summary")

    decks = ["A", "B"]
    res = {"matrix": {"A": {"A": None, "B": 70}, "B": {"A": 30, "B": None}},
           "overall": {"A": 70.0, "B": 30.0}}
    mx = server.render_matrix(decks, res, {"A": 1600, "B": 1400}, 50)
    check("<table>" in mx and "70%" in mx and "Elo 1600" in mx, "matrix page renders the heatmap")

    # --- live smoke ---
    httpd = server.make_server(0)              # ephemeral port
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def get(path):
        try:
            with urllib.request.urlopen(base + path, timeout=30) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    try:
        s, h = get("/")
        check(s == 200 and "Run matchup" in h, "GET / serves the home page")
        s, h = get("/run?deck1=dragapult&deck2=raging_bolt&games=10&action=whowins")
        check(s == 200 and "wins about" in h, "GET /run (whowins) works over HTTP")
        s, h = get("/run?deck1=dragapult&deck2=fire&games=10&action=matchup")
        check(s == 200 and "%" in h, "GET /run (matchup) works over HTTP")
        s, _ = get("/run?deck1=nope&deck2=fire&games=5&action=matchup")
        check(s == 400, f"unknown deck returns 400 (got {s})")
        s, _ = get("/totally-missing")
        check(s == 404, f"missing path returns 404 (got {s})")
    finally:
        httpd.shutdown()

    if fails:
        print(f"FAIL ({len(fails)} issue(s)):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK — web UI: home/matchup/whowins/matrix render correctly; live server serves "
          "200/400/404 over HTTP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
