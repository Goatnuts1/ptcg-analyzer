#!/usr/bin/env python3
"""
server.py — a tiny local web UI for the analyzer. **Stdlib only, zero dependencies.**

Run it with `python3 cli.py --serve` (opens http://127.0.0.1:8000). It's a thin
wrapper over the same functions the CLI uses — pick two decks and click:

  - "Run matchup"     -> win rates with bars
  - "Who would win?"  -> the plain-language readout
  - "Show meta matrix"-> the color-coded heatmap + Elo leaderboard
  - "Import a deck"   -> paste a TCG Live export, get a legality + implementation-
                         gap report, then run it against a reference gauntlet at
                         both greedy and MCTS strength

The page-rendering functions are pure (data -> HTML string) so they're unit-tested;
the HTTP handler is just glue that runs a quick greedy simulation and renders the result.
Binds to 127.0.0.1 only — it's a personal tool, not a public server.
"""

from __future__ import annotations

import html as _html
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.engine.cards import CardDB
from src.engine.decks import DECKS
from src.engine.legality import validate_deck
from src.importers.tcglive import import_deck, save_deck
from src.analysis.gap_check import check_deck_implementation
from src.analysis.report import matrix_fragment, _MATRIX_CSS

IMPORT_DIR = "decks/imported"

# The default reference gauntlet offered on the import-and-run form: the two
# faithful tournament lists plus the two homebrew wall decks. Anything else in
# DECKS can still be checked manually.
DEFAULT_GAUNTLET = [d for d in ("dragapult", "charizard_xy", "no_vacancy", "innkeeper")
                    if d in DECKS]

_CSS = _MATRIX_CSS + (
    " .bar{height:1.4rem;border-radius:3px;background:#2e90c4;color:#fff;"
    "white-space:nowrap;padding:0 .4rem;line-height:1.4rem;font-size:.85rem}"
    " form{margin:1rem 0;padding:1rem;background:#f7f7f7;border:1px solid #ddd;border-radius:6px}"
    " select,input,textarea{font-size:1rem;padding:.2rem} button{font-size:1rem;padding:.3rem .8rem;"
    "margin:.2rem;cursor:pointer} a{color:#2e90c4} .big{font-size:1.3rem;line-height:2rem}"
    " textarea{width:100%;box-sizing:border-box;font-family:ui-monospace,Menlo,monospace;font-size:.85rem}"
    " .ok{color:#1a7f37;font-weight:bold} .bad{color:#c4302e;font-weight:bold}"
    " .warn{color:#9a6700;font-weight:bold}"
    " ul.report{margin:.3rem 0} ul.report li{margin:.15rem 0}"
    " table.simres{border-collapse:collapse;margin:.6rem 0} table.simres td,table.simres th"
    "{padding:.3rem .7rem;border-bottom:1px solid #ddd;text-align:left}"
    " .explainer{background:#eef5fb;border:1px solid #cfe0ee;border-radius:6px;padding:.8rem 1rem;"
    "margin:1rem 0;font-size:.92rem} .explainer h3{margin-top:0}"
    " code.path{font-size:.8rem;color:#666}")


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
  <b>Which deck is best?</b> games per pair <input name="games" value="60" size="4">
  <button>🏆 Rank all decks (heatmap + Elo + best deck)</button>
  <br><small>(plays every deck vs every deck and ranks them — takes a few seconds)</small>
</form>
<p><b>Available decks:</b> {_html.escape(decklist)}</p>
<form action="/import" method="get">
  <b>Got a deck built?</b> Paste a TCG Live export, validate it, and simulate it.
  <br>
  <button>📋 Import a deck</button>
</form>
"""
    return _page("Pokémon TCG Deck Analyzer", body)


def render_import_form(prefill_name: str = "", prefill_text: str = "",
                       error: str = "") -> str:
    esc = _html.escape
    err = f'<p class="bad">{esc(error)}</p>' if error else ""
    body = f"""
