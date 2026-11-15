import heapq
import json
import math
import unittest
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from algorithms import plan_route
from algorithms.grid import MarsRasterGeometry
from algorithms.pathfinding import RouteGraph
from algorithms.terrain import TerrainGrid
from backend.main import create_app


class TestGeometry:
    def pixel_to_lonlat(self, row, col):
        return float(col), float(row)

    def lonlat_to_pixel(self, lon, lat):
        return math.floor(lat), math.floor(lon)

    def distance_m(self, a, b):
        return math.dist(a, b) * 20


def dijkstra(graph, start, goal):
    queue = [(0.0, start)]
    visited = set()
    while queue:
        cost, cell = heapq.heappop(queue)
        if cell in visited:
            continue
        if cell == goal:
            return cost
        visited.add(cell)
        r, c = cell
        for nr in range(r - 1, r + 2):
            for nc in range(c - 1, c + 2):
                neighbour = nr, nc
                if graph.contains(neighbour) and neighbour not in visited:
                    edge = graph.edge_cost(cell, neighbour)
                    if edge is not None:
                        heapq.heappush(queue, (cost + edge, neighbour))
    return None


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.geometry = TestGeometry()

    def test_no_corner_cutting(self):
        z = np.zeros((2, 2))
        valid = np.array([[1, 0], [0, 1]])
        for mode in ('astar', 'hierarchical'):
            result = plan_route(z, z, valid, self.geometry, (0, 0), (1, 1), mode=mode)
            self.assertEqual(result['status'], 'no_route')

    def test_endpoint_errors_and_same_cell(self):
        z = np.zeros((3, 3))
        valid = np.ones_like(z)
        valid[1, 1] = 0
        self.assertEqual(plan_route(z, z, valid, self.geometry, (0, 0), (9, 9)),
                         {'status': 'outside_grid', 'endpoint': 'end'})
        self.assertEqual(plan_route(z, z, valid, self.geometry, (1, 1), (0, 0)),
                         {'status': 'blocked_endpoint', 'endpoint': 'start'})
        same = plan_route(z, z, valid, self.geometry, (0, 0), (0.2, 0.2))
        self.assertEqual(same['route']['geometry']['type'], 'Point')
        self.assertEqual(same['metrics']['distance_m'], 0)
        json.dumps(same, allow_nan=False)

    def test_high_cost_cells_blocked_or_avoided(self):
        z = np.zeros((5, 7))
        slope = z.copy()
        slope[2, 2:5] = 12
        valid = np.ones_like(z)
        for mode in ('astar', 'hierarchical'):
            flat = RouteGraph(z, slope, valid, self.geometry, slope_weight=0)
            penalized = RouteGraph(z, slope, valid, self.geometry, slope_weight=15)
            excluded = RouteGraph(z, slope, valid, self.geometry, max_slope_deg=10)
            a, b = (2, 0), (2, 6)
            self.assertIn((2, 3), flat.search(a, b, mode=mode).cells)
            for graph in (penalized, excluded):
                route = graph.search(a, b, mode=mode)
                self.assertTrue(route.cells)
                self.assertTrue(all(slope[cell] == 0 for cell in route.cells))

    def test_profile_and_segment_grade_limit(self):
        z = np.array([[0.0, 2.0, 1.0]])
        slope = np.zeros_like(z)
        valid = np.ones_like(z)
        result = plan_route(z, slope, valid, self.geometry, (0, 0), (2, 0))
        metrics = result['metrics']
        self.assertEqual(metrics['distance_m'], 40)
        self.assertEqual(metrics['ascent_m'], 2)
        self.assertEqual(metrics['descent_m'], 1)
        self.assertAlmostEqual(metrics['max_segment_grade_deg'], math.degrees(math.atan(0.1)))
        blocked = plan_route(z, slope, valid, self.geometry, (0, 0), (2, 0), max_slope_deg=5)
        self.assertEqual(blocked['status'], 'no_route')

    def test_coarse_graph_detects_disconnected_regions(self):
        z = np.zeros((20, 20))
        z[:, 12] = np.nan
        graph = RouteGraph(z, np.zeros_like(z), np.ones_like(z), self.geometry)
        a, b = (5, 5), (15, 15)
        ordinary = graph.search(a, b)
        hierarchical = graph.search(a, b, mode='hierarchical', block_size=4)
        self.assertEqual(ordinary.cells, ())
        self.assertEqual(hierarchical.cells, ())
        self.assertGreater(ordinary.expanded_cells, 0)
        self.assertEqual(hierarchical.expanded_cells, 0)

    def test_both_modes_match_dijkstra(self):
        rng = np.random.default_rng(1701)
        for trial in range(18):
            z = rng.uniform(-2, 2, (13, 17))
            slope = rng.uniform(0, 16, z.shape)
            valid = rng.random(z.shape) > 0.16
            start, goal = (0, 0), (12, 16)
            valid[start] = valid[goal] = True
            slope[start] = slope[goal] = 0.0
            graph = RouteGraph(z, slope, valid, self.geometry)
            expected = dijkstra(graph, start, goal)
            for mode in ('astar', 'hierarchical'):
                with self.subTest(trial=trial, mode=mode):
                    result = graph.search(start, goal, mode=mode, block_size=2 + trial % 5)
                    if expected is None:
                        self.assertEqual(result.cells, ())
                    else:
                        self.assertAlmostEqual(result.cost, expected)
                        self.assertEqual(result.cells[0], start)
                        self.assertEqual(result.cells[-1], goal)
                        self.assertAlmostEqual(sum(graph.edge_cost(a, b)
                                                   for a, b in zip(result.cells, result.cells[1:])), expected)

    def test_mars_neighbour_distances_match_existing_gis(self):
        data = Path(__file__).resolve().parents[1] / 'data' / 'processed'
        cases = ((data, (110, 110)), (data / 'hirise', (510, 510)))
        for folder, cell in cases:
            geometry = MarsRasterGeometry(folder / 'terrain_metadata.json')
            r, c = cell
            for target in ((r, c+1), (r+1, c-1), (r+1, c), (r+1, c+1), (r+2, c+2)):
                self.assertAlmostEqual(geometry.distance_m(cell, target),
                                        geometry.coordinates.distance_m(cell, target), places=7)

    def test_relaxed_mars_bound_is_consistent_and_preserves_optimal_cost(self):
        rng = np.random.default_rng(2026)
        for dataset in ("ctx", "hirise", "regional"):
            terrain = TerrainGrid.load(dataset)
            try:
                geometry = MarsRasterGeometry(terrain=terrain)
                for _ in range(100):
                    a = tuple(int(rng.integers(1, size-1)) for size in terrain.shape)
                    goal = tuple(int(rng.integers(size)) for size in terrain.shape)
                    for dr, dc in ((0, 1), (1, 0), (1, 1), (-1, 1)):
                        b = (a[0]+dr, a[1]+dc)
                        self.assertLessEqual(geometry.lower_bound_m(a, goal),
                                             geometry.distance_m(a, b)+geometry.lower_bound_m(b, goal)+1e-8)
                # Synthetic terrain isolates algorithm correctness from science data.
                for trial in range(6):
                    z = rng.uniform(-.01, .01, (9, 13))
                    slope = rng.uniform(0, 10, z.shape)
                    valid = rng.random(z.shape) > .15
                    valid[0, 0] = valid[-1, -1] = True
                    graph = RouteGraph(z, slope, valid, geometry)
                    expected = dijkstra(graph, (0, 0), (8, 12))
                    for mode in ("astar", "hierarchical"):
                        actual = graph.search((0, 0), (8, 12), mode=mode)
                        if expected is None:
                            self.assertEqual(actual.cells, ())
                        else:
                            self.assertAlmostEqual(actual.cost, expected)
            finally:
                terrain.close()

    def test_route_api_on_both_datasets(self):
        with TestClient(create_app()) as client:
            for name, a, b in (("ctx", (125, 125), (180, 180)),
                               ("hirise", (500, 500), (530, 530))):
                grid = TerrainGrid.load(name)
                try:
                    start = dict(zip(("lon", "lat"), grid.lonlat(*a)))
                    end = dict(zip(("lon", "lat"), grid.lonlat(*b)))
                finally:
                    grid.close()
                payload = {"dataset": name, "start": start, "end": end, "max_slope_deg": 45}
                ordinary = client.post("/api/route", json=payload)
                hierarchy = client.post("/api/route", json={**payload, "mode": "hierarchical"})
                for response in (ordinary, hierarchy):
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["status"], "ok", response.text)
                    self.assertGreater(response.json()["metrics"]["distance_m"], 0)
                self.assertAlmostEqual(ordinary.json()["cost"], hierarchy.json()["cost"])


if __name__ == '__main__':
    unittest.main()
