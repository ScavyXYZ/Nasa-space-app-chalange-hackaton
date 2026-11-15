"""Bounded, connected display mesh. Never used as a routing terrain.

The entire sphere shares one nonuniform lat/lon grid: no independently raised
patches, skirts, cracks or per-tile geometry. Nested axis samples concentrate
vertices near the view; the 2-degree background remains present everywhere.
"""
import math

import numpy as np

from .global_routing import RADIUS
from .mola128 import BANDS, COLS, PPD, TILE_COLS, TILE_ROWS
from .terrain import TerrainError

MAX_LEVEL = 8


def surface_axes(lon, lat, level):
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180
            and -90 <= lat <= 90 and isinstance(level, int) and 0 <= level <= MAX_LEVEL):
        raise TerrainError("invalid_surface", "Некоректний рівень 3D-поверхні.")
    # Dyadic steps line up between levels. Never refine beyond 1/128 degree.
    half = 64 / 2**level
    quantum = half / 4
    lon = round(lon / quantum) * quantum
    lat = max(-90, min(90, round(lat / quantum) * quantum))
    xs = list(np.arange(-180, 181, 2, dtype=float))
    ys = list(np.arange(-90, 91, 2, dtype=float))
    for depth in range(1, level + 1):
        extent = 64 / 2**depth
        steps = min(128, round(2 * extent * PPD)) if depth == level else 32
        offsets = np.linspace(-extent, extent, steps + 1)
        xs.extend(((lon + offsets + 180) % 360 - 180).tolist())
        ys.extend(np.clip(lat + offsets, -90, 90).tolist())
    x = np.unique(xs)
    y = np.unique(ys)[::-1].copy()
    return x, y, (lon, lat, half)


def native_values(store, rows, cols, kind):
    """Sparse Cartesian sampling without mapping/reading giant rectangular AOIs."""
    output = np.zeros((len(rows), len(cols)), dtype=np.float32)
    for index, band in enumerate(BANDS):
        top = 2 * PPD + index * TILE_ROWS
        ri = np.flatnonzero((rows >= top) & (rows < top + TILE_ROWS))
        if not len(ri):
            continue
        for west in range(0, 360, 90):
            left = west * PPD
            ci = np.flatnonzero((cols >= left) & (cols < left + TILE_COLS))
            if len(ci):
                output[np.ix_(ri, ci)] = store._tile(band, west, kind)[
                    np.ix_(rows[ri] - top, cols[ci] - left)]
    return output


def planet_surface(store, coarse, lon, lat, level):
    x, y, focus = surface_axes(lon, lat, level)
    # MEGDR centres are (column+.5)/128 and 90-(row+.5)/128.
    ry = (90 - y) * PPD - .5
    cx = (x % 360) * PPD - .5
    r0 = np.floor(ry).astype(int)
    c0 = np.floor(cx).astype(int)
    fy, fx = ry - r0, cx - c0
    # At the measured coverage boundary clamp to its last centre. Do not let
    # an uncovered polar bin (or a zero placeholder) contaminate a measured row.
    first, last = 2 * PPD, 178 * PPD - 1
    r0c, r1c = np.clip(r0, first, last), np.clip(r0 + 1, first, last)
    a = native_values(store, r0c, c0 % COLS, "t")
    b = native_values(store, r0c, (c0 + 1) % COLS, "t")
    c = native_values(store, r1c, c0 % COLS, "t")
    d = native_values(store, r1c, (c0 + 1) % COLS, "t")
    heights = ((a * (1 - fx) + b * fx) * (1 - fy[:, None])
               + (c * (1 - fx) + d * fx) * fy[:, None])
    if not np.isfinite(heights).all() or np.any((heights < -9000) | (heights > 22000)):
        raise TerrainError("terrain_data_invalid", "Некоректні числові висоти MOLA.", 503)
    polar = np.abs(y) > 88
    # Explicit coarse MOLA overview at polar gaps, NOT invented native heights.
    rows = np.clip(((90 - y) / coarse.step).astype(int), 0, coarse.rows - 1)
    cols = ((x % 360) / coarse.step).astype(int) % coarse.cols
    overview = coarse.elevation[np.ix_(rows, cols)].astype(float)
    # All meridians meet at one pole vertex/radius.
    overview[y == 90] = float(coarse.elevation[0].mean())
    overview[y == -90] = float(coarse.elevation[-1].mean())
    heights[polar] = overview[polar]
    # Continuous transition in the uncovered cap; routing still rejects it.
    cap = (np.abs(y) > 88) & (np.abs(y) < 90)
    alpha = np.clip((np.abs(y[cap]) - 88) / 2, 0, 1)[:, None]
    native_edge = ((a * (1 - fx) + b * fx) * (1 - fy[:, None])
                   + (c * (1 - fx) + d * fx) * fy[:, None])
    heights[cap] = native_edge[cap] * (1 - alpha) + overview[cap] * alpha
    counts = native_values(store, np.clip(np.rint(ry).astype(int), first, last),
                           np.rint(cx).astype(int) % COLS, "c")
    native_rows = ~polar
    return {
        "shape": [len(y), len(x)], "longitudes": x.tolist(), "latitudes": y.tolist(),
        "elevations_m": np.round(heights, 2).ravel().tolist(), "level": level,
        "focus": list(focus[:2]), "detail_half_span_deg": focus[2],
        "radius_m": RADIUS, "source": "NASA PDS MOLA MEGDR 128 ppd",
        "source_spacing_m": store.step_m, "native_coverage_latitude": [-88, 88],
        "display_step_deg": (2*focus[2]/min(128,round(2*focus[2]*PPD))) if level else 2,
        "interpolated_fraction": float((counts[native_rows] == 0).mean()),
        "polar_fallback": "MOLA coarse overview, blended only outside ±88°; not route coverage",
        "note": "Bilinear display sampling; zero observation counts retain official interpolation. "
                "Single connected adaptive sphere; display geometry never certifies traversability.",
    }
