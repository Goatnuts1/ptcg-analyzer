#!/usr/bin/env python3
"""
tcglive_log.py — parse a Pokémon TCG Live BATTLE LOG into a structured game record.

Sibling of `tcglive.py`, which imports a DECK LIST. This one imports a GAME: the
in-app battle log, copied out as plain text, e.g.

    Setup
    Goatest1 chose tails for the opening coin flip.
    Imboutwhatever won the coin toss.
    Imboutwhatever decided to go first.
    Goatest1 drew 7 cards for the opening hand.
    - 7 drawn cards.
       • Crustle, Basic Darkness Energy, Dwebble, Boss's Orders, Dwebble, ...
    Goatest1 played Dwebble to the Active Spot.

    Goatest1's Turn
    Goatest1 drew Lillie's Determination.
    Goatest1's Dwebble used Ascension.
    - Goatest1 evolved Dwebble to Crustle in the Active Spot.

WHY THIS EXISTS: every win rate in this project is engine-vs-engine. Self-consistent,
but unfalsified — a card whose script is subtly wrong stays wrong as long as the unit
test asserts the same wrong thing, because I wrote both. A real log is the one input
that was produced by the actual game, so it can contradict us. This module is the
front door for that evidence.

SCOPE: parsing and card resolution ONLY. It builds an event tree and tells you how
much of it is understood; it does NOT drive the engine. Replaying a log against
`GameState` is a separate (much larger) job, and it needs this to be trustworthy first.

THE LOG IS PARTIAL INFORMATION, AND THE PARSER MUST NOT PRETEND OTHERWISE. A log is
written from ONE seat — yours. Your own draws are named ("Goatest1 drew Boss's Orders."),
the opponent's are not ("Yumari78 drew a card."), and hidden reveals show as "A card was
added to X's hand." Anything built on top of this has to treat the two seats as
asymmetric; `GameLog.observer` records which seat the log was copied from.

TWO PASTE DIALECTS. The same client produces two indentation styles depending on where
the text was copied from, and both appear in real captures:

    dash dialect      "- <child>"        then "   • <grandchild>"
    bullet dialect    "    •    <child>" then "• <grandchild>"

So bullet depth is NOT a reliable nesting signal on its own. `_split_marker` classifies
by marker + indent together, and nesting is resolved per-log after sniffing the dialect.

APOSTROPHES ARE MIXED WITHIN A SINGLE LINE — the client emits ASCII for the acting
player and typographic for the target:

    AlanFonseca77's N's Zoroark ex used Night Joker on Goatest1's Genesect ex for 60 damage.
                 ^ ASCII                                        ^ U+2019 in the raw text

Everything is normalised to ASCII before matching. Do not "simplify" that away.

CARD NAMES CONTAIN POSSESSIVES ("N's Zoroark ex", "Team Rocket's Petrel", "Lillie's
Determination"), so a naive `(.+?)'s` split finds the wrong boundary. Every possessive
pattern here is anchored on a KNOWN PLAYER NAME, discovered in a first pass, which is
why player discovery happens before any event parsing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from src.importers.tcglive import _candidates, _fold

# --------------------------------------------------------------------------- #
# Text normalisation
# --------------------------------------------------------------------------- #

# Typographic punctuation the client mixes with ASCII, plus the non-breaking spaces
# that survive a copy-paste out of the app.
_PUNCT = {
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", " ": " ", " ": " ",
}


def normalize(text: str) -> str:
    """Fold the client's mixed punctuation to ASCII. Accents are LEFT ALONE — 'Pokémon'
    and 'Poké Pad' are real card/UI text, and `_fold` handles accent-insensitive
    matching later."""
    for bad, good in _PUNCT.items():
        text = text.replace(bad, good)
    return unicodedata.normalize("NFC", text)


# --------------------------------------------------------------------------- #
# Line structure
# --------------------------------------------------------------------------- #

# A leading list marker: "- ", "• ", "•\t", with any surrounding whitespace.
_MARKER_RE = re.compile(r"^(\s*)([-•])\s+(.*)$")


def _split_marker(raw: str) -> tuple[str, int, str]:
    """(marker, indent, text) for one raw line. marker is '' for a top-level line."""
    m = _MARKER_RE.match(raw)
    if not m:
        return "", 0, raw.strip()
    indent, marker, text = m.group(1), m.group(2), m.group(3)
    return marker, len(indent), text.strip()


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #

@dataclass
class Event:
    """One log line, plus whatever sub-lines nested under it."""
    kind: str                                   # 'attack', 'evolve', ... or 'unparsed'
    actor: str | None = None                    # player name, when the line names one
    raw: str = ""                               # the line as written (normalised)
    fields: dict = field(default_factory=dict)  # kind-specific payload
    children: list["Event"] = field(default_factory=list)

    def walk(self):
        """Self, then every descendant, depth-first."""
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Turn:
    number: int                 # 1-based across the whole game, both seats interleaved
    player: str | None          # None for the pre-game Setup block
    events: list[Event] = field(default_factory=list)


@dataclass
class GameLog:
    players: list[str] = field(default_factory=list)
    observer: str | None = None       # the seat this log was copied from (named draws)
    first_player: str | None = None
    winner: str | None = None
    turns: list[Turn] = field(default_factory=list)
    mulligans: dict = field(default_factory=dict)     # player -> count

    def events(self):
        for t in self.turns:
            for e in t.events:
                yield from e.walk()

    @property
    def turn_count(self) -> int:
        return sum(1 for t in self.turns if t.player is not None)


# --------------------------------------------------------------------------- #
# Player discovery
# --------------------------------------------------------------------------- #

# Patterns whose subject is unambiguously a player name. "<name>'s Turn" is the
# workhorse: it appears in every log, many times, and its subject can't be a card.
_PLAYER_HINTS = (
    re.compile(r"^(.+?)'s Turn\s*$"),
    re.compile(r"^(.+?) chose (?:heads|tails) for the opening coin flip\.$"),
    re.compile(r"^(.+?) won the coin toss\.$"),
    re.compile(r"^(.+?) drew 7 cards for the opening hand\.$"),
    re.compile(r"^(.+?) decided to go (?:first|second)\.$"),
    re.compile(r"^(.+?) ended their turn\.$"),
    re.compile(r"^(.+?) took a mulligan\.$"),
)


# Fallback discovery, used only when the hints above don't produce two seats — which
# happens on a paste that starts mid-game, where one player may never get a turn header.
# These lean on a regularity the whole corpus confirms: a TCG Live handle is ONE TOKEN.
# 53 distinct handles across 53 real logs, not one containing a space ('DCs-Sister',
# '3003rawr', 'Kakuzø'). So a single token in subject position, followed by a verb only
# a player takes, is a player.
_PLAYER_FALLBACKS = (
    re.compile(r"^(\S+) (?:drew|played|discarded|attached|evolved|retreated|took|"
               r"shuffled|moved|put|flipped|chose|ended)\b"),
    re.compile(r"^(\S+)'s .+? (?:was switched|was Knocked Out|is now|is no longer|used )"),
    re.compile(r"\bon (\S+)'s "),
)

# Sentence-initial words of NON-player log lines, which would otherwise be captured as
# a one-token subject ("Cards revealed from Mulligan 1", "Damage breakdown:").
_NOT_A_HANDLE = {"cards", "damage", "total", "base", "a", "the", "opponent", "resistance",
                 "weakness", "setup", "pokemon", "pokémon", "1", "2", "3", "4", "5", "6"}


def find_players(lines: list[str]) -> list[str]:
    """The two player names, most-frequently-attested first.

    Discovery is by FREQUENCY over several unambiguous patterns rather than by taking
    the first match, because a log can be pasted starting mid-game (no Setup block, no
    coin flip) and because a truncated paste may attest one seat only. Returning fewer
    than two names is a legitimate outcome; the caller decides whether that's fatal.

    THIS RUNS BEFORE ANY EVENT PARSING AND EVERYTHING DEPENDS ON IT. Every possessive
    pattern in the grammar is anchored on a known handle, so a seat missed here doesn't
    degrade gracefully — every line naming that player silently falls through to
    'unparsed'.
    """
    counts: dict[str, int] = {}
    texts = [_split_marker(raw)[2] for raw in lines]
    for text in texts:
        for pat in _PLAYER_HINTS:
            m = pat.match(text)
            if m:
                name = m.group(1).strip()
                # Guard against a possessive card name slipping in via a mis-copied
                # line: real player names never contain these.
                if name and " to the " not in name:
                    counts[name] = counts.get(name, 0) + 1
                break

    if len(counts) < 2:
        # Corroboration threshold: a fallback candidate must appear at least twice.
        # One sighting is as likely to be a mis-parse as a player.
        extra: dict[str, int] = {}
        for text in texts:
            for pat in _PLAYER_FALLBACKS:
                m = pat.search(text)
                if m:
                    name = m.group(1).strip()
                    if name and name not in counts and _fold(name) not in _NOT_A_HANDLE:
                        extra[name] = extra.get(name, 0) + 1
        for name, n in sorted(extra.items(), key=lambda kv: (-kv[1], kv[0])):
            if n >= 2 and len(counts) < 2:
                counts[name] = 0        # attested, but ranked below a hinted seat

    return [n for n, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:2]


# --------------------------------------------------------------------------- #
# Event grammar
# --------------------------------------------------------------------------- #
#
# Each entry is (kind, template, field_names). The template is a regex written against
# a line with player names already substituted: {P} matches either player and captures
# the name. Order matters — the first match wins, so specific forms precede general
# ones (an attack WITH a target must be tried before the bare "used <move>." form).

_GRAMMAR: list[tuple[str, str, tuple[str, ...]]] = [
    # --- structural ------------------------------------------------------- #
    ("turn_header",   r"{P}'s Turn", ("player",)),
    ("checkup",       r"Pok[eé]mon Checkup", ()),
    ("setup_header",  r"Setup", ()),

    # --- pre-game --------------------------------------------------------- #
    ("open_flip",     r"{P} chose (heads|tails) for the opening coin flip\.", ("player", "face")),
    ("coin_toss",     r"{P} won the coin toss\.", ("player",)),
    ("go_order",      r"{P} decided to go (first|second)\.", ("player", "order")),
    ("opening_hand",  r"{P} drew 7 cards for the opening hand\.", ("player",)),
    ("mulligan",      r"{P} took a mulligan\.", ("player",)),
    ("mulligan_n",    r"{P} took (\d+) mulligans\.", ("player", "n")),
    ("mulligan_head", r"Cards revealed from Mulligan (\d+)", ("n",)),

    # --- attacks / abilities ---------------------------------------------- #
    # "X's <mon> used <move> on Y's <mon> for N damage." — with an OPTIONAL Weakness or
    # Resistance tail, which the client appends as a SECOND SENTENCE and sometimes
    # leaves unterminated:
    #   "... for 360 damage. Goatest1's Bloodmoon Ursaluna ex took 180 more damage
    #    because of Fighting Weakness"
    #   "... for 160 damage. Goatest1's Munkidori took -30 less damage because of
    #    Fighting Resistance."
    # The figure BEFORE the tail is the raw damage; the tail is the adjustment. Both
    # must be captured or the recorded damage is wrong by exactly that adjustment —
    # and note the Resistance amount is written already-negated ("-30 less").
    ("attack",        r"{P}'s (.+?) used (.+?) on {P2}'s (.+?) for (\d+) damage\."
                      r"(?: .+? took (-?\d+) (?:more|less) damage because of "
                      r"(\w+) (Weakness|Resistance)\.?)?",
                      ("player", "source", "move", "target_player", "target", "damage",
                       "adjust", "adjust_type", "adjust_kind")),
    # "X's <mon> used <move> on Y's <mon>." (effect attack, no damage number)
    ("attack",        r"{P}'s (.+?) used (.+?) on {P2}'s (.+?)\.",
                      ("player", "source", "move", "target_player", "target")),
    # "X's <mon> used <move>." — an attack that hit nothing, OR an Ability. The log
    # uses one verb for both; `resolve` disambiguates against the card's real text.
    ("used",          r"{P}'s (.+?) used (.+?)\.", ("player", "source", "move")),

    # --- board actions ----------------------------------------------------- #
    ("play_active",   r"{P} played (.+?) to the Active Spot\.", ("player", "card")),
    ("play_bench",    r"{P} played (.+?) to the Bench\.", ("player", "card")),
    ("play_stadium",  r"{P} played (.+?) to the Stadium spot\.", ("player", "card")),
    ("evolve",        r"{P} evolved (.+?) to (.+?) (?:in the Active Spot|on the Bench)\.",
                      ("player", "from_card", "card")),
    ("attach",        r"{P} attached (.+?) to (.+?) (?:in the Active Spot|on the Bench)\.",
                      ("player", "card", "target")),
    ("retreat",       r"{P} retreated (.+?) to the Bench\.", ("player", "card")),
    ("promote",       r"{P}'s (.+?) is now in the Active Spot\.", ("player", "card")),
    # Switch (Escape Rope, Boss's Orders, ...). NOTE both sides can name the SAME
    # card — "N's Zoroark ex was switched with N's Zoroark ex" is two copies, not a
    # no-op, so this must stay a two-field event and not be collapsed.
    ("switch",        r"{P}'s (.+?) was switched with {P2}'s (.+?) to become the Active Pok[eé]mon\.",
                      ("player", "card", "other_player", "other_card")),
    ("condition",     r"{P}'s (.+?) is now (Poisoned|Confused|Asleep|Paralyzed|Burned)\.",
                      ("player", "card", "condition")),
    ("condition_end", r"{P}'s (.+?) is no longer (Poisoned|Confused|Asleep|Paralyzed|Burned)\.",
                      ("player", "card", "condition")),
    ("play_trainer",  r"{P} played (.+?)\.", ("player", "card")),

    # --- damage / KO ------------------------------------------------------- #
    ("knockout",      r"{P}'s (.+?) was Knocked Out!", ("player", "card")),
    ("took_damage",   r"{P}'s (.+?) took (\d+) damage\.", ("player", "card", "damage")),
    ("healed",        r"{P}'s (.+?) healed (\d+) damage\.", ("player", "card", "damage")),
    # Poison/Burn counters carry a reason clause naming the Condition.
    ("damage_counters",
                      r"(\d+) damage counters? (?:was|were) placed on {P}'s (.+?)"
                      r"(?: for the Special Condition (\w+))?\.",
                      ("n", "player", "card", "condition")),
    # DO NOT TRUST `target_player` HERE. The client names the wrong owner in 17 of the 29
    # occurrences across the corpus — in both directions, so it isn't a convention you can
    # invert. Phantom Dive's bench counters are logged as "Alamo789 put 6 damage counters
    # on Alamo789's Metang" when the Metang is the OPPONENT's (proved by the KO on the
    # next line: 40 existing damage + 60 = its exact 100 HP). The field is captured as
    # written, because discarding it would hide the discrepancy; resolve the real target
    # from board state. See docs/TCGLIVE_LOG_FIDELITY.md, Finding 3.
    ("put_counters",  r"{P} put (a|\d+) damage counters? on {P2}'s (.+?)\.",
                      ("player", "n", "target_player", "card")),
    ("discard_from",  r"(\d+) cards? (?:was|were) discarded from {P}'s (.+?)\.",
                      ("n", "player", "card")),
    # A NAMED attachment leaving a Pokémon (Energy knocked off by Enhanced Hammer, a
    # Tool discarded, or the KO'd Pokémon's own parts). Distinct from `discard_from`,
    # which is the anonymous count printed when a Pokémon is Knocked Out.
    ("detach",        r"(.+?) was discarded from {P}'s (.+?)\.",
                      ("card", "player", "from_card")),
    ("prevented",     r"Damage to (.+?) was prevented\.", ("card",)),
    # Both owners are captured, including the destination's — it is the field most likely
    # to be wrong (see the put_counters note above and Finding 3), and a discrepancy you
    # don't capture is a discrepancy you can't detect.
    ("move_counters", r"{P} moved (\d+) damage counters? from {P2}'s (.+?) to {P2}'s (.+?)\.",
                      ("player", "n", "from_player", "from_card", "to_player", "card")),
    ("damage_head",   r"Damage breakdown:", ()),
    # Components: "Base damage: 90 damage", "Weakness: 60 damage",
    # "Resistance to Grass: -30 damage", "(Attack) Protect Charge: -30 damage".
    ("damage_part",   r"(.+?): (-?\d+) damage", ("label", "amount")),

    # --- cards / zones ----------------------------------------------------- #
    # ORDER IS LOAD-BEARING HERE. The named forms end in `(.+?)\.`, which happily
    # matches "2 cards." and "Beldum and played it to the Bench." — so every numeric
    # and compound form MUST be tried first. Getting this backwards is silent: the
    # line still "parses", it just files a quantity as a card name.
    ("draw_n_and_bench",
                      r"{P} drew (\d+) cards? and played them to the Bench\.",
                      ("player", "n")),
    ("draw_named_bench",
                      r"{P} drew (.+?) and played it to the Bench\.", ("player", "card")),
    ("draw_n_and",    r"{P} drew (\d+) cards? and (.+?)\.", ("player", "n", "then")),
    # The mulligan compensation draw, phrased as a reason clause — must precede the
    # bare `draw_named`, which would otherwise file the whole clause as a card name.
    ("mulligan_draw", r"{P} drew (\d+) more cards? because {P2} took at least "
                      r"(\d+) mulligans?\.?", ("player", "n", "other_player", "mulligans")),
    ("draw_n",        r"{P} drew (\d+) cards?\.", ("player", "n")),
    # An UNNAMED draw is the hidden-information case — it's how the log renders the
    # seat you can't see. Keeping it distinct from `draw_named` is the whole point:
    # anything reasoning about what a player knew must be able to tell them apart.
    ("draw_hidden",   r"{P} drew a card\.", ("player",)),
    ("draw_named",    r"{P} drew (.+?)\.", ("player", "card")),          # own seat: card named
    ("drawn_summary", r"(\d+) drawn cards?\.", ("n",)),
    ("add_hidden",    r"A card was added to {P}'s hand\.", ("player",)),
    ("add_named",     r"(.+?) was added to {P}'s hand\.", ("card", "player")),
    ("discard_n",     r"{P} discarded (\d+) cards?\.", ("player", "n")),
    ("discard_named", r"{P} discarded (.+?)\.", ("player", "card")),
    ("shuffle_deck",  r"{P} shuffled their (?:deck|cards|hand)\.", ("player",)),
    ("shuffle_in",    r"{P} shuffled (\d+) cards? into their deck\.", ("player", "n")),
    ("shuffle_named_in",
                      r"{P} shuffled (.+?) into their deck\.", ("player", "card")),
    ("reveal_n",      r"{P} revealed (\d+) cards?\.", ("player", "n")),
    ("top_of_deck",   r"{P} put a card on top of their deck\.", ("player",)),
    ("top_of_deck_named",
                      r"{P} put (.+?) on top of their deck\.", ("player", "card")),
    ("bottom_of_deck", r"{P} put (\d+) cards? on the bottom of their deck\.",
                      ("player", "n")),
    ("move_zone",     r"{P} moved {P2}'s (\d+ cards?|.+?) to (?:their|the) (hand|deck|discard pile)\.",
                      ("player", "owner", "what", "zone")),
    ("prize_one",     r"{P} took a Prize card\.", ("player",)),
    ("prize_n",       r"{P} took (\d+) Prize cards?\.", ("player", "n")),
    ("activated",     r"(.+?) was activated\.", ("card",)),
    ("coin_flip",     r"{P} flipped a coin and it landed on (heads|tails)\.",
                      ("player", "face")),
    ("coin_flips",    r"{P} flipped (\d+) coins?, and (\d+) landed on (heads|tails)\.",
                      ("player", "n", "hits", "face")),
    ("timeout",       r"{P} didn't take an action in time\.", ("player",)),
    ("end_turn",      r"{P} ended their turn\.", ("player",)),
    # Last of the {P}-prefixed forms: "<player> chose <anything>" would otherwise
    # shadow the specific choices above.
    ("chose",         r"{P} chose (.+?)\.?", ("player", "choice")),

    # --- result ------------------------------------------------------------ #
    ("win",           r"(?:.*\. )?{P} wins\.", ("player",)),
]

# Kinds whose capture is a card name we should resolve against the pool. The value is
# the tuple of field keys holding card names.
_CARD_FIELDS = {
    "play_active": ("card",), "play_bench": ("card",), "play_trainer": ("card",),
    "play_stadium": ("card",),
    "evolve": ("from_card", "card"), "attach": ("card", "target"),
    "retreat": ("card",), "promote": ("card",), "knockout": ("card",),
    "took_damage": ("card",), "healed": ("card",), "damage_counters": ("card",),
    "discard_from": ("card",), "draw_named": ("card",), "add_named": ("card",),
    "discard_named": ("card",), "activated": ("card",),
    "attack": ("source", "target"), "used": ("source",),
    "switch": ("card", "other_card"), "condition": ("card",),
    "detach": ("card", "from_card"), "prevented": ("card",),
    "move_counters": ("card", "from_card"), "draw_named_bench": ("card",),
    "condition_end": ("card",), "put_counters": ("card",),
    "shuffle_named_in": ("card",), "top_of_deck_named": ("card",),
}


def _compile(players: list[str]) -> list[tuple[str, re.Pattern, tuple[str, ...]]]:
    """Bake the two player names into the grammar. Names are regex-escaped and joined
    into one alternation, so a name containing regex metacharacters (or a typographic
    character like 'Kakuzø') is matched literally."""
    alt = "|".join(re.escape(p) for p in players) or r"(?!)"   # (?!) = match nothing
    out = []
    for kind, tmpl, fields in _GRAMMAR:
        pat = tmpl.replace("{P2}", f"({alt})").replace("{P}", f"({alt})")
        out.append((kind, re.compile("^" + pat + "$"), fields))
    return out


def _parse_line(text: str, grammar) -> Event:
    for kind, pat, names in grammar:
        m = pat.match(text)
        if not m:
            continue
        vals = dict(zip(names, (g.strip() if isinstance(g, str) else g
                                for g in m.groups())))
        actor = vals.get("player")
        # Optional groups come back as None; only convert what actually matched, or a
        # missing Weakness tail would crash every ordinary attack line.
        for key in ("n", "damage", "amount", "adjust", "hits", "mulligans"):
            if vals.get(key) is not None:
                # The client writes a count of one as the word: "put a damage counter on".
                vals[key] = 1 if vals[key] == "a" else int(vals[key])
        return Event(kind=kind, actor=actor, raw=text, fields=vals)
    return Event(kind="unparsed", raw=text)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def parse_log(text: str) -> GameLog:
    """Parse one battle log into a `GameLog`.

    Nesting: a line with a list marker attaches to the nearest preceding line at a
    shallower depth. Depth is (marker, indent) run through the per-log dialect sniff,
    because '•' is a CHILD in one dialect and a GRANDCHILD in the other.
    """
    text = normalize(text)
    raw_lines = [ln for ln in text.splitlines()]
    players = find_players(raw_lines)
    grammar = _compile(players)

    # Dialect sniff: if any '-' marker is present, this is the dash dialect, where
    # '-' is depth 1 and '•' is depth 2. Otherwise '•' carries both depths and we
    # separate them by indent (indented '•' = depth 1, flush '•' = depth 2).
    dash_dialect = any(_split_marker(ln)[0] == "-" for ln in raw_lines)

    def depth_of(marker: str, indent: int) -> int:
        if not marker:
            return 0
        if dash_dialect:
            return 1 if marker == "-" else 2
        return 1 if indent > 0 else 2

    log = GameLog(players=players)
    setup = Turn(number=0, player=None)
    log.turns.append(setup)
    current = setup
    stack: list[tuple[int, Event]] = []      # (depth, event) for open parents
    turn_no = 0

    for raw in raw_lines:
        if not raw.strip():
            continue
        marker, indent, body = _split_marker(raw)
        depth = depth_of(marker, indent)

        # A grandchild that is a bare comma-separated list of card names is a REVEAL,
        # not a sentence. Distinguish structurally: reveals have no trailing period and
        # don't match "<label>: <n> damage".
        if depth == 2 and not body.endswith(".") and not re.match(r"^.+: -?\d+ damage$", body):
            ev = Event(kind="reveal", raw=body,
                       fields={"cards": [c.strip() for c in body.split(",") if c.strip()]})
        else:
            ev = _parse_line(body, grammar)

        if ev.kind == "turn_header":
            turn_no += 1
            current = Turn(number=turn_no, player=ev.fields.get("player"))
            log.turns.append(current)
            stack = []
            continue

        if ev.kind == "go_order":
            # "X decided to go second" names the OTHER player as first.
            who, order = ev.fields.get("player"), ev.fields.get("order")
            if order == "first":
                log.first_player = who
            else:
                others = [p for p in players if p != who]
                log.first_player = others[0] if others else None
        elif ev.kind == "win":
            log.winner = ev.fields.get("player")
        elif ev.kind == "mulligan":
            who = ev.fields.get("player")
            log.mulligans[who] = log.mulligans.get(who, 0) + 1

        while stack and stack[-1][0] >= depth:
            stack.pop()
        if depth == 0 or not stack:
            current.events.append(ev)
        else:
            stack[-1][1].children.append(ev)
        stack.append((depth, ev))

    # The observer is the seat whose draws are NAMED — the log was copied from that
    # client, so only that player's private information is visible.
    named = {p: 0 for p in players}
    for ev in log.events():
        if ev.kind == "draw_named" and ev.actor in named:
            named[ev.actor] += 1
    if named:
        best = max(named, key=lambda p: named[p])
        log.observer = best if named[best] else None
    return log


# --------------------------------------------------------------------------- #
# Card resolution + coverage
# --------------------------------------------------------------------------- #

@dataclass
class Coverage:
    """How much of a log (or corpus) this parser actually understands."""
    lines: int = 0
    parsed: int = 0
    unparsed: list[str] = field(default_factory=list)
    kinds: dict = field(default_factory=dict)
    cards_seen: set = field(default_factory=set)
    cards_missing: set = field(default_factory=set)
    moves_unknown: set = field(default_factory=set)      # (card, move) not in card text
    abilities: set = field(default_factory=set)          # (card, move) resolved as Ability
    attacks: set = field(default_factory=set)            # (card, move) resolved as Attack

    @property
    def line_pct(self) -> float:
        return 100.0 * self.parsed / self.lines if self.lines else 0.0

    @property
    def card_pct(self) -> float:
        n = len(self.cards_seen)
        return 100.0 * (n - len(self.cards_missing)) / n if n else 0.0


# Log phrasings that name something OTHER than a card, which would otherwise be
# resolved and reported as a missing card.
_NOT_CARDS = {
    "a card", "cards", "their hand", "the top card of their deck",
}


def _resolve_card(name: str, by_fold: dict) -> str | None:
    """Canonical pool name for a log's card string, or None."""
    name = name.strip()
    if not name or _fold(name) in _NOT_CARDS:
        return None
    for cand in _candidates(name):
        hit = by_fold.get(_fold(cand))
        if hit:
            return hit
    return None


