import json
import unittest
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS
from fastapi.testclient import TestClient
from rasterio.windows import Window
from shapely.geometry import shape

from algorithms.terrain import TerrainGrid
from backend.main import create_app

ROOT=Path(__file__).resolve().parents[1]


class RegionalTests(unittest.TestCase):
    def test_full_optical_footprint_has_measured_heights(self):
        grid=TerrainGrid.load("regional")
        try:
            self.assertEqual(grid.shape,(1513,1515))
            self.assertTrue(grid.valid.all())
            context=json.loads((ROOT/"data/processed/gis/context_config.json").read_text())
            (south,west),(north,east)=context["bounds_lat_lon"]
            for lon in [west,(west+east)/2,east]:
                for lat in [south,(south+north)/2,north]:
                    self.assertTrue(grid.sample(lon,lat)["valid"])
        finally:
            grid.close()

    def test_native_source_pixels_preserved_and_legacy_unchanged(self):
        source=ROOT/"data/raw/dem/M20_JezeroCrater_CTXDEM_20m.tif"
        if not source.exists():
            self.skipTest("Raw source not included in runtime checkout")
        grid=TerrainGrid.load("regional")
        try:
            with rasterio.open(source) as src:
                window=Window(*grid.metadata["source_window_col_row_width_height"])
                original=src.read(1,window=window)
                np.testing.assert_array_equal(original,grid.elevation)
                halo=Window(window.col_off-1,window.row_off-1,window.width+2,window.height+2)
                z=src.read(1,window=halo,masked=True).filled(np.nan)
                lat=(grid.affine.f+(np.arange(grid.shape[0])+.5)*grid.affine.e)/3396190
                dx=20*np.cos(lat)/np.cos(np.deg2rad(18.4663))
                gx=(z[1:-1,2:]-z[1:-1,:-2])/(2*dx[:,None])
                gy=(z[2:,1:-1]-z[:-2,1:-1])/40
                expected=np.rad2deg(np.arctan(np.hypot(gx,gy)))
                np.testing.assert_allclose(expected,grid.slope,atol=1e-4)
            for filename,array in [("jezero_dem_crop.tif",grid.elevation),("jezero_slope.tif",grid.slope)]:
                with rasterio.open(ROOT/"data/processed/regional"/filename) as tif:
                    self.assertTrue(CRS(tif.crs).equals(grid.crs,ignore_axis_order=True))
                    self.assertEqual(tif.transform,grid.affine)
                    np.testing.assert_array_equal(tif.read(1),array)
                    np.testing.assert_array_equal(tif.read_masks(1)>0,grid.valid.astype(bool))
            legacy=TerrainGrid.load("ctx")
            try:
                self.assertEqual(legacy.shape,(250,250))
                self.assertEqual(legacy.metadata["aoi_size_km"],5)
            finally:
                legacy.close()
        finally:
            grid.close()

    def test_regional_catalog_display_and_source(self):
        with TestClient(create_app()) as client:
            layers=client.get("/api/layers").json()
            self.assertTrue(layers["terrain"]["regional"]["available"])
            self.assertIn("regional",layers["science"]["url"])
            science=client.get(layers["science"]["url"]).json()
            self.assertEqual(len(science["features"]),12)
            for feature in science["features"]:
                self.assertTrue(shape(feature["geometry"]).is_valid)
                self.assertIn("15m",feature["properties"]["display_geometry_note"])
            self.assertEqual(len(client.get("/api/geology?dataset=regional").json()["features"]),315)

    def test_long_route_outside_old_aoi(self):
        grid=TerrainGrid.load("regional")
        try:
            start=grid.lonlat(300,450);end=grid.lonlat(1200,1200)
            old=TerrainGrid.load("ctx")
            try:
                for point in [start,end]:
                    with self.assertRaises(ValueError):old.index(*point)
            finally:
                old.close()
            with TestClient(create_app()) as client:
                response=client.post("/api/route",json={"dataset":"regional",
                    "start":dict(zip(("lon","lat"),start)),"end":dict(zip(("lon","lat"),end)),
                    "max_slope_deg":25})
                self.assertEqual(response.status_code,200)
                data=response.json()
                self.assertEqual(data["status"],"ok")
                self.assertGreater(data["metrics"]["distance_m"],20000)
                self.assertLessEqual(data["metrics"]["max_slope_deg"],25)
                self.assertLessEqual(data["metrics"]["max_segment_grade_deg"],25)
        finally:
            grid.close()


if __name__=="__main__":
    unittest.main()
