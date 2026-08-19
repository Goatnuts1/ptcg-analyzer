#!/usr/bin/env python3
"""
test_tcglive_log.py — the TCG Live BATTLE LOG parser (src/importers/tcglive_log.py).

Fixtures here are SYNTHETIC, hand-written in the client's exact phrasing. Real captures
name real opponents, and their ladder handles have no business in a public repo — so the
corpus stays out of the tree and the tests assert against reconstructions of the shapes
it taught us. Every fixture line below is a form actually observed in real logs.

The regressions this file exists to catch are all ORDERING and BOUNDARY bugs, because
that is where this parser fails silently rather than loudly: a greedy pattern that eats
"2 cards." as a card name still "parses" the line.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.cards import CardDB
from src.importers.tcglive_log import (
    parse_log, analyse, Coverage, find_players, normalize,
)

fails = 0
def check(c, m):
    global fails
    print(("  ok  " if c else "  FAIL") + " " + m)
    if not c:
        fails += 1


def kinds(log, kind):
    return [e for e in log.events() if e.kind == kind]


# --------------------------------------------------------------------------- #
# Fixture A — dash dialect, the common paste
# --------------------------------------------------------------------------- #
DASH = """Setup
Alpha chose tails for the opening coin flip.
Bravo won the coin toss.
Bravo decided to go first.
Alpha drew 7 cards for the opening hand.
- 7 drawn cards.
   • Crustle, Basic Darkness Energy, Dwebble, Boss's Orders, Dwebble
Alpha played Dwebble to the Active Spot.
Bravo played Staryu to the Active Spot.

Bravo's Turn
Bravo drew a card.
Bravo attached Basic Water Energy to Staryu in the Active Spot.
Bravo ended their turn.

Alpha's Turn
Alpha drew Lillie's Determination.
Alpha drew 2 cards.
Alpha's Dwebble used Ascension.
- Alpha evolved Dwebble to Crustle in the Active Spot.
- Alpha shuffled their deck.
Alpha played Lillie's Determination.
Alpha's Crustle used Superb Scissors on Bravo’s Staryu for 60 damage.
Bravo's Staryu was Knocked Out!
- 1 card was discarded from Bravo's Staryu.
Alpha took a Prize card.
Bravo took all of their Prize cards. Alpha wins.
"""

print("== dash dialect: structure ==")
a = parse_log(DASH)
check(sorted(a.players) == ["Alpha", "Bravo"], f"both players found: {a.players}")
check(a.first_player == "Bravo", f"first player = Bravo (got {a.first_player})")
check(a.winner == "Alpha", f"winner = Alpha (got {a.winner})")
check(a.turn_count == 2, f"2 turns (got {a.turn_count})")
check(a.observer == "Alpha", f"observer = Alpha, the seat with named draws (got {a.observer})")

print("\n== nesting ==")
asc = kinds(a, "used")
check(len(asc) == 1 and asc[0].fields["move"] == "Ascension", "Ascension parsed as a 'used' event")
check([c.kind for c in asc[0].children] == ["evolve", "shuffle_deck"],
      f"sub-lines nest under it: {[c.kind for c in asc[0].children]}")
ko = kinds(a, "knockout")
check(len(ko) == 1 and [c.kind for c in ko[0].children] == ["discard_from"],
      "the KO's discard count nests under the KO")

print("\n== the reveal list is cards, not a sentence ==")
rev = kinds(a, "reveal")
check(len(rev) == 1, f"one reveal (got {len(rev)})")
check(rev[0].fields["cards"] == ["Crustle", "Basic Darkness Energy", "Dwebble",
                                 "Boss's Orders", "Dwebble"],
      f"5 card names split out: {rev[0].fields['cards']}")

print("\n== numeric forms are not filed as card names ==")
dn = kinds(a, "draw_n")
check(len(dn) == 1 and dn[0].fields["n"] == 2, "'drew 2 cards.' -> draw_n with n=2")
named = {e.fields["card"] for e in kinds(a, "draw_named")}
check(named == {"Lillie's Determination"},
      f"only the real card is a draw_named: {named}")
check(not any("2 cards" in str(e.fields.get("card", "")) for e in a.events()),
      "no event filed a quantity as a card name")

print("\n== possessive boundaries ==")
atk = kinds(a, "attack")
check(len(atk) == 1, f"one attack (got {len(atk)})")
if atk:
    f = atk[0].fields
    check(f["source"] == "Crustle" and f["target"] == "Staryu",
          f"source/target split correctly: {f['source']} -> {f['target']}")
    check(f["target_player"] == "Bravo", f"target owner = Bravo (got {f['target_player']})")
    check(f["damage"] == 60, f"damage = 60 (got {f['damage']})")
check(kinds(a, "unparsed") == [], f"nothing unparsed: {[e.raw for e in kinds(a, 'unparsed')]}")


# --------------------------------------------------------------------------- #
# Fixture B — bullet dialect, same game
# --------------------------------------------------------------------------- #
# Identical events, the OTHER indentation style: '•' is the child marker here and a
# flush '•' is the grandchild. If the dialect sniff regresses, the two parses diverge.
BULLET = """Setup
Alpha chose tails for the opening coin flip.
Bravo won the coin toss.
Bravo decided to go first.
Alpha drew 7 cards for the opening hand.
    •    7 drawn cards.
