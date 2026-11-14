"""Read-only access to prepared Mars grids. No Earth fallback or void filling."""
import json
import math
from pathlib import Path

import numpy as np
from affine import Affine
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "ctx": ("data/processed", "jezero"),
    "hirise": ("data/processed/hirise", "jezero_hirise"),
}


class TerrainError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


class TerrainGrid:
    """Arrays are indexed [row,col]. Point lookup uses containing cell, not interpolation."""
    def __init__(self, directory, prefix, dataset="custom"):
        directory = Path(directory)
        self.dataset = dataset
        try:
            self.metadata = json.loads((directory / "terrain_metadata.json").read_text(encoding="utf-8"))
            self.elevation = np.load(directory / f"{prefix}_elevation.npy", mmap_mode="r")
            self.slope = np.load(directory / f"{prefix}_slope.npy", mmap_mode="r")
            self.valid = np.load(directory / f"{prefix}_valid_mask.npy", mmap_mode="r")
        except (OSError, ValueError) as exc:
            raise TerrainError("dataset_unavailable", f"Dataset '{dataset}' is missing or unreadable; run data preparation.", 503) from exc
        required = {"crs_wkt","transform","shape_rows_cols","pixel_size_m"}
        if not required.issubset(self.metadata):
            raise TerrainError("invalid_dataset", "Terrain metadata is incomplete", 503)
        self.crs = CRS(self.metadata["crs_wkt"])
        if not self.crs.is_projected or self.crs.ellipsoid.semi_major_metre != 3396190 or self.crs.ellipsoid.semi_minor_metre != 3396190:
            raise TerrainError("invalid_dataset", "Expected projected Mars sphere (radius 3396190 m)", 503)
        if any(axis.unit_conversion_factor != 1 for axis in self.crs.axis_info):
            raise TerrainError("invalid_dataset", "Projected axes must use metres", 503)
        self.affine = Affine(*self.metadata["transform"][:6])
        if self.affine.b != 0 or self.affine.d != 0 or self.affine.a <= 0 or self.affine.e >= 0:
            raise TerrainError("invalid_dataset", "Expected north-up, unrotated terrain", 503)
        self.shape = tuple(self.metadata["shape_rows_cols"])
        if self.elevation.shape != self.slope.shape or self.slope.shape != self.valid.shape or self.shape != self.valid.shape:
            raise TerrainError("invalid_dataset", "Terrain array shapes disagree", 503)
        if not np.allclose([self.affine.a, -self.affine.e], self.metadata["pixel_size_m"]):
            raise TerrainError("invalid_dataset", "Pixel size differs from affine", 503)
        finite = np.isfinite(self.elevation) & np.isfinite(self.slope)
        if not np.array_equal(finite, self.valid.astype(bool)) or not np.isin(self.valid, [0, 1]).all():
            raise TerrainError("invalid_dataset", "Terrain masks disagree or contain invalid values", 503)
        if not self.valid.any() or np.any(self.slope[finite] < 0) or np.any(self.slope[finite] > 90):
            raise TerrainError("invalid_dataset", "No usable cells or slope outside [0,90]", 503)
        self.forward = Transformer.from_crs(self.crs.geodetic_crs, self.crs, always_xy=True)
        self.inverse = Transformer.from_crs(self.crs, self.crs.geodetic_crs, always_xy=True)
        self.geod = self.crs.get_geod()
        self.north_spacing = abs(self.affine.e)
        scales = self.metadata.get("east_west_ground_cell_size_range_m", [self.affine.a])
        self.min_ground_spacing = min(self.north_spacing, *scales)

    @classmethod
    def load(cls, dataset="ctx", root=ROOT):
        if dataset not in DATASETS:
            raise TerrainError("unknown_dataset", "Choose 'ctx' or 'hirise'")
        directory, prefix = DATASETS[dataset]
        return cls(Path(root) / directory, prefix, dataset)

    def fractional_pixel(self, lon, lat):
        if not math.isfinite(lon) or not math.isfinite(lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise TerrainError("invalid_coordinate", "Expected finite Mars longitude/latitude in degrees")
        x, y = self.forward.transform(lon, lat)
        col, row = ~self.affine * (x, y)
        return row, col

    def index(self, lon, lat):
        row, col = self.fractional_pixel(lon, lat)
        if not (0 <= row < self.shape[0] and 0 <= col < self.shape[1]):
            raise TerrainError("outside_coverage", f"Point is outside '{self.dataset}' terrain; no automatic CTX/HiRISE fallback")
        return math.floor(row), math.floor(col)

    def lonlat(self, row, col):
        if not (0 <= row < self.shape[0] and 0 <= col < self.shape[1]):
            raise TerrainError("outside_coverage", "Cell outside terrain")
        return self.inverse.transform(*(self.affine * (col+0.5, row+0.5)))

    def sample(self, lon, lat):
        row, col = self.index(lon, lat)
        valid = bool(self.valid[row, col])
        centre = self.lonlat(row, col)
        return {"dataset": self.dataset, "lon": lon, "lat": lat, "row": row, "col": col,
                "cell_center": {"lon": centre[0], "lat": centre[1]}, "valid": valid,
                "elevation_m": float(self.elevation[row, col]) if valid else None,
                "slope_deg": float(self.slope[row, col]) if valid else None,
                "sampling": "containing_cell_no_interpolation",
                "coordinate_system": "Mars planetocentric, east-positive degrees"}

    def blocked_mask(self, max_slope_deg=15):
        if not math.isfinite(max_slope_deg) or not 0 <= max_slope_deg <= 90:
            raise TerrainError("invalid_slope", "Model slope threshold must be in [0,90]")
        return ~self.valid.astype(bool) | (self.slope > max_slope_deg)

    def close(self):
        """Release owned read-only mmap handles, including on Windows shutdown."""
        for array in (self.elevation,self.slope,self.valid):
            handle = getattr(array,"_mmap",None)
            if handle is not None:
                handle.close()

    def distance_m(self, a, b):
        """a and b are (lon, lat) in Mars geographic degrees."""
        return float(self.geod.inv(a[0], a[1], b[0], b[1])[2])

    def crossed_cells(self, a, b):
        """Supercover of a short projected segment, including corner-touch cells.

        Used between dense geodesic profile samples to prevent skipping NoData
        or diagonally cutting an unknown corner. Conservative at exact corners.
        """
        r0, c0 = self.fractional_pixel(*a)
        r1, c1 = self.fractional_pixel(*b)
        row, col = self.index(*a)
        end_row, end_col = self.index(*b)
        yield row, col
        dc, dr = c1-c0, r1-r0
        sc = 1 if dc > 0 else -1
        sr = 1 if dr > 0 else -1
        tc = ((col+1-c0) if sc > 0 else (c0-col))/abs(dc) if dc else math.inf
        tr = ((row+1-r0) if sr > 0 else (r0-row))/abs(dr) if dr else math.inf
        dtc = 1/abs(dc) if dc else math.inf
        dtr = 1/abs(dr) if dr else math.inf
        remaining = abs(end_row-row)+abs(end_col-col)+4
        while (row, col) != (end_row, end_col):
            remaining -= 1
            if remaining < 0:
                raise TerrainError("invalid_route","Unable to traverse raster segment numerically; move vertices off exact cell boundaries")
            if math.isclose(tc, tr, rel_tol=0, abs_tol=1e-10):
                yield row, col+sc
                yield row+sr, col
                row, col = row+sr, col+sc
                tr, tc = tr+dtr, tc+dtc
            elif tc < tr:
                col, tc = col+sc, tc+dtc
            else:
                row, tr = row+sr, tr+dtr
            yield row, col
