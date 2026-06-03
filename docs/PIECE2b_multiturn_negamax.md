# Policy Milestone — Piece 2b: Multi-Turn (Negamax) MCTS

**From:** design/algorithm side → **integrate:** CC against current `main` (72b85d5).
**Built against:** the exact `mcts.py` you pasted (post R6→R15→R16). Verified in
sandbox: negamax logic unit-tested, single-ply backward-compatible (plain MCTS still
beats greedy 61%), and 2-ply confirmed to cross the turn boundary and build opponent
nodes (depth 6, 125 opponent-chooser nodes at a real decision point).

## Why this piece

The remaining gap is downstream-payoff: the stadium war stays even because neither
agent can OUT-SEQUENCE it, and Budew item-lock reads 0/120 because its payoff lands
the turn AFTER you promote it. A single-turn tree structurally can't see one turn
ahead. 2b makes the tree span the turn boundary so search can value "lock now → they
whiff next turn." Both named gaps are the same shape; depth + a real opponent is the
lever.

## The two correctness requirements (and how this satisfies them)

You flagged both precisely. Here's how the code handles each:

**1. Negamax backprop (the dangerous one).** A node's stat is stored from the
perspective of the player who CHOSE it (`_Node.chooser`). In `_backprop`, a node the
opponent chose accumulates `1 - value` instead of `value`. So opponent nodes are
optimized FOR the opponent — UCB at each parent maximizes its own actor's value. The
inversion bug (storing `value` everywhere) would model an opponent that helps you win
and report an inflated-but-believable number; `tests/test_mcts_negamax.py` pins this
(a line that's winning-for-me must score ~0 at the opponent's node).

**2. No-leak determinization preserved.** Still ONE `determinize` per iteration at the
root, from the root player's legitimate knowledge. The opponent's in-tree draws come
off THAT determinized deck; diversity comes from re-sampling per iteration. This is
correct PIMC with a multi-ply tree (sometimes "determinized UCT"). It does NOT leak,
because every world is built only from what `me` legitimately knows.

> **Deliberate scope line:** I did NOT add mid-tree re-determinization (full ISMCTS,
> resampling the opponent's hidden draw at each in-tree turn boundary). It's a real
> upgrade but it's **2c**, not 2b — determinized-root multi-ply already gives depth +
> a correct adversary, which is what the Budew/stadium gap needs. Adding mid-tree
> resampling now would be more surface area for subtle leak bugs without being
> required to close the named gap. Do 2b, measure, then decide if 2c earns its risk.

## What changed (targeted edits — full file also provided as `mcts.py`)

You can drop in the whole file or apply these surgically. All localized:

1. **`_Node`** — added a `chooser` slot (the player who made the move into this node):
   ```python
   __slots__ = ("parent", "key", "children", "visits", "wins", "chooser")
   def __init__(self, parent, key, chooser=None):
       ...
       self.chooser = chooser
   ```

2. **`MCTSAgent.__init__`** — new param `search_plies: int = 1` (default preserves v1):
   ```python
   self.search_plies = max(1, search_plies)
   ```

3. **`choose`** — root node `chooser=None`; pass `me` into backprop:
   ```python
   root = _Node(parent=None, key=None, chooser=None)
   ...
   self._backprop(node, value, me)
   ```

4. **`_select_expand`** — descend across the boundary up to `search_plies`
   turn-segments, tagging each child with the actor who chose it:
   ```python
   plies = 0
   while world.phase == Phase.MAIN and plies < self.search_plies:
       actor_here = world.active_index
       by_key = _deduped_legal(world)
       if not by_key: break
       untried = [k for k in by_key if k not in node.children]
       if untried:
           k = self.rng.choice(untried)
           self._apply(world, by_key[k], me)
           child = _Node(parent=node, key=k, chooser=actor_here)
           node.children[k] = child
           return child
       legal_children = [node.children[k] for k in by_key if k in node.children]
       if not legal_children: break
       node = self._ucb_select(node, legal_children)
       before = world.active_index
       self._apply(world, by_key[node.key], me)
       if world.active_index != before:
           plies += 1
   return node
   ```
   (`_apply` is unchanged — it already crosses the boundary on attack/pass. It's
   actor-agnostic, so the same code drives the opponent's in-tree turn. `_deduped_legal`
   uses `state.current`, so it naturally enumerates whoever is to move.)

5. **`_backprop`** — negamax:
   ```python
   def _backprop(self, node, value, me):
       while node is not None:
           node.visits += 1
           if node.chooser is None or node.chooser == me:
               node.wins += value
           else:
               node.wins += (1.0 - value)
           node = node.parent
   ```

Nothing else changes. `_evaluate` still returns value in [0,1] from `me`'s view; UCB
is untouched (each child's mean is already from its chooser's perspective, so plain
maximize is correct).

## How to run it

```python
MCTSAgent(iterations=160, rollout="eval", search_plies=2, rng=rng)
```
`search_plies=1` == current behavior exactly. `search_plies=2` = your turn + opponent
+ your next, then eval leaf. **Pair it with `rollout="eval"`** — the eval truncates
each deep line cheaply, which is what makes multi-ply affordable (this is why pieces 1
and 2b are synergistic). Cost grows with depth × branching, so start at 2; only try 3
if 2 isn't enough and you can spare the time.

## Regression protocol (same discipline)

Re-run Dragapult vs Mega Charizard X/Y, mirrored seats, `rollout="eval"`,
`search_plies=2` (try both sides, and Dragapult-only).

**Success = band + mechanism, NOT a point.** Do not tune toward 84.
- The signal that 2b worked is the named lines moving: **Budew item-lock climbing off
  0/120**, and the stadium war resolving in Dragapult's favor — because the agent can
  now see the next-turn payoff. Report those line-fire counts next to win%.
- The win% should move toward the Dragapult-favored band (~68–82%). If it moves but
  Budew is still 0, depth alone wasn't enough — report that honestly; it points at
  piece 3 (search-owned target/opening policies: promote-to-disrupt is a turn-1
  opening choice the current legal-action set may not even surface well).
- **Run `test_mcts_negamax.py` first and make it green before trusting any matchup
  number.** If the number jumps but that test is red, the opponent model is inverted
  and the number is the believable-disguise bug, not progress.

## Watch items for integration

- Your `position_value` is the real signed eval; the file imports it unchanged. (My
  sandbox used a shim; ignore that — your import line is correct as-is.)
- `_apply` calling `end_turn`/`start_turn` inside the tree means the opponent's
  in-tree turn draws a card off the determinized deck — intended. Just confirm
  `start_turn` doesn't do anything that assumes it's the "real" turn (logging side
  effects are fine; persistent external state would not be).
- Per-iteration cost roughly multiplies with depth. If 2-ply is too slow at your
  current `iterations`, drop iterations rather than depth — one good 2-ply look beats
  many shallow ones for this specific gap.