<p>Paste a Pokémon TCG Live "Copy Deck List" export below. Every card is matched
against the current Standard pool and checked for legality (regulation marks,
4-copy rule, 1 ACE SPEC, exactly 60 cards) before anything gets simulated.</p>
{err}
<form action="/import" method="post">
  <label>Deck name: <input name="name" value="{esc(prefill_name)}" placeholder="my_deck"></label>
  <br><br>
  <textarea name="decklist" rows="16" placeholder="Pokémon: 16
3 Dwebble DRI 12
3 Crustle DRI 12
...

Trainer: 30
4 Boss's Orders
...

Energy: 14
5 Basic Grass Energy
...">{esc(prefill_text)}</textarea>
  <br>
  <button>Validate</button>
</form>
"""
    return _page("Import a deck", body)


def render_import_report(name: str, res, violations: list[str],
                         gaps: list[dict], saved_path: str) -> str:
    esc = _html.escape
    matched_ok = res.recipe and not res.missing
    legal_ok = matched_ok and not violations
    body = [f'<p>{esc(name)} — {res.matched_total}/{res.total} cards matched, '
            f'saved to <code class="path">{esc(saved_path)}</code></p>']

    if res.missing:
        body.append('<p class="bad">✗ Missing cards (not in the current pool — check '
                     'spelling or set legality):</p><ul class="report">')
        body.extend(f"<li>{q}× {esc(n)}</li>" for n, q in res.missing)
        body.append("</ul>")
    else:
        body.append('<p class="ok">✓ Every card matched the current pool.</p>')

    if res.warnings:
        body.append('<p class="warn">⚠ Unparsed lines:</p><ul class="report">')
        body.extend(f"<li>{esc(w)}</li>" for w in res.warnings)
        body.append("</ul>")

    if matched_ok:
        if violations:
            body.append('<p class="bad">✗ Not legal for current Standard:</p><ul class="report">')
            body.extend(f"<li>{esc(v)}</li>" for v in violations)
            body.append("</ul>")
        else:
            body.append('<p class="ok">✓ Legal — 60 cards, regulation marks current, '
                         'copy/ACE SPEC rules OK.</p>')

    if gaps:
        body.append(f'<p class="warn">⚠ {len(gaps)} card effect(s) may not be scripted yet '
                     '(heuristic — a flagged item might already be covered by a generic '
                     'engine fallback, but verify before trusting the sim numbers):</p>'
                     '<ul class="report">')
        for g in gaps:
            body.append(f'<li><b>{esc(g["card"])}</b> ({esc(g["kind"])} '
                        f'"{esc(g["name"])}"): {esc(g["text"])}</li>')
        body.append("</ul><p><small>These need implementing in "
                     "<code>src/engine/effects.py</code> before the sim numbers mean "
                     "anything — see the <code>deck-playbook</code> skill's step 2. "
                     "Simulating anyway is allowed below, but the flagged cards will "
                     "act as if they only deal printed damage with no rider.</small></p>")

    if legal_ok:
        opts = "".join(
            f'<label><input type="checkbox" name="opp" value="{esc(d)}"'
            f'{" checked" if d in DEFAULT_GAUNTLET else ""}> {esc(d)}</label><br>'
            for d in sorted(DECKS))
        body.append(f"""
<form action="/import/run" method="get">
  <input type="hidden" name="path" value="{esc(saved_path)}">
  <b>Run against:</b><br>{opts}
  <br>Greedy games/matchup <input name="games_greedy" value="1000" size="6">
  &nbsp; MCTS games/matchup <input name="games_mcts" value="60" size="4">
  <br>
  <button name="mode" value="greedy">▶ Run greedy (fast, seconds)</button>
  <button name="mode" value="mcts">🐢 Run MCTS (slow — pilots the deck properly;
    ~1-2 games/sec, so budget a few minutes for several opponents)</button>
