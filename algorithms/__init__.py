"""Route planning over a GIS-supplied terrain grid."""

from math import isfinite

from .grid import GridGeometry, LonLat, load_jezero_grid
from .path_metrics import route_metrics
from .pathfinding import Mode, RouteGraph

__all__ = ["plan_route", "load_jezero_grid"]


def plan_route(elevation, slope, valid, geometry: GridGeometry, start: LonLat, end: LonLat,
               *, max_slope_deg: float = 15.0, slope_weight: float = 1.0,
               mode: Mode = "astar", block_size: int = 16) -> dict:
    """Produce a JSON-ready route result. Input coordinates are (lon, lat)."""
    graph = RouteGraph(elevation, slope, valid, geometry,
                       max_slope_deg=max_slope_deg, slope_weight=slope_weight)
    cells = []
    for name, (lon, lat) in (("start", start), ("end", end)):
        try:
            if not isfinite(lon) or not isfinite(lat):
                raise ValueError("Nonfinite coordinates")
            cell = geometry.lonlat_to_pixel(lon, lat)
            if not graph.contains(cell):
                raise ValueError("Cell is outside the supplied arrays")
        except (ValueError, OverflowError):
            return {"status": "outside_grid", "endpoint": name}
        if not graph.open[cell]:
            return {"status": "blocked_endpoint", "endpoint": name}
        cells.append(cell)

    result = graph.search(*cells, mode=mode, block_size=block_size)
    if not result.cells:
        return {"status": "no_route", "mode": mode, "expanded_cells": result.expanded_cells}

    coordinates = [[float(lon), float(lat)]
                   for lon, lat in (geometry.pixel_to_lonlat(*cell) for cell in result.cells)]
    route_geometry = ({"type": "Point", "coordinates": coordinates[0]} if len(coordinates) == 1
                      else {"type": "LineString", "coordinates": coordinates})
    return {
        "status": "ok",
        "mode": mode,
        "expanded_cells": result.expanded_cells,
        "cost": result.cost,
        "snapped_start": coordinates[0],
        "snapped_end": coordinates[-1],
        "route": {"type": "Feature", "geometry": route_geometry, "properties": {}},
        "metrics": route_metrics(graph, result.cells),
    }
