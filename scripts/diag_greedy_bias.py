"""Greedy-bias diagnostic: why does greedy Crustle win ~93%? Parses game logs."""
import random, re, sys, collections
sys.path.insert(0, '.')  # run from the repo root: python3 scripts/THIS.py OPP_DECK GAMES
from cli import _make_agent
from src.engine.cards import CardDB
from src.engine.decks import load_deck
from src.engine.run import play_game
db = CardDB.from_pool('data/standard_pool.json')
opp = sys.argv[1] if len(sys.argv) > 1 else 'dragapult_puebla'
N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
c = collections.Counter(); atk = collections.Counter()
for i in range(N):
    st = play_game(load_deck(db, 'crustle_drew_v11'), load_deck(db, opp),
                   _make_agent('greedy', random.Random(i)), _make_agent('greedy', random.Random(i + 10**6)),
                   seed=i, db=db, first_player=i % 2)
    c['games'] += 1; c['crustle_win'] += st.winner == 0
    p0 = st.players[0]; p1 = st.players[1]
    c['opp_prizes_taken'] += 6 - len(p1.prizes); c['cr_prizes_taken'] += 6 - len(p0.prizes)
    end = st.log[-1] if st.log else ''
    if st.winner == 0:
        c['win_by_' + ('benchout' if 'no Pokémon' in ' '.join(st.log[-3:]) or not p1.active else ('prizes' if len(p0.prizes) == 0 else 'deckout/other'))] += 1
    for line in st.log:
        m = re.match(r'T\d+ P(\d): (.+?) used (.+?) for (\d+)', line)
        if m and m.group(1) == '1':
            atk[(m.group(2), m.group(3), 'zero' if m.group(4) == '0' else 'dmg')] += 1
        if ' P1: ' in line and 'prevented' in line: c['opp_prevented'] += 1
        if ' P1: played Boss' in line: c['opp_boss'] += 1
        if ' P1: played Prime Catcher' in line: c['opp_catcher'] += 1
        if ' P1: ' in line and 'retreat' in line.lower(): c['opp_retreat'] += 1
        if ' P1: ' in line and 'passed' in line.lower(): c['opp_pass'] += 1
for k, v in c.items(): print(f'{k:24s} {v}')
print('--- opponent attacks (attacker, attack, zero/dmg): top 20')
for k, v in atk.most_common(20): print(v, k)
