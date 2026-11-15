"""Independent Dijkstra oracle and explicit smooth-climb regressions."""
import heapq
import math
import unittest
from time import monotonic
import numpy as np

from algorithms.bidirectional import bidirectional_search
from algorithms.global_routing import GlobalTerrain, distance


def dijkstra(start, goal, neighbours, cost):
    queue=[(0.,start)];best={start:0.}
    while queue:
        value,node=heapq.heappop(queue)
        if value!=best[node]:
            continue
        if node==goal:
            return value
        for other in neighbours(node):
            edge=cost(node,other)
            if edge is None:
                continue
            candidate=value+edge
            if candidate<best.get(other,math.inf):
                best[other]=candidate;heapq.heappush(queue,(candidate,other))
    return math.inf


class BidirectionalTests(unittest.TestCase):
    def test_matches_dijkstra_with_asymmetric_costs_and_obstacles(self):
        for seed in range(30):
            rng=np.random.default_rng(seed)
            blocked=rng.random((12,12))<.15
            blocked[0,0]=blocked[11,11]=False
            extra=rng.random((12,12))*5
            def neighbours(a):
                for dr,dc in [(0,1),(0,-1),(1,0),(-1,0),(1,1),(-1,-1)]:
                    b=a[0]+dr,a[1]+dc
                    if 0<=b[0]<12 and 0<=b[1]<12 and not blocked[b]:
                        yield b
            def metric(a,b):
                return math.hypot(a[0]-b[0],a[1]-b[1])
            def cost(a,b):
                return None if blocked[a] or blocked[b] else metric(a,b)+float(extra[b])
            oracle=dijkstra((0,0),(11,11),neighbours,cost)
            for potential in [True,False]:
                path,_,limited=bidirectional_search((0,0),(11,11),neighbours,cost,metric,use_potential=potential)
                self.assertFalse(limited)
                measured=sum(cost(a,b) for a,b in zip(path,path[1:])) if path else math.inf
                self.assertAlmostEqual(measured,oracle,places=8)

    def test_smooth_high_climb_is_allowed_and_altitude_invariant(self):
        heights=np.repeat((np.arange(24)*100.)[:,None],48,axis=1)
        counts=np.ones((24,48),dtype=int)
        low=GlobalTerrain(heights,counts)
        high=GlobalTerrain(heights+100000,counts)
        start,end=low.coordinate((4,20)),low.coordinate((18,20))
        result=low.route(start,end,max_grade_deg=1)
        elevated=high.route(start,end,max_grade_deg=1)
        self.assertEqual(result["status"],"ok")
        self.assertEqual(elevated["status"],"ok")
        self.assertGreater(result["metrics"]["ascent_m"],1000)
        self.assertLess(result["metrics"]["max_grade_deg"],1)
        self.assertEqual(result["route"]["geometry"],elevated["route"]["geometry"])

    def test_steep_wall_does_not_become_passable_when_lowered(self):
        heights=np.zeros((24,48));heights[12:]=1e6
        grid=GlobalTerrain(heights,np.ones_like(heights))
        a,b=grid.coordinate((10,10)),grid.coordinate((14,10))
        self.assertEqual(grid.route(a,b,max_grade_deg=1)["status"],"no_route")

    def test_budget(self):
        path,_,limited=bidirectional_search(0,2,lambda x:[(x+1)%3],lambda a,b:1,
                                            lambda a,b:0,deadline=monotonic()-1)
        self.assertTrue(limited);self.assertFalse(path)


if __name__=="__main__":
    unittest.main()
