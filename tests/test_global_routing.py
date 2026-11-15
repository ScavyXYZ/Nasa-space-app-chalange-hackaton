import unittest

import numpy as np
from fastapi.testclient import TestClient

from algorithms.global_routing import GlobalTerrain, distance
from algorithms.mola128 import Mola128Store
from backend.main import create_app


class GlobalRoutingTests(unittest.TestCase):
    def setUp(self):
        self.grid = GlobalTerrain(np.zeros((24, 48)), np.ones((24, 48), dtype=int))

    def test_longitude_wrap_and_poles(self):
        self.assertEqual(self.grid.index((-180, 0)), self.grid.index((180, 0)))
        self.assertEqual(self.grid.neighbour((0, 0), -1, 0, 24, 48), (0, 24))
        self.assertEqual(self.grid.neighbour((23, 0), 1, 0, 24, 48), (23, 24))
        result = self.grid.route((179, 0), (-179, 0))
        self.assertEqual(result["status"], "ok")
        self.assertLess(result["metrics"]["distance_m"], 500000)
        result = self.grid.route((0, 89), (180, 89))
        self.assertEqual(result["status"], "ok")
        self.assertLess(result["metrics"]["distance_m"], 500000)

    def test_grade_and_interpolated_provenance(self):
        self.grid.elevation[:, 24:] = 1000000
        result = self.grid.route((10, 0), (-10, 0), max_grade_deg=0)
        self.assertEqual(result["status"], "no_route")
        self.grid.counts[:] = 0
        result = self.grid.route((10, 0), (20, 0))
        self.assertEqual(result["metrics"]["interpolated_cells"], result["metrics"]["cells"])

    def test_stationary_and_time_budget(self):
        result = self.grid.route((10, 0), (10, 0))
        self.assertEqual(result["route"]["geometry"]["type"], "Point")
        self.assertEqual(result["metrics"]["distance_m"], 0)
        self.assertEqual(self.grid.route((0, 0), (90, 0), time_budget_s=0)["status"], "search_limit")

    def test_success_is_not_traversability_verification(self):
        # Even fully measured, perfectly flat coarse bins cannot rule out
        # sub-cell crater walls. Changing the graph search cannot recover them.
        result=self.grid.route((10,0),(20,0))
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["metrics"]["max_grade_deg"],0)
        assessment=result["traversability"]
        self.assertEqual(assessment["status"],"unverified")
        self.assertEqual(assessment["scope"],"strategic_corridor")
        self.assertIn("local_crater_rims_and_cliffs",assessment["missing_evidence"])
        self.assertEqual(result["route"]["properties"]["traversability"],assessment)

    def test_reported_crater_route_remains_unverified(self):
        # Every output cell now uses real 128 ppd terrain, not just A/B patches.
        with TestClient(create_app()) as client:
            response=client.post("/api/expedition",json={
                "start":{"lon":-97.150761,"lat":24.024217},
                "end":{"lon":150.624967,"lat":9.070396}})
            self.assertEqual(response.status_code,200)
            result=response.json()
            self.assertEqual(result["status"],"ok")
            self.assertEqual(result["dataset"],"mola128")
            self.assertEqual(result["traversability"]["status"],"unverified")
            self.assertLess(result["traversability"]["dem_spacing_m"],464)
            self.assertGreater(result["metrics"]["distance_m"],6_000_000)
            self.assertTrue(result["hazard_policy"]["enabled"])
            self.assertTrue(result["terrain_validation"]["entire_route"])
            self.assertFalse(result["terrain_validation"]["catalogue_circles_blocked"])
            self.assertLessEqual(result["metrics"]["max_grade_deg"],15)
            self.assertLessEqual(result["metrics"]["max_surface_slope_deg"],15)
            self.assertTrue(all(p["dataset"]=="mola128" and p["slope_deg"]<=15 for p in result["profile"]))
            self.assertEqual(result["profile"][0]["dataset"],"mola128")
            self.assertEqual(result["profile"][-1]["dataset"],"mola128")

    def test_actual_mola_and_api(self):
        grid = GlobalTerrain.load()
        # Olympus Mons vicinity must be high; Hellas must be low.
        self.assertGreater(grid.sample((-133.8, 18.65))["elevation_m"], 18000)
        self.assertLess(grid.sample((70, -42))["elevation_m"], -5000)
        self.assertEqual(grid.display()["shape"], [180, 360])
        with TestClient(create_app()) as client:
            self.assertEqual(client.get("/api/global").status_code, 200)
            self.assertEqual(client.get("/api/global/elevation?lon=181&lat=0").status_code, 422)
            response = client.post("/api/global/route", json={
                "start": {"lon": -133.8, "lat": 18.65}, "end": {"lon": -112.5, "lat": -7.5}})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["approximate"])
            self.assertGreater(result["metrics"]["distance_m"], 1800000)
            coordinates = result["route"]["geometry"]["coordinates"]
            measured = sum(distance(a, b) for a, b in zip(coordinates, coordinates[1:]))
            self.assertAlmostEqual(measured, result["metrics"]["distance_m"])
            native=Mola128Store()
            for a, b in zip(coordinates, coordinates[1:]):
                ca,cb=native.index(a),native.index(b)
                self.assertLessEqual(abs(ca[0]-cb[0]),1)
                delta=abs(ca[1]-cb[1])
                self.assertLessEqual(min(delta,native.cols-delta),1)
            self.assertEqual(client.get("/api/assets/mola-topography.jpg").status_code, 200)


if __name__ == "__main__":
    unittest.main()
