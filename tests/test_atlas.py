import io
import json
import unittest
import numpy as np
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient
from algorithms.atlas import Geology, expedition
from algorithms.global_routing import GlobalTerrain
from backend.main import create_app

ROOT=Path(__file__).resolve().parents[1]


class AtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geology=Geology(ROOT)
        cls.terrain=GlobalTerrain.load()

    def test_geology_source_and_boundaries(self):
        self.assertEqual(len(self.geology.geometries),1311)
        units=self.geology.point(77.4508,18.4447)
        self.assertTrue(units)
        self.assertTrue(all(u["source"]=="https://doi.org/10.3133/sim3292" for u in units))
        wrapped=self.geology.along([(179.9,5),(-179.9,5)])
        # Ensure an antimeridian crossing doesn't accidentally intersect the entire planet.
        self.assertLess(len(wrapped),10)

    def test_multi_stop_metrics(self):
        points=[(-133.8,18.65),(-122,6),(-112.5,-7.5)]
        result=expedition(self.terrain,points,15,5,self.geology)
        self.assertEqual(result["status"],"ok")
        self.assertEqual(len(result["legs"]),2)
        self.assertAlmostEqual(sum(leg["distance_m"] for leg in result["legs"]),result["metrics"]["distance_m"])
        self.assertEqual(result["profile"][-1]["distance_m"],result["metrics"]["distance_m"])
        self.assertTrue(all(a["distance_m"]<=b["distance_m"] for a,b in zip(result["profile"],result["profile"][1:])))
        self.assertEqual(len(result["metrics"]["snap_offsets_m"]),3)
        self.assertEqual(result["data_quality"]["resolution_deg"],.0625)
        self.assertTrue(result["geological_units"])

    def test_catalog_inspect_media_qr_and_tiles(self):
        with TestClient(create_app()) as client:
            catalog=client.get("/api/atlas").json()
            self.assertEqual(catalog["features"],1311)
            self.assertEqual(len(catalog["tiles"]),8)
            self.assertEqual(len(catalog["missions"]),3)
            self.assertTrue(client.get("/api/atlas/inspect?lon=77.45&lat=18.44").json()["geology"])
            self.assertEqual(client.get("/api/atlas/inspect?lon=nan&lat=0").status_code,422)
            for name in ["perseverance","jezero-delta","curiosity"]:
                response=client.get("/api/atlas/media/"+name)
                self.assertEqual(response.status_code,200)
                Image.open(io.BytesIO(response.content)).verify()
            qr=client.get("/api/share/qr",params={"url":"https://example.org/#mission=test"})
            self.assertEqual(qr.status_code,200)
            Image.open(io.BytesIO(qr.content)).verify()
            self.assertEqual(client.get("/api/share/qr?url=javascript:alert(1)").status_code,422)
            self.assertEqual(client.get("/api/atlas/tiles/mola/99/0/0").status_code,404)
            self.assertEqual(client.get("/api/atlas/tiles/mola/0/0/0").status_code,200)

    def test_unified_auto_ctx_and_global(self):
        with TestClient(create_app()) as client:
            local=client.post("/api/expedition",json={
                "start":{"lon":77.450812,"lat":18.444801},"end":{"lon":77.470379,"lat":18.426243}}).json()
            self.assertEqual(local["status"],"ok",local)
            self.assertEqual(local["dataset"],"regional")
            self.assertEqual(local["traversability"]["status"],"unverified")
            self.assertEqual(local["traversability"]["scope"],"local_dem_path")
            self.assertFalse(local["approximate"])
            self.assertEqual(local["data_quality"]["equatorial_spacing_m"],20)
            global_result=client.post("/api/expedition",json={
                "start":{"lon":179,"lat":5},"end":{"lon":-179,"lat":5}}).json()
            # One point is inside a catalogue crater, the other outside.
            # Coarse, apparently smooth heights must not certify an exit.
            self.assertEqual(global_result["status"],"no_route")
            self.assertEqual(global_result["reason"],"crater_exit_needs_finer_dem")
            self.assertFalse(global_result["terrain_validation"]["catalogue_circles_blocked"])
            baseline=global_result
            # Legacy avoid_craters=False cannot disable physical slope checks.
            global_result=client.post("/api/expedition",json={
                "start":{"lon":179,"lat":5},"end":{"lon":-179,"lat":5},
                "avoid_craters":False}).json()
            self.assertEqual(global_result["status"],baseline["status"])
            self.assertNotIn("route",global_result)
            # Independent native-coordinate wrap regression outside those rims.
            global_result=client.post("/api/expedition",json={
                "start":{"lon":179,"lat":0},"end":{"lon":-179,"lat":0}}).json()
            self.assertEqual(global_result["status"],"ok",global_result)
            self.assertEqual(global_result["dataset"],"mola128")
            self.assertLess(global_result["metrics"]["distance_m"],200000)
            self.assertEqual(client.post("/api/expedition",json={
                "start":{"lon":0,"lat":0},"end":{"lon":1,"lat":1},"resolution":"regional"}).status_code,422)
            self.assertEqual(client.post("/api/expedition",json={
                "start":{"lon":0,"lat":0},"end":{"lon":1,"lat":1},
                "stops":[{"lon":1,"lat":1}]*5}).status_code,422)

    def test_best_point_dem_and_native_ctx_levels(self):
        from algorithms.terrain import TerrainGrid
        grid=TerrainGrid.load("hirise")
        try:
            indices=np.argwhere(grid.valid)
            row,col=indices[len(indices)//2]
            lon,lat=grid.lonlat(int(row),int(col))
            with TestClient(create_app()) as client:
                inspected=client.get("/api/atlas/inspect",params={"lon":lon,"lat":lat}).json()
                self.assertEqual(inspected["elevation"]["dataset"],"hirise")
                self.assertEqual(inspected["elevation"]["spacing_m"],1)
                self.assertGreaterEqual(len(inspected["measurements"]),2)
                # Same-cell route is a valid exact point with no invented subpixel leg.
                result=client.post("/api/expedition",json={"start":{"lon":lon,"lat":lat},
                    "end":{"lon":lon,"lat":lat},"max_grade_deg":90}).json()
                self.assertEqual(result["status"],"ok")
                self.assertEqual(result["dataset"],"hirise")
                self.assertEqual(result["traversability"]["status"],"unverified")
                self.assertEqual(result["metrics"]["distance_m"],0)
                catalog=client.get("/api/atlas").json()
                source=next(s for s in catalog["tiles"] if s["id"]=="ctx-global")
                self.assertEqual(source["native_tile_size"],512)
                self.assertEqual(len(source["matrices"]),18)
        finally:
            grid.close()


if __name__=="__main__":
    unittest.main()