def analyse(log: GameLog, db, cov: Coverage | None = None) -> Coverage:
    """Walk a parsed log and record what resolved and what didn't.

    The `used` disambiguation is the interesting part: TCG Live writes one verb for
    attacks and Abilities alike, so we ask the CARD what it owns. A name that is
    neither an attack nor an Ability of that card is recorded in `moves_unknown` —
    that is a genuine fidelity signal (wrong card print, or missing card data), not a
    parser complaint.
    """
    cov = cov or Coverage()
    by_fold = {_fold(n): n for n in db.names()}

    for ev in log.events():
        cov.lines += 1
        if ev.kind == "unparsed":
            cov.unparsed.append(ev.raw)
            continue
        cov.parsed += 1
        cov.kinds[ev.kind] = cov.kinds.get(ev.kind, 0) + 1

        names = []
        if ev.kind == "reveal":
            names = ev.fields.get("cards", [])
        else:
            for key in _CARD_FIELDS.get(ev.kind, ()):
                if ev.fields.get(key):
                    names.append(ev.fields[key])

        canon_first = None
        for i, nm in enumerate(names):
            if _fold(nm) in _NOT_CARDS:
                continue
            cov.cards_seen.add(nm)
            canon = _resolve_card(nm, by_fold)
            if canon is None:
                cov.cards_missing.add(nm)
            elif i == 0:
                canon_first = canon

        move = ev.fields.get("move")
        if move and canon_first:
            card = db.get(canon_first)
            atk = {_fold(a.name) for a in getattr(card, "attacks", []) or []}
            abl = {_fold(a.name) for a in getattr(card, "abilities", []) or []}
            key = (canon_first, move)
            if _fold(move) in atk:
                cov.attacks.add(key)
            elif _fold(move) in abl:
                cov.abilities.add(key)
            else:
                cov.moves_unknown.add(key)
    return cov


