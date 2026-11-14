"""Validate local HiRISE products and optionally compare native remote samples."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer

from download_nasa_data import checksum
from process_hirise import ENV, URL
from terrain_coordinates import TerrainCoordinates

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed/hirise"


def validate(remote_samples=False):
    metadata = json.loads((OUT / "terrain_metadata.json").read_text(encoding="utf-8"))
    acquisition = metadata["acquisition"]
    raw_path = ROOT / acquisition["raw_path"]
    assert checksum(raw_path) == acquisition["sha256"], "Raw window altered"
    with rasterio.open(raw_path) as raw, \
         rasterio.open(OUT / "jezero_hirise_dem_crop.tif") as dem, \
         rasterio.open(OUT / "jezero_hirise_slope.tif") as slope:
        crs = CRS(dem.crs)
        assert "Mars" in crs.geodetic_crs.name
        assert crs.ellipsoid.semi_major_metre == crs.ellipsoid.semi_minor_metre == 3396190
        assert np.allclose(dem.res, (1, 1))
        assert dem.crs == slope.crs == raw.crs
        assert dem.transform == slope.transform
        assert slope.shape == dem.shape == tuple(metadata["shape_rows_cols"])
        assert dem.transform == raw.window_transform(rasterio.windows.Window(1, 1, dem.width, dem.height))
        z = np.load(OUT / "jezero_hirise_elevation.npy")
        s = np.load(OUT / "jezero_hirise_slope.npy")
        m = np.load(OUT / "jezero_hirise_valid_mask.npy").astype(bool)
        assert z.dtype == s.dtype == np.dtype("float32")
        assert z.shape == s.shape == m.shape == dem.shape
        assert m.mean() >= 0.9
        assert np.array_equal(np.isfinite(z), m) and np.array_equal(np.isfinite(s), m)
        assert np.array_equal(dem.read_masks(1) != 0, m)
        assert np.array_equal(slope.read_masks(1) != 0, m)
        assert dem.nodata == raw.nodata
        assert slope.nodata == -9999
        assert np.array_equal(dem.read(1)[m], z[m])
        assert np.array_equal(slope.read(1)[m], s[m])
        raw_z = raw.read(1, masked=True).filled(np.nan)
        assert np.array_equal(raw_z[1:-1, 1:-1][m], z[m]), "Source heights changed"
        assert np.array_equal(np.isfinite(raw_z[1:-1, 1:-1]),
                              np.load(OUT / "jezero_hirise_source_valid_mask.npy"))
        # Independent 3x3 finite differences from the ORIGINAL halo, including
        # every delivered edge pixel. No reliance on derive_slope here.
        lat = (dem.transform.f + (np.arange(dem.height)+0.5)*dem.transform.e) / 3396190
        dx = np.cos(lat)
        gx = (raw_z[1:-1, 2:] - raw_z[1:-1, :-2]) / (2*dx[:, None])
        gy = (raw_z[2:, 1:-1] - raw_z[:-2, 1:-1]) / 2
        expected_s = np.degrees(np.arctan(np.hypot(gx, gy)))
        expected_valid = np.isfinite(raw_z[1:-1,1:-1]) & np.isfinite(expected_s)
        assert np.array_equal(expected_valid, m)
        assert np.allclose(s[m], expected_s[m], atol=1e-4)
        assert np.all((s[m] >= 0) & (s[m] <= 90))
        coords = TerrainCoordinates(OUT / "terrain_metadata.json")
        pixels = [(0, 0), (dem.height//2, dem.width//2), (dem.height-1, dem.width-1)]
        with rasterio.open(ROOT / "data/processed/jezero_dem_crop.tif") as ctx:
            to_ctx = Transformer.from_crs(dem.crs, ctx.crs, always_xy=True)
            for row, col in pixels:
                assert coords.lonlat_to_pixel(*coords.pixel_to_lonlat(row, col)) == (row, col)
                x, y = to_ctx.transform(*(dem.transform * (col+0.5, row+0.5)))
                assert ctx.bounds.left < x < ctx.bounds.right and ctx.bounds.bottom < y < ctx.bounds.top
        east_spacing = coords.distance_m((100,100),(100,101))
        north_spacing = coords.distance_m((100,100),(101,100))
        assert 0.94 < east_spacing < 0.96 and 0.999 < north_spacing < 1.001
        samples = []
        if remote_samples:
            col0, row0, _, _ = acquisition["source_window_col_row_width_height"]
            with rasterio.Env(**ENV), rasterio.open(URL) as remote:
                assert remote.crs == raw.crs and remote.nodata == raw.nodata
                for row, col in pixels:
                    sample = remote.read(1, window=rasterio.windows.Window(col0+col+1, row0+row+1, 1, 1))[0,0]
                    original = raw_z[row+1,col+1]
                    assert sample == original or (sample == remote.nodata and np.isnan(original))
                    samples.append({"row": row, "col": col, "matches_remote": True})
        result = {
            "status": "passed", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "shape": list(z.shape), "valid_cells": int(m.sum()), "valid_fraction": float(m.mean()),
            "elevation_range_m": [float(z[m].min()),float(z[m].max())],
            "slope_range_deg": [float(s[m].min()),float(s[m].max())],
            "east_west_ground_spacing_m": east_spacing, "north_south_ground_spacing_m": north_spacing,
            "checks": ["source_window_sha256", "Mars_CRS_1m_projected_pixels",
                       "source_heights_and_nodata_preserved", "shared_masks_and_affine",
                       "independent_slope_with_halo", "coordinate_roundtrip",
                       "Mars_ground_distances", "within_CTX_AOI"],
            "remote_samples": samples
        }
    assert (OUT / "hirise_quality_check.png").is_file()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote-samples", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(args.remote_samples)
    except Exception as exc:
        (OUT / "validation_report.json").write_text(
            json.dumps({"status":"failed", "error":str(exc)},indent=2), encoding="utf-8")
        raise
    (OUT / "validation_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