</form>
""")
    elif matched_ok:
        body.append('<p><a href="/import">← fix the deck list above and re-import</a></p>')
    else:
        body.append('<p><a href="/import">← fix the missing cards above and re-import</a></p>')

    return _page(f"Import report: {name}", "\n".join(body))


def render_sim_results(deck_name: str, mode: str, games: int,
                       rows: list[dict]) -> str:
    """`rows`: [{"opp": str, "d_wins": int, "opp_wins": int, "ties": int}, ...]"""
    esc = _html.escape
    body = [f"<p>{esc(deck_name)} vs the gauntlet — {games} games/matchup, "
            f"{'greedy' if mode == 'greedy' else 'MCTS'} pilot.</p>",
            '<table class="simres"><tr><th>Opponent</th><th>Win %</th>'
            '<th>Record</th></tr>']
    for r in rows:
        tot = r["d_wins"] + r["opp_wins"]
        pct = 100 * r["d_wins"] / tot if tot else 50
        body.append(f'<tr><td>{esc(r["opp"])}</td><td><b>{pct:.1f}%</b></td>'
                    f'<td>{r["d_wins"]}-{r["opp_wins"]}-{r["ties"]}</td></tr>')
    body.append("</table>")
    body.append(_greedy_vs_mcts_explainer(mode))
    return _page(f"{deck_name} vs gauntlet ({mode})", "\n".join(body))


def _greedy_vs_mcts_explainer(mode: str = "") -> str:
    """A static explanation of what greedy and MCTS actually are, why they can
    disagree, and which to trust for which deck shape — grounded in a real,
    sourced finding from this project rather than generic flavor text."""
    if mode == "greedy":
        note = ("<p><b>You just ran greedy.</b> Treat this as a floor, not a verdict — "
                "run the MCTS pass too before trusting a close or surprising number.</p>")
    elif mode == "mcts":
        note = ("<p><b>You just ran MCTS.</b> This is the more trustworthy number for "
                "control, stall, and combo decks. If it disagrees with a greedy run by "
                "more than ~5-8 points, believe the MCTS number.</p>")
    else:
        note = ""
    return f"""
