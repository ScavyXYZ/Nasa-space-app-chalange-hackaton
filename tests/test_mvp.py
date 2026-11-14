import unittest
from fastapi.testclient import TestClient
from backend.main import create_app
from algorithms.terrain import TerrainGrid
from algorithms import plan_route
from algorithms.grid import MarsRasterGeometry


class MVPTests(unittest.TestCase):
    def test_route_contains_sourced_nearby_regions(self):
        with TestClient(create_app()) as client:
            r=client.post("/api/route",json={
                "start":{"lon":77.450812,"lat":18.444801},
                "end":{"lon":77.470379,"lat":18.426243},"nearby_radius_m":200})
            self.assertEqual(r.status_code,200)
            data=r.json()
            self.assertEqual(data["status"],"ok")
            self.assertGreater(len(data["nearby_science"]),0)
            for f in data["nearby_science"]:
                self.assertLessEqual(f["properties"]["distance_to_route_m"],200)
                self.assertEqual(f["properties"]["source"],"https://doi.org/10.3133/sim3464")
            self.assertTrue(data["warnings"])

    def test_search_budget_is_not_misreported_as_no_route(self):
        terrain=TerrainGrid.load()
        try:
            geometry=MarsRasterGeometry(terrain=terrain)
            data=plan_route(terrain.elevation,terrain.slope,terrain.valid,geometry,
                            terrain.lonlat(125,125),terrain.lonlat(180,180),max_slope_deg=45,max_expansions=1)
            self.assertEqual(data["status"],"search_limit")
        finally:
            terrain.close()

    def test_outside_and_blocked_are_explicit(self):
        with TestClient(create_app()) as client:
            data={"start":{"lon":77.450812,"lat":18.444801},"end":{"lon":0,"lat":0}}
            r=client.post("/api/route",json=data)
            self.assertEqual(r.json()["status"],"outside_grid")
            data["end"]={"lon":77.470379,"lat":18.426243}
            data["max_slope_deg"]=0
            self.assertEqual(client.post("/api/route",json=data).json()["status"],"blocked_endpoint")

    def test_qa_still_accessible(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.get("/gis-check").status_code,200)
            self.assertEqual(client.get("/api/health").status_code,200)


if __name__=="__main__":
    unittest.main()
