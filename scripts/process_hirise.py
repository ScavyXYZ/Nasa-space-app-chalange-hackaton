"""Acquire/process a native 1m HiRISE window, never the entire 1.84GB mosaic.

Source strip GeoTIFF has a standard parallel of 0 degrees (NOT the CTX DEM's
18.4663 degrees). Keep both terrain grids separate. A halo supplies derivative
neighbours; original sampled elevations and NoData remain in the raw window.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window

from download_nasa_data import checksum
from inspect_hirise import URL
from process_dem import derive_slope

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/hirise/jezero_hirise_source_window.tif"
OUT = ROOT / "data/processed/hirise"
ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
           CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_TIMEOUT="60",
           GDAL_HTTP_MAX_RETRY="2")


def acquire(size_m, lon, lat):
    RAW.parent.mkdir(parents=True, exist_ok=True)
    provenance_path = RAW.with_suffix(".json")
    if RAW.exists():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance["selection"] != dict(size_m=size_m, lon=lon, lat=lat):
            raise ValueError("Existing raw acquisition uses another AOI; retain it and choose a separate output directory.")
        if checksum(RAW) != provenance["sha256"]:
            raise ValueError("Raw HiRISE window checksum changed")
        return provenance
    with rasterio.Env(**ENV), rasterio.open(URL) as src:
        crs = CRS(src.crs)
        assert crs.ellipsoid.semi_major_metre == 3396190
        assert np.allclose(src.res, [1, 1])
        # In this projection native 1m east-west spacing on the sphere is
        # cos(latitude) metres. Selection size is in projected metres.
        fwd = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
        x, y = fwd.transform(lon, lat)
        row, col = src.index(x, y)
        n = int(size_m)
        window = Window(col-n//2-1, row-n//2-1, n+2, n+2)
        if window.intersection(Window(0, 0, src.width, src.height)) != window:
            raise ValueError("Requested window exceeds HiRISE mosaic bounds")
        print(f"Reading {n+2}x{n+2} pixels plus halo via HTTP Range; no global/full mosaic download.", flush=True)
        raw_data = src.read(1, window=window)
        profile = src.profile.copy()
        profile.update(width=n+2, height=n+2, transform=src.window_transform(window),
                       tiled=True, blockxsize=256, blockysize=256, compress="deflate")
        temp = RAW.with_suffix(".part.tif")
        with rasterio.open(temp, "w", **profile) as dst:
            dst.write(raw_data, 1)
            dst.update_tags(source_url=URL, acquisition="Unresampled source pixel window with 1-pixel halo")
        with rasterio.open(temp) as check:
            if not np.array_equal(raw_data, check.read(1)):
                raise ValueError("Saved source window differs from remote source pixels")
        temp.rename(RAW)
        provenance = {
            "source_url": URL,
            "source_page": "https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_hirise_dtm_mosaic",
            "source_full_size_bytes": 1839545409,
            "source_window_col_row_width_height": list(window.flatten()),
            "selection": dict(size_m=size_m, lon=lon, lat=lat),
            "source_dimensions": [src.height, src.width], "source_block_shape": list(src.block_shapes[0]),
            "raw_path": RAW.relative_to(ROOT).as_posix(),
            "raw_file_bytes": RAW.stat().st_size, "sha256": checksum(RAW),
            "preservation": "Unresampled source values and NoData preserved in local window; this is NOT the complete original TIFF.",
            "transfer_note": "GDAL reads full width strips for the selected rows; transfer exceeds 4MB pixel window. Approximately 86MB strip payload for 1002 rows, not a measured network byte count."
        }
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        return provenance


def process(provenance):
    OUT.mkdir(parents=True, exist_ok=True)
    with rasterio.open(RAW) as src:
        crs = CRS(src.crs)
        z_halo = src.read(1, masked=True).filled(np.nan)
        # Standard parallel 0, and real local Mars distances, not Earth CRS.
        s_halo, valid_halo, scale_halo = derive_slope(z_halo, src.transform, standard_parallel_deg=0)
        z = z_halo[1:-1, 1:-1].copy()
        slope = s_halo[1:-1, 1:-1].copy()
        source_valid = np.isfinite(z)
        valid = valid_halo[1:-1, 1:-1]
        z[~valid] = np.nan
        slope[~valid] = np.nan
        if valid.mean() < 0.9:
            raise ValueError(f"Insufficient native HiRISE coverage: {valid.mean():.1%}; select another AOI explicitly")
        window = Window(1, 1, z.shape[1], z.shape[0])
        transform = src.window_transform(window)
        profile = src.profile.copy()
        profile.update(width=z.shape[1], height=z.shape[0], transform=transform)
        with rasterio.open(OUT / "jezero_hirise_dem_crop.tif", "w", **profile) as dst:
            dst.write(np.where(valid, z, src.nodata), 1)
            dst.update_tags(elevation_units="metres", source_url=URL)
        profile.update(nodata=-9999)
        with rasterio.open(OUT / "jezero_hirise_slope.tif", "w", **profile) as dst:
            dst.write(np.where(valid, slope, -9999), 1)
            dst.update_tags(slope_units="degrees", method="Central finite differences; 1px halo; Mars metric correction")
        np.save(OUT / "jezero_hirise_elevation.npy", z)
        np.save(OUT / "jezero_hirise_slope.npy", slope)
        np.save(OUT / "jezero_hirise_valid_mask.npy", valid.astype("uint8"))
        np.save(OUT / "jezero_hirise_source_valid_mask.npy", source_valid)
        geo = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        bounds = rasterio.windows.bounds(window, src.transform)
        west, south = geo.transform(bounds[0], bounds[1])
        east, north = geo.transform(bounds[2], bounds[3])
        scale = scale_halo[1:-1]
        metadata = {
            "source": "USGS Mars 2020 TRN HiRISE DTM Mosaic",
            "source_url": URL, "acquisition": provenance,
            "shape_rows_cols": list(z.shape), "pixel_size_m": [1, 1],
            "pixel_size_semantics": "Projected metres; east-west spherical ground spacing corrected below",
            "east_west_ground_cell_size_range_m": [float(scale.min()), float(scale.max())],
            "crs_wkt": crs.to_wkt(), "geographic_crs_wkt": crs.geodetic_crs.to_wkt(),
            "mars_radius_m": 3396190, "standard_parallel_deg": 0,
            "transform": list(transform), "bounds_projected_m": list(bounds),
            "bounds_lon_lat_deg": [west, south, east, north],
            "coordinate_semantics": "Mars planetocentric latitude; east-positive longitude; NOT WGS84",
            "elevation_units": "m", "nodata": src.nodata, "slope_nodata": -9999,
            "vertical_reference": "Source MOLA topography / DeltaGeoid product; no vertical datum transformation applied; do not assume zero offset to CTX",
            "slope_units": "degrees",
            "slope_method": "Central differences with 1-pixel source halo; dx_ground=1*cos(latitude), dy_ground=1 metre",
            "valid_cells": int(valid.sum()), "valid_fraction": float(valid.mean()),
            "source_valid_fraction": float(source_valid.mean()),
            "elevation_range_m": [float(np.nanmin(z)), float(np.nanmax(z))],
            "slope_range_deg": [float(np.nanmin(slope)), float(np.nanmax(slope))],
            "integration": "Separate high-detail grid; use terrain_coordinates.TerrainCoordinates with this metadata path. Do not index with CTX rows/cols.",
            "caveats": ["1m sampling is not 1m absolute accuracy or safety certification.",
                        "No interpolation of voids; derivative-adjacent invalid cells blocked.",
                        "Geology registration uncertainty remains 100–200m; do not infer metre-accurate contacts."]
        }
    (OUT / "terrain_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (ROOT / "data/hirise_download_manifest.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for ax, arr, title, cmap in zip(axes, [z, slope], ["HiRISE elevation (m)", "HiRISE slope (degrees)"], ["terrain", "magma"]):
        im = ax.imshow(arr, extent=[west,east,south,north], cmap=cmap)
        ax.set_title(title)
        ax.set_xlabel("East longitude (Mars)")
        ax.set_ylabel("Planetocentric latitude")
        fig.colorbar(im, ax=ax, shrink=0.75)
    fig.savefig(OUT / "hirise_quality_check.png", dpi=140)
    plt.close(fig)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-m", type=int, default=1000)
    parser.add_argument("--lon", type=float, default=77.4508)
    parser.add_argument("--lat", type=float, default=18.4447)
    args = parser.parse_args()
    if not 20 <= args.size_m <= 2000:
        parser.error("Use 20–2000 projected metres to bound transfer and memory")
    process(acquire(args.size_m, args.lon, args.lat))
