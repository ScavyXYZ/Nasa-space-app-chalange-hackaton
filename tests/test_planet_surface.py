import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
from fastapi.testclient import TestClient

from algorithms.global_routing import GlobalTerrain
from algorithms.mola128 import BANDS, PPD, TILE_ROWS, STEP_M
from algorithms.planet_surface import planet_surface, surface_axes
from algorithms.terrain import TerrainError
from backend.main import create_app


class AnalyticStore:
    step_m = STEP_M

    def _tile(self, band, west, kind):
        top = 2*PPD+BANDS.index(band)*TILE_ROWS

        class Tile:
            def __getitem__(self, index):
                r, c = index
                if kind == "c":
                    return np.broadcast_arrays(r, c)[0] % 2
                return (top+r)*.25-4000 + 100*np.cos((west*PPD+c)/PPD*math.pi/180)
        return Tile()


class PlanetSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.coarse = GlobalTerrain(np.full((90, 180), -1200), np.ones((90, 180)))
        self.store = AnalyticStore()

    def test_closed_bounded_axes_at_all_zoom_levels_and_dateline(self):
        for level in range(9):
            for lon, lat in [(179.99, 0), (-179.99, -25), (77.45, 18.44), (30, 89.9)]:
                x, y, focus = surface_axes(lon, lat, level)
                self.assertEqual((x[0], x[-1]), (-180, 180))
                self.assertEqual((y[0], y[-1]), (90, -90))
                self.assertTrue(np.all(np.diff(x) > 0))
                self.assertTrue(np.all(np.diff(y) < 0))
                self.assertLess(len(x)*len(y), 220000)
                self.assertLessEqual(np.diff(x).max(), 2)
                if level:
                    self.assertLessEqual(np.diff(x).min(), 2/2**level)

    def test_native_bilinear_values_no_fake_zero_polar_heights(self):
        result = planet_surface(self.store, self.coarse, 123, 10, 8)
        x, y = np.array(result["longitudes"]), np.array(result["latitudes"])
        h = np.array(result["elevations_m"]).reshape(result["shape"])
        row = int(np.argmin(abs(y-10)))
        col = int(np.argmin(abs(x-123)))
        # Analytic fixture is linear north/south; cosine interpolation error < .001m.
        expected = ((90-y[row])*PPD-.5)*.25-4000+100*math.cos(
            ((x[col] % 360)*PPD-.5)/PPD*math.pi/180)
        self.assertAlmostEqual(h[row, col], expected, delta=.02)
        np.testing.assert_allclose(h[:, 0], h[:, -1])
        np.testing.assert_allclose(h[0], -1200)
        np.testing.assert_allclose(h[-1], -1200)
        self.assertTrue(np.isfinite(h).all())
        self.assertEqual(result["native_coverage_latitude"], [-88, 88])
        self.assertEqual(result["display_step_deg"], 1/128)
        self.assertGreater(result["interpolated_fraction"], 0)
        self.assertIn("never certifies", result["note"])

    def test_polar_detail_stays_closed_and_explicitly_coarse(self):
        result = planet_surface(self.store, self.coarse, 0, 90, 8)
        h = np.array(result["elevations_m"]).reshape(result["shape"])
        self.assertTrue(np.isfinite(h).all())
        np.testing.assert_allclose(h[0], -1200)
        self.assertIn("not route coverage", result["polar_fallback"])

    def test_bad_arguments_and_endpoint_bounds(self):
        for args in [(0, 0, 9), (181, 0, 1), (0, float("nan"), 1)]:
            with self.assertRaises(TerrainError):
                surface_axes(*args)
        with TestClient(create_app()) as client:
            for query in ["level=9", "level=-1", "lat=91", "lon=nan", "level=1.5"]:
                self.assertEqual(client.get("/api/global/surface?"+query).status_code, 422)
            self.assertEqual(client.get("/api/globe/imagery/6/0/0").status_code, 404)
            self.assertEqual(client.get("/api/globe/imagery/1/2/0").status_code, 404)
            self.assertEqual(client.get("/api/globe/imagery/1/0/-1").status_code, 404)

    def test_missing_numeric_files_do_not_return_an_invented_native_surface(self):
        from algorithms.mola128 import Mola128Store
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(TerrainError) as context:
                planet_surface(Mola128Store(Path(folder)), self.coarse, 0, 0, 1)
            self.assertEqual(context.exception.code, "terrain_data_unavailable")

    def test_prepared_local_imagery_is_complete_if_present(self):
        root = Path(__file__).resolve().parents[1]
        folder = root/"data/processed/globe/imagery"
        manifest = folder/"manifest.json"
        if not manifest.exists():
            self.skipTest("Local pyramid is optional in minimal CI deployments")
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertGreaterEqual(meta["equatorial_m_per_pixel"], 1000)
        count = 0
        for level in range(meta["max_level"]+1):
            for y in range(2**level):
                for x in range(2**(level+1)):
                    self.assertTrue((folder/f"{level}/{y}/{x}.jpg").is_file())
                    count += 1
        self.assertEqual(meta["tiles"], count)


if __name__ == "__main__":
    unittest.main()
