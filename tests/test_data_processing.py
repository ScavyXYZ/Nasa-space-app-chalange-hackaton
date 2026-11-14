"""Synthetic mathematics tests ONLY; these are not Mars observations."""
import sys
import unittest
from pathlib import Path

import numpy as np
from affine import Affine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from process_dem import derive_slope, MARS_RADIUS_M, STANDARD_PARALLEL
from terrain_coordinates import TerrainCoordinates


class SlopeTests(unittest.TestCase):
    def setUp(self):
        self.transform = Affine(20, 0, 0, 0, -20, MARS_RADIUS_M*np.deg2rad(STANDARD_PARALLEL)+10)

    def test_flat(self):
        s, valid, _ = derive_slope(np.ones((11, 11))*123, self.transform)
        self.assertTrue(valid.all())
        np.testing.assert_array_equal(s, 0)

    def test_north_south_plane(self):
        z = np.broadcast_to(np.arange(11)[:, None]*20, (11, 11)).astype(float)
        s, valid, _ = derive_slope(z, self.transform)
        np.testing.assert_allclose(s, 45)

    def test_east_west_plane_scale(self):
        z = np.broadcast_to(np.arange(11)[None, :]*20, (11, 11)).astype(float)
        s, _, scale = derive_slope(z, self.transform)
        np.testing.assert_allclose(s[:, 5], np.rad2deg(np.arctan(1/scale)), atol=1e-5)

    def test_void_not_interpolated(self):
        z = np.ones((11, 11))
        z[4:7, 4:7] = np.nan
        s, valid, _ = derive_slope(z, self.transform)
        self.assertFalse(valid[4:7, 4:7].any())
        self.assertFalse(valid[3, 5])
        self.assertTrue(np.isnan(s[4:7, 4:7]).all())
        self.assertTrue(valid[0, 0])

    def test_hirise_zero_standard_parallel(self):
        z = np.broadcast_to(np.arange(11)[None, :]*20, (11, 11)).astype(float)
        s, valid, scale = derive_slope(z, self.transform, standard_parallel_deg=0)
        self.assertTrue(valid.all())
        np.testing.assert_allclose(s[:, 5], np.rad2deg(np.arctan(1/scale)), atol=1e-5)
        # This latitude requires ~cos(18.47deg) scale, not CTX's ~1 scale.
        self.assertTrue(np.all(scale < 0.95))

    def test_real_coordinate_roundtrips(self):
        coords = TerrainCoordinates()
        for row, col in [(0, 0), (125, 125), (249, 249)]:
            self.assertEqual((row, col), coords.lonlat_to_pixel(*coords.pixel_to_lonlat(row, col)))

    def test_outside_is_not_clamped(self):
        with self.assertRaises(ValueError):
            TerrainCoordinates().lonlat_to_pixel(0, 0)


if __name__ == "__main__":
    unittest.main()
