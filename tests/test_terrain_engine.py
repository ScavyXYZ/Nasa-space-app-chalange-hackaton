"""Synthetic fixtures test software only, not claimed as Mars observations."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from pyproj import CRS
from fastapi.testclient import TestClient

from algorithms.terrain import ROOT, TerrainGrid, TerrainError
from algorithms.metrics import analyze_route
from backend.main import create_app


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.directory = self.root / "data/processed"
        self.directory.mkdir(parents=True)
        self.z = np.arange(36,dtype="float32").reshape(6,6)
        self.slope = np.full((6,6),5,dtype="float32")
        self.mask = np.ones((6,6),dtype="uint8")
        crs = CRS.from_proj4("+proj=eqc +lat_ts=18.4663 +R=3396190 +units=m")
        self.metadata = {"crs_wkt":crs.to_wkt(),"transform":[20,0,4351980,0,-20,1095820,0,0,1],
                         "shape_rows_cols":[6,6],"pixel_size_m":[20,20],
                         "east_west_ground_cell_size_range_m":[19.99,20.01]}
        (self.directory / "terrain_metadata.json").write_text(json.dumps(self.metadata))
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        np.save(self.directory/"jezero_elevation.npy",self.z)
        np.save(self.directory/"jezero_slope.npy",self.slope)
        np.save(self.directory/"jezero_valid_mask.npy",self.mask)

    def load(self):
        return TerrainGrid.load("ctx",self.root)

    def test_point_uses_actual_cell(self):
        grid=self.load()
        p=grid.sample(*grid.lonlat(2,3))
        self.assertEqual((p["row"],p["col"]),(2,3))
        self.assertEqual(p["elevation_m"],15.)
        self.assertEqual(p["slope_deg"],5.)

    def test_nodata_returns_json_safe_nulls(self):
        self.z[2,3]=self.slope[2,3]=np.nan
        self.mask[2,3]=0
        self.save()
        grid=self.load()
        p=grid.sample(*grid.lonlat(2,3))
        self.assertFalse(p["valid"])
        self.assertIsNone(p["elevation_m"])
        self.assertIsNone(p["slope_deg"])
        self.assertTrue(grid.blocked_mask()[2,3])

    def test_bad_masks_rejected(self):
        self.mask[2,3]=0
        self.save()
        with self.assertRaisesRegex(TerrainError,"masks disagree"):
            self.load()

    def test_out_of_bounds_not_clamped(self):
        with self.assertRaisesRegex(TerrainError,"outside"):
            self.load().sample(0,0)

    def test_nonfinite_coordinates_rejected(self):
        for lon,lat in [(np.nan,18),(77,np.inf),(181,18)]:
            with self.assertRaises(TerrainError):
                self.load().sample(lon,lat)

    def test_profile_length_gain_loss(self):
        grid=self.load()
        a,b=grid.lonlat(2,0),grid.lonlat(2,5)
        result=analyze_route(grid,[a,b])
        summary=result["summary"]
        self.assertAlmostEqual(summary["distance_m"],grid.distance_m(a,b),places=5)
        self.assertEqual(summary["elevation_gain_m"],5)
        self.assertEqual(summary["elevation_loss_m"],0)
        self.assertEqual(summary["net_elevation_change_m"],5)
        reverse=analyze_route(grid,[b,a])["summary"]
        self.assertEqual(reverse["elevation_gain_m"],0)
        self.assertEqual(reverse["elevation_loss_m"],5)
        self.assertFalse(summary["requires_review"])

    def test_profile_rejects_crossed_void_with_valid_endpoints(self):
        self.z[:,3]=self.slope[:,3]=np.nan
        self.mask[:,3]=0
        self.save()
        grid=self.load()
        with self.assertRaisesRegex(TerrainError,"unknown terrain"):
            analyze_route(grid,[grid.lonlat(2,0),grid.lonlat(2,5)],sample_step_m=1000)

    def test_no_diagonal_cutting_unknown_corner(self):
        self.z[1,2]=self.slope[1,2]=np.nan
        self.mask[1,2]=0
        self.save()
        grid=self.load()
        # Direct projected segment through a corner must include the side cells.
        cells=set(grid.crossed_cells(grid.lonlat(1,1),grid.lonlat(2,2)))
        self.assertIn((1,2),cells)

    def test_slope_threshold_is_a_review_flag_not_safety_claim(self):
        self.slope[2,2]=25
        self.save()
        grid=self.load()
        result=analyze_route(grid,[grid.lonlat(2,0),grid.lonlat(2,5)],max_slope_deg=15)
        self.assertTrue(result["summary"]["requires_review"])
        self.assertEqual(result["summary"]["max_terrain_slope_deg"],25)

    def test_stationary_route(self):
        grid=self.load()
        p=grid.lonlat(2,2)
        result=analyze_route(grid,[p,p])
        self.assertEqual(result["summary"]["distance_m"],0)
        self.assertEqual(result["summary"]["elevation_gain_m"],0)

    def test_profile_resource_limit(self):
        grid=self.load()
        with self.assertRaisesRegex(TerrainError,"limit"):
            analyze_route(grid,[grid.lonlat(0,0),grid.lonlat(5,5)],max_samples=2)

    def test_earth_crs_rejected(self):
        self.metadata["crs_wkt"]=CRS.from_epsg(3857).to_wkt()
        (self.directory/"terrain_metadata.json").write_text(json.dumps(self.metadata))
        with self.assertRaisesRegex(TerrainError,"Mars"):
            self.load()

    def test_api_errors_and_profile(self):
        grid=self.load()
        lon,lat=grid.lonlat(2,2)
        with TestClient(create_app(self.root)) as client:
            self.assertEqual(client.get("/api/health").status_code,200)
            point=client.get("/api/elevation",params={"lon":lon,"lat":lat})
            self.assertEqual(point.status_code,200)
            self.assertEqual(point.json()["elevation_m"],14)
            self.assertEqual(client.get("/api/elevation?lon=0&lat=0").status_code,422)
            self.assertEqual(client.get(f"/api/elevation?lon={lon}&lat={lat}&dataset=earth").status_code,422)
            self.assertEqual(client.get(f"/api/elevation?lon=nan&lat={lat}").status_code,422)
            missing=client.get(f"/api/elevation?lon={lon}&lat={lat}&dataset=hirise")
            self.assertEqual(missing.status_code,503)
            payload={"coordinates":[grid.lonlat(2,0),grid.lonlat(2,5)]}
            result=client.post("/api/route/profile",json=payload)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json()["summary"]["elevation_gain_m"],5)
            self.assertEqual(client.post("/api/route/profile",json={**payload,"max_slope_deg":91}).status_code,422)
            self.assertEqual(client.post("/api/route/profile",json={**payload,"coordinates":[[1,2,3],[4,5,6]]}).status_code,422)
            self.assertEqual(client.get("/api/assets/not-allowed.png").status_code,404)


class RealDataIntegration(unittest.TestCase):
    def test_real_ctx_and_hirise(self):
        for dataset in ["ctx","hirise"]:
            grid=TerrainGrid.load(dataset)
            a=grid.lonlat(grid.shape[0]//2,grid.shape[1]//2)
            b=grid.lonlat(grid.shape[0]//2,grid.shape[1]//2+5)
            result=analyze_route(grid,[a,b])
            self.assertGreater(result["summary"]["distance_m"],0)
            self.assertTrue(all(p["valid"] for p in result["profile"]))

    def test_missing_data_health_is_unavailable(self):
        with tempfile.TemporaryDirectory() as empty, TestClient(create_app(empty)) as client:
            self.assertEqual(client.get("/api/health").status_code,503)

    def test_real_api_layers_and_assets(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.get("/api/layers").status_code,200)
            self.assertEqual(len(client.get("/api/geology").json()["features"]),8)
            self.assertGreaterEqual(len(client.get("/api/points").json()["features"]),3)
            for dataset in ["ctx","hirise"]:
                response=client.get(f"/api/overlays/{dataset}")
                self.assertEqual(response.status_code,200)
                for item in response.json()["overlays"]:
                    image=client.get(item["url"])
                    self.assertEqual(image.status_code,200)
                    self.assertEqual(image.headers["content-type"],"image/png")
            self.assertEqual(client.get("/").status_code,200)
            self.assertEqual(client.get("/api/assets/ctx-optical.png").status_code,200)


if __name__=="__main__":
    unittest.main()
