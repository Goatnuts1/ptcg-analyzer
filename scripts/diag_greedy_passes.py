"""Why do opponents of greedy Crustle end turns without attacking?"""
import random, sys, collections
sys.path.insert(0, '.')  # run from the repo root: python3 scripts/THIS.py OPP_DECK GAMES
from cli import _make_agent
from src.engine.cards import CardDB
from src.engine.decks import load_deck
from src.engine.run import play_game
from src.engine.game import legal_actions
db = CardDB.from_pool('data/standard_pool.json')
opp = sys.argv[1]; N = int(sys.argv[2]); hero = sys.argv[3] if len(sys.argv) > 3 else 'crustle_drew_v11'
C = collections.Counter(); act = collections.Counter()
class Spy:
    def __init__(s, inner): s.inner = inner
    def choose(s, st):
        a = s.inner.choose(st)
        if a.kind in ('pass',) :
            acts = legal_actions(st)
            atk = any(x.kind == 'attack' for x in acts)
            ret = any(x.kind == 'retreat' for x in acts)
            m = st.current.active
            key = ('attack_legal' if atk else 'no_attack_legal', 'retreat_legal' if ret else 'no_retreat',
                   m.card.name if m else None, m.energy_count() if m else 0, 'E_in_hand=%d' % sum(c.is_energy for c in st.current.hand), 'attached' if st.current.energy_attached_this_turn else 'not_attached')
            C[key] += 1
        act[a.kind] += 1
        return a
wins = 0
for i in range(N):
    st = play_game(load_deck(db, hero), load_deck(db, opp),
                   _make_agent('greedy', random.Random(i)), Spy(_make_agent('greedy', random.Random(i + 10**6))),
                   seed=i, db=db, first_player=i % 2)
    wins += st.winner == 0
print('hero wins', wins, '/', N); print(dict(act))
for k, v in C.most_common(25): print(v, k)