• Crustle, Basic Darkness Energy, Dwebble, Boss's Orders, Dwebble
Alpha played Dwebble to the Active Spot.

Alpha's Turn
Alpha drew Lillie's Determination.
Alpha's Dwebble used Ascension.
    •    Alpha evolved Dwebble to Crustle in the Active Spot.
    •    Alpha shuffled their deck.
"""

print("\n== bullet dialect parses to the same shape ==")
b = parse_log(BULLET)
check(sorted(b.players) == ["Alpha", "Bravo"], f"players found: {b.players}")
basc = kinds(b, "used")
check(len(basc) == 1 and [c.kind for c in basc[0].children] == ["evolve", "shuffle_deck"],
      f"children nest the same way: {[c.kind for c in basc[0].children] if basc else None}")
brev = kinds(b, "reveal")
check(len(brev) == 1 and len(brev[0].fields["cards"]) == 5,
      "the flush-bullet card list is still a reveal")
check(kinds(b, "unparsed") == [], "nothing unparsed in the bullet dialect")


# --------------------------------------------------------------------------- #
# Fixture C — the awkward real-world lines
# --------------------------------------------------------------------------- #
EDGE = """Charlie's Turn
Charlie drew a card.
Charlie's Mega Lucario ex used Aura Jab on Delta’s Munkidori for 160 damage. Delta's Munkidori took -30 less damage because of Fighting Resistance.
Charlie's Tyrantrum used Wreak Havoc on Delta’s Bloodmoon Ursaluna ex for 360 damage. Delta's Bloodmoon Ursaluna ex took 180 more damage because of Fighting Weakness
Delta drew 1 more card because Delta took at least 1 mulligan.
Delta drew 3 cards and played them to the Bench.
Delta drew Beldum and played it to the Bench.
Delta played Academy at Night to the Stadium spot.
Delta's Genesect ex was switched with Delta's Metang to become the Active Pokemon.
1 damage counter was placed on Delta's Metang for the Special Condition Poisoned.
Basic Metal Energy was discarded from Delta's Beldum.
Delta's N's Zoroark ex used Night Joker on Charlie’s N's Zoroark ex for 60 damage.
Charlie moved 3 damage counters from Charlie's Crustle to Charlie's Mega Sharpedo ex.
Delta discarded 2 cards.
Delta discarded Annihilape.
"""

print("\n== a mid-game paste finds the seat with no turn header ==")
c = parse_log(EDGE)
# Delta never gets a "Delta's Turn" header here — the paste starts mid-game. Every
# possessive pattern is anchored on a known handle, so if the fallback discovery
# regresses, Delta's ten lines don't degrade: they vanish into 'unparsed'.
check(sorted(c.players) == ["Charlie", "Delta"],
      f"both seats found without a header for one of them: {c.players}")
check(find_players(["Zulu played Ultra Ball.", "Yankee's Turn", "Yankee drew a card."])
      == ["Yankee"],
      "a single-sighting name is NOT promoted to a player (corroboration threshold)")

print("\n== weakness / resistance tails ==")
atks = kinds(c, "attack")
check(len(atks) == 3, f"3 attacks parsed (got {len(atks)})")
res = [e for e in atks if e.fields.get("adjust_kind") == "Resistance"]
check(len(res) == 1 and res[0].fields["damage"] == 160 and res[0].fields["adjust"] == -30,
      "Resistance tail: raw damage 160 kept separate from the -30 adjustment")
wk = [e for e in atks if e.fields.get("adjust_kind") == "Weakness"]
check(len(wk) == 1 and wk[0].fields["damage"] == 360 and wk[0].fields["adjust"] == 180,
      "Weakness tail (unterminated sentence): 360 raw, +180 adjustment")
check(res and res[0].fields["target"] == "Munkidori",
      f"the tail is not swallowed into the target name: {res[0].fields['target'] if res else None}")

print("\n== a card name that contains a possessive ==")
zo = [e for e in atks if e.fields["move"] == "Night Joker"]
check(len(zo) == 1 and zo[0].fields["source"] == "N's Zoroark ex"
      and zo[0].fields["target"] == "N's Zoroark ex",
      "\"N's Zoroark ex\" survives on both sides of the possessive split")

print("\n== compound and reason-clause draws ==")
check(len(kinds(c, "mulligan_draw")) == 1, "'drew 1 more card because ... mulligan' is its own kind")
check(len(kinds(c, "draw_n_and_bench")) == 1, "'drew 3 cards and played them to the Bench'")
dnb = kinds(c, "draw_named_bench")
check(len(dnb) == 1 and dnb[0].fields["card"] == "Beldum",
      "'drew Beldum and played it to the Bench' -> card is just 'Beldum'")
check(not kinds(c, "draw_named"), "none of the three leaked into the bare draw_named form")

print("\n== the rest of the awkward set ==")
check(len(kinds(c, "play_stadium")) == 1, "Stadium play is not a generic play_trainer")
sw = kinds(c, "switch")
check(len(sw) == 1 and sw[0].fields["card"] == "Genesect ex"
      and sw[0].fields["other_card"] == "Metang", "switch keeps both sides")
dc = kinds(c, "damage_counters")
check(len(dc) == 1 and dc[0].fields["card"] == "Metang"
      and dc[0].fields["condition"] == "Poisoned",
      "the Special Condition clause is a field, not part of the card name")
det = kinds(c, "detach")
check(len(det) == 1 and det[0].fields["card"] == "Basic Metal Energy",
      "a named attachment leaving a Pokemon is a detach, not a KO discard")
check(len(kinds(c, "move_counters")) == 1, "damage-counter movement parsed")
check(len(kinds(c, "discard_n")) == 1 and len(kinds(c, "discard_named")) == 1,
      "discard: numeric and named forms both land in the right kind")
check(kinds(c, "unparsed") == [], f"nothing unparsed: {[e.raw for e in kinds(c, 'unparsed')]}")


# --------------------------------------------------------------------------- #
# Normalisation and player discovery
# --------------------------------------------------------------------------- #
print("\n== the damage-counter owner label is preserved, not silently 'corrected' ==")
# Real logs name the wrong owner on this event most of the time (docs/TCGLIVE_LOG_FIDELITY
# Finding 3). The parser's job is to surface the discrepancy, so actor and labelled owner
# must stay separately readable — a downstream harness resolves the real target from board
# state. If someone "fixes" this by dropping or rewriting target_player, this fails.
pc = parse_log("Kilo's Turn\nKilo put 6 damage counters on Kilo's Metang.\n"
               "Kilo ended their turn.\n\nLima's Turn\nLima ended their turn.\n")
ev = [e for e in pc.events() if e.kind == "put_counters"]
check(len(ev) == 1 and ev[0].actor == "Kilo" and ev[0].fields["target_player"] == "Kilo"
      and ev[0].fields["n"] == 6,
      "actor and labelled owner both retained verbatim, count parsed")
sing = parse_log("Kilo's Turn\nKilo put a damage counter on Kilo's Metang.\n"
                 "Kilo ended their turn.\n\nLima's Turn\nLima ended their turn.\n")
sev = [e for e in sing.events() if e.kind == "put_counters"]
check(len(sev) == 1 and sev[0].fields["n"] == 1,
      "the singular 'a damage counter' form parses as n=1")

print("\n== normalisation ==")
check("'" in normalize("Goatest1’s Genesect ex") and "’" not in normalize("a’b"),
      "typographic apostrophes fold to ASCII")
check("Pokémon" in normalize("Pokémon Checkup"),
      "accents are NOT stripped (card text keeps them)")

print("\n== player discovery survives a partial paste ==")
mid = parse_log("Echo's Turn\nEcho drew a card.\nEcho ended their turn.\n")
check(mid.players == ["Echo"], f"a one-seat fragment yields one player, not a crash: {mid.players}")
check(mid.winner is None and mid.first_player is None,
      "no result is claimed when the paste doesn't contain one")


# --------------------------------------------------------------------------- #
# Card resolution + the ability/attack split
# --------------------------------------------------------------------------- #
print("\n== resolution against the live pool ==")
db = CardDB.from_pool()
cov = analyse(a, db)
check(cov.line_pct > 99.0, f"fixture A is fully understood: {cov.line_pct:.1f}%")
check("Crustle" in cov.cards_seen and "Crustle" not in cov.cards_missing,
      "a real card resolves against the pool")

ABIL = """Foxtrot's Turn
Foxtrot's Metang used Metal Maker.
Foxtrot's Crustle used Superb Scissors on Golf’s Staryu for 60 damage.
Foxtrot ended their turn.

