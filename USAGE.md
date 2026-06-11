# How to use the Deck Analyzer

Two ways to use it: a **point-and-click web page** (easiest), or **terminal commands**
(more control). Both run entirely on your computer — no internet, no accounts, no cost.

> First time only — build the card database:
> ```bash
> python3 src/fetch_standard_pool.py --out data/standard_pool.json
> ```

---

## Option A — the web UI (easiest, great for quick testing)

```bash
python3 cli.py --serve
```

Then open **http://127.0.0.1:8000** in your browser. You'll get a page where you can:

- **Run matchup** — pick two decks, see who wins (with bars).
- **Who would win?** — a plain-English answer ("gardevoir wins about 6 out of 10!").
- **Show meta matrix** — a color-coded heatmap of every deck vs every deck, ranked by Elo.

Press **Ctrl-C** in the terminal to stop the server. (Use a different port with
`python3 cli.py --serve 9000`.)

---

## Option B — terminal commands

See the available decks:
```bash
python3 cli.py --list
```

**Who would win?** (the friendly one-liner)
```bash
python3 cli.py --who-would-win gardevoir fire
```

**Run a matchup** (exact win rates):
```bash
python3 cli.py --deck1 dragapult --deck2 charizard_xy --games 1000
```

**See the whole meta at once** — a win-rate matrix + Elo tier ranking:
```bash
python3 cli.py --round-robin
```

**Save the meta as a file** you can open or share:
```bash
python3 cli.py --round-robin --export meta.html    # color-coded heatmap (open in a browser)
python3 cli.py --round-robin --export meta.csv     # spreadsheet
```

**Import your own deck** from Pokémon TCG Live:
```bash
python3 cli.py --import-deck --name mydeck
# paste the TCG Live "Copy Deck List" export, then press Ctrl-D
```
It tells you which cards matched, which are missing/rotated, and whether the deck is
legal, then saves it to `decks/imported/mydeck.json`.

**Watch a single game step by step:**
```bash
python3 cli.py --deck1 dragapult --deck2 raging_bolt --seed 42 --save-game mygame
python3 cli.py --replay saved_games/mygame.json
```

---

## Good to know

- **Same `--seed` = same result, every time** — reproducible.
- `--agent greedy` (default) is fast; `--agent mcts` plays smarter but much slower and
  is fairer to combo decks (see "Reading the matrix" in the README).
- More games = a more accurate number (`--games 5000`); fewer = faster.
