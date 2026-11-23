# Heading-aware nearby-place ranking: algorithm specification

This page describes the ranking method in a language-neutral way, so it can be
re-implemented or evaluated without reading the Python. It is a reference
specification, not a submission of code. The reference implementation is
`detour/world.py` (`cost_to_go`) and `detour/scorers.py` (`HeadingAware`).
Every number in the test vectors below is checked by `tests/test_spec_vectors.py`.

## 1. The problem

Given a vehicle position and a set of candidate places, rank by distance (straight-line
or direction-blind drive time) can put first a place the vehicle has just passed, because
reaching it needs a U-turn or a loop around the block. The proposal is to rank by the
time it would actually take to reach each place, given the direction of travel.

## 2. Inputs and outputs

| Input | Meaning |
|---|---|
| Road graph | Directed edges with length (m) and speed (m/s). One-way streets are a single edge. |
| `uturn_ok[node]` | Whether a vehicle may reverse at that node (true at intersections and dead ends). |
| Vehicle state | The directed edge `(a, b)` being driven, and `t` in [0, 1], the fraction already travelled along it. |
| Candidates | A set of places, each attached to a graph node. |
| `uturn_penalty` | Seconds added for any reversal. Reference value: 20 s. |

Output: for each candidate, an estimated time to reach it (seconds, or infinity if
unreachable). The ranking is ascending by that time. Ties go to the earlier candidate in
the input order.

The only new input compared with a distance-based ranking is the vehicle's heading. The
heading is used to decide which directed edge the vehicle is on (section 5).

## 3. Model

State = "arrived at node `v` by travelling the edge `u -> v`", written `(u, v)`.
Using directed-edge states instead of nodes is what lets the cost of a reversal appear
naturally: leaving `v` back along the edge to `u` is a transition from state `(u, v)`
to state `(v, u)` with an extra `uturn_penalty`.

- Driving edge `(m, w)` costs `length(m, w) / speed(m, w)` seconds.
- Reversing at node `m` (taking `m -> u` right after arriving by `u -> m`) costs
  `uturn_penalty` extra seconds, and is only allowed if `uturn_ok[m]`.
- The remaining part of the current edge costs `(1 - t) * length(a, b) / speed(a, b)`.
  The vehicle cannot turn around mid-block.

## 4. Algorithm

```
# cost_to_go(target, uturn_penalty)
# Returns, for every state (u, v), the fastest time to reach `target` from a vehicle
# that has just arrived at v via u -> v.  Backward Dijkstra over directed-edge states.

g = {}                                   # state -> cost
heap = min-heap
for u in in_neighbors(target):           # vehicle arrives at the target node
    g[(u, target)] = 0
    push (0, (u, target))

while heap not empty:
    cost, (m, w) = pop(heap)
    if cost > g[(m, w)]: continue        # stale entry
    step = length(m, w) / speed(m, w)    # time spent travelling m -> w
    for u in in_neighbors(m):            # predecessor state (u, m): arrived at m via u -> m
        is_reversal = (u == w)           # going m -> w right after u -> m with u == w
        if is_reversal and not uturn_ok[m]: continue
        c = cost + step + (uturn_penalty if is_reversal else 0)
        if (u, m) not in g or c < g[(u, m)]:
            g[(u, m)] = c
            push (c, (u, m))
```

Scoring one query:

```
remaining = (1 - t) * length(a, b) / speed(a, b)
for each candidate p:
    if p.node == b:   score[p] = remaining
    else:             score[p] = remaining + g_p[(a, b)]      # infinity if (a, b) not in g_p
rank candidates by score ascending (stable)
```

`g_p = cost_to_go(p.node, uturn_penalty)` does not depend on where the vehicle is, so it
can be computed once per candidate place and reused for every later query.

## 5. Finding the directed edge from a noisy GPS fix

Pick the directed edge `(a, b)` that minimises

```
(distance from fix to the edge / sigma_pos)^2 + (heading difference to the edge bearing / sigma_head)^2
```

with reference noise of `sigma_pos = 8 m` and `sigma_head = 10 degrees`. Without the
heading term, the two directions of a two-way street tie, which is the heading-blind case.
In a stream of fixes, restrict the candidates to edges reachable from the previous match
(speed times elapsed time plus a small margin, and a short allowance behind) and fall back
to the full search if the best restricted cost is too high. In the benchmark, single-fix
matching loses 2 to 3 times more time than this track-aware matching on dense one-way
streets (see the README results). See `detour/matching.py`.

## 6. Cost and latency (design notes)

- One `cost_to_go` run touches each directed-edge state once. For a graph with `E` directed
  edges and small average degree this is `O(E log E)` per candidate place.
- Per query, scoring is a dictionary lookup per candidate plus the map-matching step.
- The reference implementation runs one backward search per place and caches it. That suits
  a benchmark where the same places are queried thousands of times. For a live query with
  few candidates, a single forward search from the vehicle's state with early termination
  once the candidates are settled gives the same scores with one search instead of one per
  candidate. This variant is a design note and has not been implemented or measured here.

## 7. Suggested API shape

An optional heading on the origin when ranking by drive time (degrees clockwise from
north, or a bearing already used by route origins). Behaviour when it is absent: unchanged.
Behaviour when it is present: the first edge is chosen using the heading as in section 5,
and reversal costs are applied. A fallback is recommended when speed is very low and the
heading is unreliable: use the heading-blind ranking. That fallback is a recommendation and
was not evaluated in this repo.

## 8. Test vectors

All vectors use 100 m edges at 10 m/s (10 s per edge) and `uturn_penalty = 20`.

### Vector A: a place just behind versus a place ahead

Straight two-way street, nodes 0, 1, 2, 3 at x = 0, 100, 200, 300 m. The vehicle is on edge
`(1, 2)` at `t = 0.5`, heading east. Place A is at node 1 (behind), place B at node 3 (ahead).

| | Straight-line distance | Heading-aware time |
|---|---|---|
| A (behind) | 50 m | 5 s to node 2, 20 s reversal, 10 s back = **35 s** |
| B (ahead) | 150 m | 5 s to node 2, 10 s on = **15 s** |

Distance ranking picks A. Heading-aware ranking picks **B**.

### Vector B: a loop around a one-way block

Square block, one-way, counter-clockwise: edges `0->1->2->3->0`, nodes at (0,0), (100,0),
(100,100), (0,100). No reversals possible. The vehicle is on `(0, 1)` at `t = 0.5`. Places:
A at node 0, B at node 3, C at node 2.

| | Straight-line distance | Heading-aware time |
|---|---|---|
| A (node 0, just passed) | 50 m | 5 + 10 + 10 + 10 = **35 s** (a full loop) |
| B (node 3) | 112 m | 5 + 10 + 10 = **25 s** |
| C (node 2) | 112 m | 5 + 10 = **15 s** |

Distance ranking picks A. Heading-aware ranking picks **C**, then B, then A.

### Vector C: reversal not allowed at one node

Vector A with `uturn_ok[2] = false`. The vehicle cannot reverse at node 2, so to reach A it
must drive on to the dead end at node 3, reverse there, and come back: 5 + 10 s to node 3,
20 s reversal, 10 + 10 s back to node 1 = **55 s**. B is still **15 s**.

## 9. What this does not cover

Traffic, signals, turn restrictions, and per-turn costs other than the single reversal
penalty are not modelled. Speeds are defaults from the road class. The benchmark's ground
truth uses the same graph model as the ranking (with a different reversal penalty, 30 s, so
the scorer is deliberately mis-specified), and the drives are simulated. Google Maps' own
ranking was not measured. See the README limitations section.