<div class="explainer">
<h3>Greedy vs. MCTS — what's the difference, and why both?</h3>
<p><b>Greedy</b> picks each turn's action by a hand-written priority list (mostly:
rank legal attacks by printed damage, fall back to generic Item/Supporter rules).
It's fast — about 900-1000 games/second — because it never looks more than one
action ahead. That speed is exactly its weakness: it can't sequence a multi-turn
plan (set up a wall THEN swing a finisher, hold up a hand-disruption Supporter
for the right turn, bluff a KO to bait a bad retreat). It ranks a deck as
strong exactly to the extent that "attack for the most damage available right
now" is a good strategy for it — which flatters simple aggro and quietly
mispilots anything that wins by sequencing.</p>
<p><b>MCTS</b> (Monte Carlo Tree Search) actually simulates forward from the
current position — it plays out many possible continuations and picks the
action whose simulated futures look best. It's far slower (roughly 1-2
games/second here) but it can find and execute multi-turn lines greedy can't
even see, so it's the more trustworthy read on a control/stall/combo deck's
real strength.</p>
<p><b>A real example from this project:</b> the "Innkeeper" wall deck was
deliberately built to trade win rate for disruption. Greedy piloting put it at
a 50.4% coinflip against the format's benchmark deck. MCTS piloting put the
exact same 60 cards at <b>61%</b> — because greedy was mispiloting Innkeeper's
denial sequencing (hammers, item lock timing, damage-transfer abilities) the
whole time. The deck wasn't actually mediocre; the fast pilot just couldn't
play it correctly. That's the failure mode to watch for: if a control/combo
deck's greedy number looks worse than you'd expect from its card quality,
don't trust it until you've checked MCTS.</p>
{note}
</div>
"""


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
    best = max(decks, key=lambda d: elo[d])
    overall = res["overall"]
    headline = (
        f'<p class="big">🏆 Best deck this run: <b>{_html.escape(best)}</b> — '
        f'Elo {elo[best]} · {overall[best]:.0f}% overall.</p>\n'
        '<p><small>⚠️ This quick view uses the fast <b>greedy</b> pilot, which '
        'over-rates simple aggressive decks (~14 pts). For the trustworthy ranking, '
        'run <code>python3 cli.py --round-robin --agent mcts --export best.html</code> '
        '(slower, pilots combo decks fairly).</small></p>\n')
    frag = matrix_fragment(decks, res["matrix"], overall, elo)
    return _page(f"Meta matrix ({games} games/pair, greedy)", headline + frag)


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

    def _safe_import_path(self, path: str) -> str | None:
        """Only ever open files inside IMPORT_DIR — the `path` field round-trips
        through a form, so don't trust it blindly even on localhost."""
        real_dir = os.path.realpath(IMPORT_DIR)
        real_path = os.path.realpath(path)
        if os.path.commonpath([real_dir, real_path]) != real_dir:
            return None
        return real_path if os.path.isfile(real_path) else None

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
            elif parsed.path == "/import":
                self._send(render_import_form())
            elif parsed.path == "/import/run":
                import json as _json
                path = self._safe_import_path(arg("path"))
                if path is None:
                    self._send(_page("Error", "<p>Unknown or invalid import file. "
                                     "<a href='/import'>Back</a></p>"), 400)
                    return
                with open(path, encoding="utf-8") as f:
                    record = _json.load(f)
                recipe = [(n, c) for n, c in record["recipe"]]
                db = CardDB.from_pool(self.pool)
                violations = validate_deck(db, recipe)
                if violations:
                    self._send(_page("Error", "<p>This saved deck is no longer legal: "
                                     f"{_html.escape('; '.join(violations))}. "
                                     "<a href='/import'>Re-import</a></p>"), 400)
                    return
                opponents = [d for d in q.get("opp", []) if d in DECKS]
                if not opponents:
                    self._send(_page("Error", "<p>Pick at least one opponent. "
                                     "<a href='/import'>Back</a></p>"), 400)
                    return
                mode = arg("mode", "greedy")
                if mode == "mcts":
                    games = max(5, min(300, int(arg("games_mcts", "60") or 60)))
                    agent = "mcts"
                else:
                    games = max(1, min(2000, int(arg("games_greedy", "1000") or 1000)))
                    agent = "greedy"
                rows = []
                for opp in opponents:
                    r = cli.run_recipe(recipe, opp, games, agent, seed=2026,
                                       mirror=True, pool=self.pool)
                    rows.append({"opp": opp, "d_wins": r["d1_wins"],
                                "opp_wins": r["d2_wins"], "ties": r["ties"]})
                self._send(render_sim_results(record.get("name", "imported deck"),
                                              mode, games, rows))
            else:
                self._send(_page("Not found", "<p><a href='/'>home</a></p>"), 404)
        except Exception as e:               # never crash the server on one bad request
            self._send(_page("Error", f"<pre>{_html.escape(str(e))}</pre>"), 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)

        def arg(name, default=""):
            return form.get(name, [default])[0]

        try:
            if parsed.path == "/import":
                name = arg("name").strip() or "imported_deck"
                text = arg("decklist")
                if not text.strip():
                    self._send(render_import_form(name, text,
                                                  error="Paste a deck list first."))
                    return
                db = CardDB.from_pool(self.pool)
                res = import_deck(text, db)
                violations = validate_deck(db, res.recipe) if res.recipe and not res.missing else []
                gaps = check_deck_implementation(res.recipe, db) if res.recipe else []
                saved_path = save_deck(res, name, out_dir=IMPORT_DIR)
                self._send(render_import_report(name, res, violations, gaps, saved_path))
            else:
                self._send(_page("Not found", "<p><a href='/'>home</a></p>"), 404)
        except Exception as e:
            self._send(_page("Error", f"<pre>{_html.escape(str(e))}</pre>"), 500)


def make_server(port: int = 8000, pool: str = "data/standard_pool.json",
                host: str = "127.0.0.1"):
    _Handler.pool = pool
    return ThreadingHTTPServer((host, port), _Handler)


def serve(port: int = 8000, pool: str = "data/standard_pool.json",
         host: str = "127.0.0.1") -> None:
    httpd = make_server(port, pool, host)
    url = f"http://{host}:{httpd.server_address[1]}"
    print(f"Deck Analyzer UI running at {url}  (Ctrl-C to stop)")
    if host != "127.0.0.1":
        print(f"⚠ Bound to {host}, not just localhost — reachable from other devices "
              "that can route to this machine (e.g. your LAN or Tailscale peers). "
              "There's no login/auth on this server, so anyone who can reach that "
              "address can run simulations and read/write files under decks/imported/.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        httpd.shutdown()