def format_coverage(cov: Coverage, top_unparsed: int = 25) -> str:
    """A fidelity report: what the parser understood, and precisely what it didn't."""
    out = [
        f"lines           {cov.lines}",
        f"parsed          {cov.parsed} ({cov.line_pct:.1f}%)",
        f"distinct cards  {len(cov.cards_seen)} seen, "
        f"{len(cov.cards_missing)} unresolved ({cov.card_pct:.1f}% resolved)",
        f"moves           {len(cov.attacks)} attacks, {len(cov.abilities)} abilities, "
        f"{len(cov.moves_unknown)} unknown",
    ]
    if cov.kinds:
        out.append("\nevent kinds:")
        for k, v in sorted(cov.kinds.items(), key=lambda kv: -kv[1]):
            out.append(f"  {v:6d}  {k}")
    if cov.cards_missing:
        out.append(f"\nunresolved card names ({len(cov.cards_missing)}):")
        for n in sorted(cov.cards_missing)[:40]:
            out.append(f"  - {n}")
    if cov.moves_unknown:
        out.append(f"\nmoves not found on the resolved card ({len(cov.moves_unknown)}):")
        for c, m in sorted(cov.moves_unknown)[:40]:
            out.append(f"  - {c}: {m}")
    if cov.unparsed:
        counts: dict[str, int] = {}
        for line in cov.unparsed:
            counts[line] = counts.get(line, 0) + 1
        out.append(f"\nunparsed lines ({len(cov.unparsed)} total, "
                   f"{len(counts)} distinct):")
        for line, n in sorted(counts.items(), key=lambda kv: -kv[1])[:top_unparsed]:
            out.append(f"  {n:4d}x  {line}")
    return "\n".join(out)
