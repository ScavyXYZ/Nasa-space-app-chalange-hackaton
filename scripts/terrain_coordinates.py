"""Backend/A* coordinate helpers. Reject points outside the raster.

Mars coordinates use planetocentric latitude and east-positive longitude.
"""
import json
from pathlib import Path
from affine import Affine
from pyproj import CRS, Transformer


class TerrainCoordinates:
    def __init__(self, metadata_path=None):
        path = metadata_path or Path(__file__).resolve().parents[1] / "data/processed/terrain_metadata.json"
        self.meta = json.loads(Path(path).read_text(encoding="utf-8"))
        self.affine = Affine(*self.meta["transform"][:6])
        self.crs = CRS(self.meta["crs_wkt"])
        self.forward = Transformer.from_crs(self.crs.geodetic_crs, self.crs, always_xy=True)
        self.inverse = Transformer.from_crs(self.crs, self.crs.geodetic_crs, always_xy=True)
        self.geod = self.crs.get_geod()

    def pixel_to_lonlat(self, row, col):
        self._check(row, col)
        return self.inverse.transform(*(self.affine * (col + 0.5, row + 0.5)))

    def lonlat_to_pixel(self, lon, lat):
        import math
        col, row = ~self.affine * self.forward.transform(lon, lat)
        row, col = math.floor(row), math.floor(col)
        self._check(row, col)
        return row, col

    def _check(self, row, col):
        h, w = self.meta["shape_rows_cols"]
        if not (0 <= row < h and 0 <= col < w):
            raise ValueError("Coordinate outside the selected terrain")

    def distance_m(self, a, b):
        """a,b are (row,col). Use actual Mars spherical distance."""
        p, q = self.pixel_to_lonlat(*a), self.pixel_to_lonlat(*b)
        return self.geod.inv(*p, *q)[2]
