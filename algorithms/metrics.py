"""Analyse supplied routes, not route search. Reject unknown terrain crossings."""
import math
import numpy as np

from .terrain import TerrainError, TerrainGrid


def analyze_route(grid: TerrainGrid, coordinates, sample_step_m=None, max_slope_deg=15, max_samples=20000):
    if not 2 <= len(coordinates) <= 1000:
        raise TerrainError("invalid_route", "Provide 2–1000 [longitude,latitude] vertices")
    grid.blocked_mask(max_slope_deg)  # Validate model parameter; no implicit obstacle policy.
    for coordinate in coordinates:
        if len(coordinate) != 2:
            raise TerrainError("invalid_route", "Only two-dimensional [longitude,latitude] coordinates are supported")
        grid.index(*coordinate)
    if sample_step_m is not None and (not math.isfinite(sample_step_m) or sample_step_m <= 0):
        raise TerrainError("invalid_step", "Sampling step must be finite and positive")
    # Never allow requested coarse sampling to skip raster cells.
    step = min(sample_step_m or math.inf, grid.min_ground_spacing/2)
    segments, count = [], 1
    for a, b in zip(coordinates, coordinates[1:]):
        distance = grid.distance_m(a, b)
        if distance <= 1e-8:
            continue
        n = max(1, math.ceil(distance/step))
        count += n
        if count > max_samples:
            raise TerrainError("profile_too_large", f"Profile requires {count} samples; limit is {max_samples}. Shorten route or use CTX.", 413)
        segments.append((a,b,n))
    points = [tuple(coordinates[0])]
    for a,b,n in segments:
        points.extend(grid.geod.npts(*a,*b,n-1) if n > 1 else [])
        points.append(tuple(b))
    profile, distance, touched, high_cells = [], 0.0, set(), set()
    max_terrain_slope = 0.0
    for i, point in enumerate(points):
        sample = grid.sample(*point)
        cells = grid.crossed_cells(points[i-1], point) if i else [(sample["row"],sample["col"])]
        for row,col in cells:
            if not (0 <= row < grid.shape[0] and 0 <= col < grid.shape[1]):
                raise TerrainError("outside_coverage", "Route touches the raster exterior")
            if not grid.valid[row,col]:
                raise TerrainError("route_nodata", f"Route intersects unknown terrain at row={row}, col={col}")
            touched.add((row,col))
            slope = float(grid.slope[row,col])
            max_terrain_slope = max(max_terrain_slope, slope)
            if slope > max_slope_deg:
                high_cells.add((row,col))
        if i:
            distance += grid.distance_m(points[i-1],point)
        profile.append({**sample, "distance_m":distance, "exceeds_slope_threshold":sample["slope_deg"] > max_slope_deg})
    heights = np.array([p["elevation_m"] for p in profile])
    changes = np.diff(heights)
    return {
        "dataset":grid.dataset,
        "route":{"type":"Feature", "geometry":{"type":"LineString","coordinates":coordinates},
                 "properties":{"coordinate_system":"Mars, not WGS84", "route_type":"user_supplied_not_A_star"}},
        "summary":{"distance_m":distance, "elevation_min_m":float(heights.min()),
                   "elevation_max_m":float(heights.max()), "elevation_gain_m":float(changes[changes>0].sum()),
                   "elevation_loss_m":float(-changes[changes<0].sum()),
                   "net_elevation_change_m":float(heights[-1]-heights[0]),
                   "max_terrain_slope_deg":max_terrain_slope, "cells_crossed":len(touched),
                   "cells_above_slope_threshold":len(high_cells),
                   "requires_review":bool(high_cells)},
        "sampling":{"effective_max_step_m":step, "count":len(profile), "height_method":"containing_cell_no_interpolation"},
        "model_parameters":{"max_slope_deg":max_slope_deg},
        "profile":profile,
        "warnings":["User-supplied line analysis, NOT A* and NOT a safety assessment.",
                    "Slope threshold is an application parameter, not a NASA limit.",
                    "Gain/loss depend on DEM resolution, sampling and photogrammetric noise; no smoothing or datum blending applied."]
    }
