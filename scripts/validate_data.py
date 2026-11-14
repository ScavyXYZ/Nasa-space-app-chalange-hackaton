"""Validate the complete handoff. Any failure exits nonzero and is reported.

Use --online to additionally check official metadata URLs. No silent incomplete
success: geology, scientific regions, imagery, provenance and masks are required.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import CRS, Transformer
from rasterio.windows import from_bounds
from shapely.geometry import shape, box
from shapely.ops import transform
from pyogrio.raw import read
from shapely import from_wkb, make_valid

from download_nasa_data import checksum
from terrain_coordinates import TerrainCoordinates

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data/processed"


def validate(online=False):
    required = ["jezero_dem_crop.tif", "jezero_slope.tif", "jezero_elevation.npy",
                "jezero_slope.npy", "jezero_valid_mask.npy", "terrain_metadata.json",
                "geology.geojson", "geology_legend.json", "imagery_config.json",
                "jezero_ctx_crop.tif", "jezero_ctx_overlay.png", "terrain_quality_check.png"]
    assert all((P / f).is_file() for f in required), "Missing required outputs"
    manifest = json.loads((ROOT / "data/download_manifest.json").read_text())
    for item in manifest:
        path = ROOT / item["path"]
        assert path.stat().st_size == item["bytes"]
        assert checksum(path) == item["sha256"], f"Original altered: {path}"
    with rasterio.open(P / "jezero_dem_crop.tif") as dem, rasterio.open(P / "jezero_slope.tif") as slope:
        crs = CRS(dem.crs)
        assert "Mars" in crs.geodetic_crs.name
        assert crs.ellipsoid.semi_major_metre == 3396190
        assert crs.ellipsoid.semi_minor_metre == 3396190
        assert crs.is_projected and crs.axis_info[0].unit_name == "metre"
        assert np.allclose(dem.res, [20, 20])
        z = np.load(P / "jezero_elevation.npy")
        s = np.load(P / "jezero_slope.npy")
        m = np.load(P / "jezero_valid_mask.npy").astype(bool)
        assert z.shape == s.shape == m.shape == (dem.height, dem.width)
        assert slope.crs == dem.crs and slope.transform == dem.transform
        assert slope.shape == dem.shape
        assert np.any(m), "No valid A* cells"
        assert np.array_equal(np.isfinite(z), m) and np.array_equal(np.isfinite(s), m)
        assert np.array_equal(dem.read_masks(1) != 0, m)
        assert np.array_equal(slope.read_masks(1) != 0, m)
        assert np.array_equal(dem.read(1)[m], z[m])
        assert np.array_equal(slope.read(1)[m], s[m])
        assert dem.nodata is not None and slope.nodata is not None
        with rasterio.open(ROOT / "data/raw/dem/M20_JezeroCrater_CTXDEM_20m.tif") as raw:
            win = from_bounds(*dem.bounds, raw.transform).round_offsets().round_lengths()
            orig = raw.read(1, window=win, masked=True)
            assert np.array_equal(orig.data[m], z[m]), "Crop altered source heights"
            assert np.array_equal(np.load(P / "jezero_source_valid_mask.npy"), ~np.ma.getmaskarray(orig))
        # Independent central-difference recomputation for real interior cells.
        lat = (dem.transform.f + (np.arange(dem.height)+0.5)*dem.transform.e) / 3396190
        dx = 20*np.cos(lat)/np.cos(np.deg2rad(18.4663))
        source_z = orig.filled(np.nan)
        gx = (source_z[1:-1, 2:] - source_z[1:-1, :-2]) / (2*dx[1:-1, None])
        gy = (source_z[2:, 1:-1] - source_z[:-2, 1:-1])/40
        expected = np.degrees(np.arctan(np.sqrt(gx**2+gy**2)))
        interior_valid = m[1:-1, 1:-1]
        assert np.allclose(s[1:-1, 1:-1][interior_valid], expected[interior_valid], atol=1e-4)
        assert np.all((s[m] >= 0) & (s[m] <= 90))
        coord = TerrainCoordinates()
        for row, col in [(0, 0), (dem.height-1, dem.width-1), (100, 150)]:
            assert coord.lonlat_to_pixel(*coord.pixel_to_lonlat(row, col)) == (row, col)
        assert 19.9 < coord.distance_m((100, 100), (100, 101)) < 20.1
        try:
            coord.lonlat_to_pixel(0, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("Out-of-bounds point accepted")
        # A* smoke test: BFS reachability on the same 4-connected valid mask.
        # No slope safety threshold imposed here.
        from collections import deque
        start, goal = (0, 0), (dem.height-1, dem.width-1)
        queue, visited = deque([start]), {start}
        while queue and goal not in visited:
            r, c = queue.popleft()
            for rr, cc in [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]:
                if 0 <= rr < dem.height and 0 <= cc < dem.width and m[rr,cc] and (rr,cc) not in visited:
                    visited.add((rr,cc))
                    queue.append((rr,cc))
        assert goal in visited, "No valid-grid path across demonstration AOI"
        geo = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
        aoi = box(*dem.bounds).buffer(0.001)
        geology = json.loads((P / "geology.geojson").read_text(encoding="utf-8"))
        pois = json.loads((ROOT / "science/points_of_interest.geojson").read_text(encoding="utf-8"))
        assert geology["features"] and len(pois["features"]) >= 3
        source_fids = {f["properties"]["source_fid"] for f in geology["features"]}
        gdb = next((ROOT / "data/raw/geology/extracted").rglob("*.gdb"))
        raw_meta, raw_fids, raw_wkbs, raw_attrs = read(gdb, layer="GeoUnits_v1", return_fids=True)
        original = {int(fid): (wkb, {field: values[i] for field, values in zip(raw_meta["fields"], raw_attrs)})
                    for i, (fid, wkb) in enumerate(zip(raw_fids, raw_wkbs))}
        raw_to_dem = Transformer.from_crs(raw_meta["crs"], crs, always_xy=True)
        for f in geology["features"]:
            props = f["properties"]
            raw_wkb, raw_properties = original[props["source_fid"]]
            assert props["name"] == raw_properties["name"]
            assert props["unit"] == raw_properties["unit"]
            raw_geom = transform(raw_to_dem.transform, make_valid(from_wkb(raw_wkb)))
            expected_geom = raw_geom.intersection(box(*dem.bounds))
            delivered = transform(geo.transform, shape(f["geometry"]))
            assert delivered.symmetric_difference(expected_geom).area < 0.01, "Source geometry altered"
        for f in geology["features"] + pois["features"]:
            g = shape(f["geometry"])
            assert g.is_valid and not g.is_empty
            assert aoi.covers(transform(geo.transform, g)), "Geology outside AOI"
            assert f["properties"]["source"] == "https://doi.org/10.3133/sim3464"
        for f in pois["features"]:
            props = f["properties"]
            assert all(props.get(k) for k in ["name", "description", "research_interest", "source_layer", "source_fids"])
            assert set(props["source_fids"]).issubset(source_fids)
        config = json.loads((P / "imagery_config.json").read_text())
        assert config["valid_fraction"] > 0.95
        with rasterio.open(P / "jezero_ctx_crop.tif") as optical:
            assert optical.crs == dem.crs
            assert np.allclose(optical.bounds, dem.bounds)
            assert optical.read(1).max() > optical.read(1).min()
        result = {"status": "passed", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                  "shape": list(z.shape), "valid_cells": int(m.sum()),
                  "elevation_range_m": [float(z[m].min()), float(z[m].max())],
                  "slope_range_deg": [float(s[m].min()), float(s[m].max())],
                  "geology_features": len(geology["features"]), "science_regions": len(pois["features"]),
                  "imagery_valid_fraction": config["valid_fraction"],
                  "checks": ["source_sha256", "Mars_CRS", "20m_pixels", "source_height_preservation",
                             "common_masks", "slope_independent_recalculation", "coordinate_roundtrip",
                             "Mars_distance", "out_of_bounds_rejection", "routing_grid_connectivity",
                             "geology_validity_and_bounds", "science_region_provenance", "optical_coverage"]}
    if online:
        urls = [
            "https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic",
            "https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_context_camera_orthorectified_image_mosaic",
            "https://pubs.usgs.gov/publication/sim3464",
            "https://pubs.usgs.gov/sim/3464/sim3464_readme.txt",
            "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars",
        ]
        result["online_sources"] = []
        for url in urls:
            response = requests.get(url, timeout=(20, 60))
            response.raise_for_status()
            result["online_sources"].append({"url": url, "http_status": response.status_code})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(args.online)
    except Exception as exc:
        (P / "validation_report.json").write_text(
            json.dumps({"status": "failed", "error": str(exc)}, indent=2), encoding="utf-8")
        raise
    (P / "validation_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