Golf's Turn
Golf ended their turn.
"""
cov2 = analyse(parse_log(ABIL), db)
check(("Metang", "Metal Maker") in cov2.abilities,
      f"'used' resolves to an ABILITY when the card owns one: {cov2.abilities}")
check(("Crustle", "Superb Scissors") in cov2.attacks,
      f"and to an ATTACK when it's an attack: {cov2.attacks}")

# The disambiguation must also REPORT a miss rather than quietly guessing. A move that
# belongs to a different print of the same card name is exactly the signal we want.
BAD = """Hotel's Turn
Hotel's Metagross used Metallic Hammer on India’s Beldum for 150 damage.
Hotel ended their turn.

India's Turn
India ended their turn.
"""
cov3 = analyse(parse_log(BAD), db)
check(("Metagross", "Metallic Hammer") in cov3.moves_unknown,
      "a move the pool's print does not have is reported, not silently accepted")

print("\n== coverage accounting ==")
cov4 = Coverage()
analyse(a, db, cov4)
analyse(b, db, cov4)
check(cov4.lines > cov.lines, "a shared Coverage accumulates across logs")
check(cov4.parsed <= cov4.lines, "parsed never exceeds lines")

print("\n" + ("ALL PASS" if not fails else f"{fails} FAILURES"))
sys.exit(1 if fails else 0)
