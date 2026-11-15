"""Balanced bidirectional search. Requires edge costs >= metric distance.

Potential p=(d(v,goal)-d(v,start))/2 gives nonnegative reduced edge costs.
Stop when min(gF+p)+min(gB-p) >= best joined path.
"""
from heapq import heappop, heappush
from math import inf
from time import monotonic


def bidirectional_search(start, goal, neighbours, edge_cost, metric, *,
                         deadline=inf, max_expansions=300000, use_potential=True):
    if monotonic() >= deadline:
        return [], 0, True
    if start == goal:
        return [start], 0, False
    potentials = {}
    def potential(cell):
        if cell not in potentials:
            potentials[cell]=(metric(cell,goal)-metric(cell,start))/2 if use_potential else 0.
        return potentials[cell]
    best=[{start:0.},{goal:0.}]
    parents,closed=[{},{}],[set(),set()]
    queues=[[(potential(start),0.,start)],[(-potential(goal),0.,goal)]]
    join,incumbent,expanded=None,inf,0
    def clean(side):
        queue=queues[side]
        while queue and (queue[0][2] in closed[side] or queue[0][1]!=best[side].get(queue[0][2])):
            heappop(queue)
    while True:
        clean(0);clean(1)
        if not queues[0] or not queues[1]:
            break
        if incumbent<inf and queues[0][0][0]+queues[1][0][0]>=incumbent:
            break
        if expanded>=max_expansions or expanded%128==0 and monotonic()>=deadline:
            return [],expanded,True
        f=queues[0][0][0]-potential(start)
        b=queues[1][0][0]+potential(goal)
        side=expanded%2 if abs(f-b)<1e-8 else (0 if f<b else 1)
        _,cost,cell=heappop(queues[side])
        closed[side].add(cell);expanded+=1
        if cell in best[1-side] and cost+best[1-side][cell]<incumbent:
            incumbent,join=cost+best[1-side][cell],cell
        for other in neighbours(cell):
            if other in closed[side]:
                continue
            transition=edge_cost(cell,other) if side==0 else edge_cost(other,cell)
            if transition is None:
                continue
            candidate=cost+transition
            if candidate>=best[side].get(other,inf):
                continue
            best[side][other]=candidate;parents[side][other]=cell
            heappush(queues[side],(candidate+(1 if side==0 else -1)*potential(other),candidate,other))
            if other in best[1-side] and candidate+best[1-side][other]<incumbent:
                incumbent,join=candidate+best[1-side][other],other
    if join is None:
        return [],expanded,False
    left=[join]
    while left[-1]!=start:
        left.append(parents[0][left[-1]])
    path=list(reversed(left))
    while path[-1]!=goal:
        path.append(parents[1][path[-1]])
    return path,expanded,False
