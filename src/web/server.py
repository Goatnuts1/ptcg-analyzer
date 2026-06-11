#!/usr/bin/env python3
"""
server.py — a tiny local web UI for the analyzer. **Stdlib only, zero dependencies.**

Run it with `python3 cli.py --serve` (opens http://127.0.0.1:8000). It's a thin
wrapper over the same functions the CLI uses — pick two decks and click:

  - "Run matchup"     -> win rates with bars
  - "Who would win?"  -> the plain-language readout
  - "Show meta matrix"-> the color-coded heatmap + Elo leaderboard

The page-rendering functions are pure (data -> HTML string) so they're unit-tested;
the HTTP handler is just glue that runs a quick greedy simulation and renders the result.
Binds to 127.0.0.1 only — it's a personal tool, not a public server.
"""

from __future__ import annotations

import html as _html
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.engine.decks import DECKS
from src.analysis.report import matrix_fragment, _MATRIX_CSS

_CSS = _MATRIX_CSS + (
    " .bar{height:1.4rem;border-radius:3px;background:#2e90c4;color:#fff;"
    "white-space:nowrap;padding:0 .4rem;line-height:1.4rem;font-size:.85rem}"
    " form{margin:1rem 0;padding:1rem;background:#f7f7f7;border:1px solid #ddd;border-radius:6px}"
    " select,input{font-size:1rem;padding:.2rem} button{font-size:1rem;padding:.3rem .8rem;"
    "margin:.2rem;cursor:pointer} a{color:#2e90c4} .big{font-size:1.3rem;line-height:2rem}")


def _page(title: str, body: str) -> str:
    esc = _html.escape
    return (f"<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{esc(title)}</title>\n<style>\n{_CSS}\n</style></head><body>\n"
            f"<p><a href=\"/\">&larr; home</a></p>\n<h1>{esc(title)}</h1>\n{body}\n"
            f"</body></html>\n")


def _deck_options(selected: str = "") -> str:
    return "".join(
        f"<option{' selected' if d == selected else ''}>{_html.escape(d)}</option>"
        for d in sorted(DECKS))


def render_home(decks=None) -> str:
    """The landing page: a matchup picker + a meta-matrix button + the deck list."""
    opts = _deck_options()
    decklist = ", ".join(sorted(DECKS))
    body = f"""
<p>Pick two decks and see who wins. Everything runs locally — no internet, no tokens.</p>
<form action="/run" method="get">
  <b>Matchup:</b>
  <select name="deck1">{opts}</select> vs
  <select name="deck2">{opts}</select>
  &nbsp; games <input name="games" value="200" size="4">
  <br>
  <button name="action" value="matchup">▶ Run matchup</button>
  <button name="action" value="whowins">🥊 Who would win?</button>
</form>
<form action="/matrix" method="get">
  <b>Whole meta:</b> games per pair <input name="games" value="60" size="4">
  <button>📊 Show meta matrix (heatmap + Elo)</button>
  <br><small>(plays every deck vs every deck — takes a few seconds)</small>
</form>
<p><b>Available decks:</b> {_html.escape(decklist)}</p>
<p><small>Tip: import your own from Pokémon TCG Live with
<code>python3 cli.py --import-deck</code>.</small></p>
"""
    return _page("Pokémon TCG Deck Analyzer", body)


def render_matchup(deck1: str, deck2: str, r: dict, games: int) -> str:
    esc = _html.escape
    tot = r["d1_wins"] + r["d2_wins"]
    p1 = 100 * r["d1_wins"] / tot if tot else 50
    p2 = 100 - p1
    body = f"""
<p>{games} games, mirrored seats (fair), greedy pilot.</p>
<p>{esc(deck1)} — <b>{p1:.0f}%</b> ({r['d1_wins']} wins)</p>
<div class="bar" style="width:{max(p1,4):.0f}%">{esc(deck1)}</div>
<p style="margin-top:1rem">{esc(deck2)} — <b>{p2:.0f}%</b> ({r['d2_wins']} wins)</p>
<div class="bar" style="width:{max(p2,4):.0f}%;background:#c4582e">{esc(deck2)}</div>
<p style="margin-top:1rem">Ties: {r['ties']}</p>
"""
    return _page(f"{deck1} vs {deck2}", body)


def render_whowins(deck1: str, deck2: str, summary: str) -> str:
    body = f'<pre class="big">{_html.escape(summary)}</pre>'
    return _page(f"Who would win? {deck1} vs {deck2}", body)


def render_matrix(decks, res: dict, elo: dict, games: int) -> str:
    frag = matrix_fragment(decks, res["matrix"], res["overall"], elo)
    return _page(f"Meta matrix ({games} games/pair, greedy)", frag)


class _Handler(BaseHTTPRequestHandler):
    pool = "data/standard_pool.json"

    def _send(self, html_str: str, code: int = 200):
        body = html_str.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):           # quiet — no per-request console spam
        pass

    def do_GET(self):
        import cli                           # lazy: reuse the CLI's sim functions
        from src.analysis.ratings import compute_elo
        from src.analysis.report import who_would_win

        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)

        def arg(name, default=""):
            return q.get(name, [default])[0]

        try:
            if parsed.path in ("/", "/index.html"):
                self._send(render_home())
            elif parsed.path == "/run":
                d1, d2 = arg("deck1"), arg("deck2")
                games = max(1, min(2000, int(arg("games", "200") or 200)))
                if d1 not in DECKS or d2 not in DECKS:
                    self._send(_page("Error", "<p>Unknown deck. <a href='/'>Back</a></p>"), 400)
                    return
                r = cli.run(d1, d2, games, "greedy", 0, mirror=True, pool=self.pool)
                if arg("action") == "whowins":
                    s = who_would_win(d1, d2, r["d1_wins"], r["d2_wins"], r["ties"], games)
                    self._send(render_whowins(d1, d2, s))
                else:
                    self._send(render_matchup(d1, d2, r, games))
            elif parsed.path == "/matrix":
                games = max(1, min(500, int(arg("games", "60") or 60)))
                decks = sorted(DECKS)
                res = cli.round_robin(decks, games, "greedy", 0, self.pool)
                elo = compute_elo(decks, res["matrix"])
                self._send(render_matrix(decks, res, elo, games))
            else:
                self._send(_page("Not found", "<p><a href='/'>home</a></p>"), 404)
        except Exception as e:               # never crash the server on one bad request
            self._send(_page("Error", f"<pre>{_html.escape(str(e))}</pre>"), 500)


def make_server(port: int = 8000, pool: str = "data/standard_pool.json"):
    _Handler.pool = pool
    return ThreadingHTTPServer(("127.0.0.1", port), _Handler)


def serve(port: int = 8000, pool: str = "data/standard_pool.json") -> None:
    httpd = make_server(port, pool)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"Deck Analyzer UI running at {url}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        httpd.shutdown()
