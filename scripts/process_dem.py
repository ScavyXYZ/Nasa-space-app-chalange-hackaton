"""Crop the USGS Jezero CTX DEM and derive slope/A* inputs.

Default AOI is a 5 km square around Perseverance's published landing location.
The source mosaic uses a Mars spherical equirectangular projection; all slope
distances are computed in its metre units, not from angular coordinates.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/dem/M20_JezeroCrater_CTXDEM_20m.tif"
OUT = ROOT / "data/processed"
# Design-selected AOI centre near Perseverance's landing area, not a science POI.
LANDING_LAT = 18.4447
LANDING_LON = 77.4508
MARS_RADIUS_M = 3_396_190.0
STANDARD_PARALLEL = 18.4663


def derive_slope(elevation, transform):
    """Central gradients in local Mars surface metres; NaNs remain blocked."""
    dz_dy, dz_dx = np.gradient(elevation, abs(transform.e), abs(transform.a))
    lat_rows = (transform.f + (np.arange(elevation.shape[0]) + 0.5) * transform.e) / MARS_RADIUS_M
    east_scale = np.cos(lat_rows) / np.cos(np.deg2rad(STANDARD_PARALLEL))
    slope = np.degrees(np.arctan(np.hypot(dz_dx / east_scale[:, None], dz_dy))).astype("float32")
    valid = np.isfinite(elevation) & np.isfinite(slope)
    slope[~valid] = np.nan
    return slope, valid, east_scale


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--size-km", type=float, default=5.0)
    args = parser.parse_args()
    if args.size_km <= 0:
        parser.error("--size-km must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(args.source) as src:
        if "Mars_2000" not in src.crs.to_wkt() and "Mars" not in src.crs.to_wkt():
            raise ValueError(f"Unexpected non-Martian CRS: {src.crs}")
        # Spherical equirectangular coordinates, consistent with this mosaic's
        # standard parallel and east-positive longitude.
        x = MARS_RADIUS_M * np.deg2rad(LANDING_LON) * np.cos(np.deg2rad(STANDARD_PARALLEL))
        y = MARS_RADIUS_M * np.deg2rad(LANDING_LAT)
        half = args.size_km * 500
        win = from_bounds(x-half, y-half, x+half, y+half, src.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        arr = src.read(1, window=win, masked=True).astype("float32")
        if arr.size == 0 or arr.count() == 0:
            raise ValueError("Selected AOI has no valid DEM pixels; check landing-point datum/coordinates.")
        transform = src.window_transform(win)
        profile = src.profile.copy()
        profile.update(width=arr.shape[1], height=arr.shape[0], transform=transform,
                       compress="deflate", tiled=True, blockxsize=256, blockysize=256)
        # Central finite differences (one-sided at outer edges); nodata
        # neighbours are masked so slopes adjacent to voids are not fabricated.
        z = arr.filled(np.nan)
        valid = ~np.ma.getmaskarray(arr)
        # Equirectangular x-distance scale varies with latitude. Correct the
        # derivative from map metres to local surface metres on the Mars sphere.
        slope, slope_valid, east_scale = derive_slope(z, transform)
        # Keep a common mask on all routing outputs; preserve the source mask
        # separately so derivative-neighbour exclusions can be distinguished.
        np.save(OUT / "jezero_source_valid_mask.npy", valid)
        z[~slope_valid] = np.nan
        with rasterio.open(OUT / "jezero_dem_crop.tif", "w", **profile) as dst:
            dst.write(np.where(slope_valid, z, src.nodata), 1)
            dst.update_tags(elevation_units="metres", source=args.source.name)
        sp = profile.copy()
        sp.update(dtype="float32", nodata=-9999.0)
        with rasterio.open(OUT / "jezero_slope.tif", "w", **sp) as dst:
            dst.write(np.where(slope_valid, slope, -9999.0), 1)
        np.save(OUT / "jezero_elevation.npy", z.astype("float32"))
        np.save(OUT / "jezero_slope.npy", slope)
        np.save(OUT / "jezero_valid_mask.npy", (valid & slope_valid).astype("uint8"))
        metadata = {
            "source": "USGS Astrogeology Mars 2020 Science Investigation CTX DEM Mosaic",
            "source_url": "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif",
            "shape_rows_cols": list(arr.shape), "pixel_size_m": [abs(transform.a), abs(transform.e)],
            "crs_wkt": src.crs.to_wkt(), "transform": list(transform),
            "nodata": src.nodata, "elevation_units": "m",
            "aoi_center_source": "Design-selected coordinate near landing area, not a surveyed scientific target",
            "aoi_center_lat_lon_planetocentric_deg": [LANDING_LAT, LANDING_LON],
            "aoi_size_km": args.size_km,
            "valid_pixels": int(valid.sum()), "total_pixels": int(valid.size),
            "elevation_min_m": float(arr.min()), "elevation_max_m": float(arr.max()),
            "slope_units": "degrees", "slope_method": "Central differences with one-sided outer edges; east-west distances corrected by cos(latitude)/cos(18.4663deg)",
            "mars_radius_m": MARS_RADIUS_M, "standard_parallel_deg": STANDARD_PARALLEL,
            "east_west_ground_cell_size_range_m": [float(20*east_scale.min()), float(20*east_scale.max())],
            "vertical_reference": "USGS product description: DEM additions localized vertically to MOLA; original values retained, no vertical datum conversion",
            "caveat": "Modelled slope; not a safety assessment. DEM coverage/voids remain masked."
        }
        crs = CRS(src.crs)
        geo = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        left, bottom, right, top = rasterio.windows.bounds(win, src.transform)
        metadata["bounds_projected_m"] = [left, bottom, right, top]
        metadata["bounds_lon_lat_deg"] = [*geo.transform(left, bottom), *geo.transform(right, top)]
        metadata["geographic_crs_wkt"] = crs.geodetic_crs.to_wkt()
        (OUT / "terrain_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
