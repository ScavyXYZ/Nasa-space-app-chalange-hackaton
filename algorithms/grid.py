"""Input contract for the routing code and an adapter for prepared Jezero data."""

from pathlib import Path
from typing import Protocol

import numpy as np

Cell = tuple[int, int]  # row, column
LonLat = tuple[float, float]


class GridGeometry(Protocol):
    """Distances in metres must be metric (including the triangle inequality)."""

    def pixel_to_lonlat(self, row: int, col: int) -> LonLat: ...
    def lonlat_to_pixel(self, lon: float, lat: float) -> Cell: ...
    def distance_m(self, a: Cell, b: Cell) -> float: ...


class MarsRasterGeometry:
    """Cache coordinate transforms and neighbour distances on a regular Mars grid."""

    def __init__(self, metadata_path: Path | None = None, *, terrain=None):
        from scripts.terrain_coordinates import TerrainCoordinates

        self.coordinates = TerrainCoordinates(metadata_path) if terrain is None else terrain
        if terrain is None:
            self._index = self.coordinates.lonlat_to_pixel
            centre = self.coordinates.pixel_to_lonlat
            self.shape = tuple(self.coordinates.meta["shape_rows_cols"])
        else:
            self._index = terrain.index
            centre = terrain.lonlat
            self.shape = terrain.shape
        rows, cols = self.shape
        affine = self.coordinates.affine
        operation = self.coordinates.crs.coordinate_operation
        if (affine.b != 0 or affine.d != 0 or operation is None
                or not operation.method_name.startswith("Equidistant Cylindrical")):
            raise ValueError("Expected an unrotated equirectangular Mars raster")
        self._lons = [centre(0, col)[0] for col in range(cols)]
        self._lats = [centre(row, 0)[1] for row in range(rows)]
        self._horizontal = [self._geodesic((r, 0), (r, 1)) for r in range(rows)] if cols > 1 else []
        self._vertical = [self._geodesic((r, 0), (r + 1, 0)) for r in range(rows - 1)]
        self._diagonal = ([self._geodesic((r, 0), (r + 1, 1)) for r in range(rows - 1)]
                          if cols > 1 else [])
        self._min_horizontal = min(self._horizontal, default=0.0)
        self._min_vertical = min(self._vertical, default=0.0)
        self._min_diagonal = min(self._diagonal, default=self._min_horizontal + self._min_vertical)

    def lower_bound_m(self, a: Cell, b: Cell) -> float:
        """Admissible octile bound for this eight-neighbour raster.

        Each edge is no cheaper than the global minimum for its direction.
        This is a relaxed grid, not a replacement for Mars edge measurements.
        Lowering axis costs to the diagonal cost also keeps the norm valid on
        unusually anisotropic rasters. No terrain samples are approximated.
        """
        dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
        h = min(self._min_horizontal, self._min_diagonal)
        v = min(self._min_vertical, self._min_diagonal)
        diagonal = min(self._min_diagonal, h + v)
        return h * dc + v * dr + (diagonal - h - v) * min(dr, dc)

    def pixel_to_lonlat(self, row: int, col: int) -> LonLat:
        return self._lons[col], self._lats[row]

    def lonlat_to_pixel(self, lon: float, lat: float) -> Cell:
        return self._index(lon, lat)

    def _geodesic(self, a: Cell, b: Cell) -> float:
        return self.coordinates.geod.inv(*self.pixel_to_lonlat(*a), *self.pixel_to_lonlat(*b))[2]

    def distance_m(self, a: Cell, b: Cell) -> float:
        dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
        if dr == 0 and dc == 1:
            return self._horizontal[a[0]]
        if dr == 1:
            if dc == 0:
                return self._vertical[min(a[0], b[0])]
            if dc == 1:
                return self._diagonal[min(a[0], b[0])]
        return self._geodesic(a, b)


def load_jezero_grid(folder: Path, prefix: str = "jezero"):
    """Return elevation, slope, validity mask and geometry for a prepared DEM."""
    folder = Path(folder)
    arrays = tuple(np.load(folder / f"{prefix}_{name}.npy", allow_pickle=False)
                   for name in ("elevation", "slope", "valid_mask"))
    geometry = MarsRasterGeometry(folder / "terrain_metadata.json")
    if any(array.shape != geometry.shape for array in arrays):
        raise ValueError("Prepared raster arrays do not match their metadata")
    return (*arrays, geometry)
