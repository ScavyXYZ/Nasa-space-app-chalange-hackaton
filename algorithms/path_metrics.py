"""Profile and statistics for a route through prepared terrain."""

from itertools import pairwise
from math import atan2, degrees

from .grid import Cell
from .pathfinding import RouteGraph


def route_metrics(graph: RouteGraph, path: tuple[Cell, ...]) -> dict:
    elevations = [float(graph.elevation[cell]) for cell in path]
    slopes = [float(graph.slope[cell]) for cell in path]
    distances = [0.0]
    grades = []
    uphill = downhill = 0.0
    steep_segments = []
    for i, (a, b) in enumerate(pairwise(path)):
        length = graph.geometry.distance_m(a, b)
        rise = elevations[i + 1] - elevations[i]
        grade = degrees(atan2(rise, length))
        uphill += max(rise, 0)
        downhill += max(-rise, 0)
        distances.append(distances[-1] + length)
        grades.append(abs(grade))
        peak = max(abs(grade), slopes[i], slopes[i + 1])
        if peak > 0 and peak >= 0.8 * graph.max_slope_deg:
            steep_segments.append(i)
    return {
        "distance_m": distances[-1],
        "min_elevation_m": min(elevations),
        "max_elevation_m": max(elevations),
        "ascent_m": uphill,
        "descent_m": downhill,
        "max_slope_deg": max(slopes),
        "max_segment_grade_deg": max(grades, default=0.0),
        "steep_segment_indices": steep_segments,
        "elevation_profile": [
            {"distance_m": distance, "elevation_m": elevation, "slope_deg": slope}
            for distance, elevation, slope in zip(distances, elevations, slopes)
        ],
    }
