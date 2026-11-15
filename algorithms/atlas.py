"""Source-geometry geological queries and ordered multi-stop expeditions."""
import gzip
import json
from time import monotonic

import numpy as np
from shapely import STRtree, from_wkb
from shapely.geometry import Point, LineString

from .global_routing import distance
from .terrain import TerrainError


class Geology:
    def __init__(self, root):
        folder = root/"data/processed/atlas"
        try:
            with gzip.open(folder/"geology_query.json.gz", "rt", encoding="utf-8") as stream:
                data = json.load(stream)
            self.properties = data["properties"]
            self.geometries = [from_wkb(bytes.fromhex(wkb)) for wkb in data["wkb"]]
            self.tree = STRtree(self.geometries)
        except (OSError, ValueError, KeyError) as exc:
            raise TerrainError("geology_unavailable", "Prepare atlas data first", 503) from exc

    def point(self, lon, lat):
        point = Point(lon, lat)
        indices = self.tree.query(point, predicate="intersects")
        return [self.properties[int(i)] for i in indices]

    def along(self, coordinates):
        # Never draw a 358-degree shortcut through polygons across the world.
        found = set()
        for a, b in zip(coordinates, coordinates[1:]):
            if abs(a[0]-b[0]) > 180:
                lon = b[0]+(360 if b[0] < a[0] else -360)
                edge = 180 if lon > a[0] else -180
                t = (edge-a[0])/(lon-a[0])
                lat = a[1]+t*(b[1]-a[1])
                segments = [LineString([a, (edge, lat)]), LineString([(-edge, lat), b])]
            else:
                segments = [LineString([a, b])]
            for line in segments:
                found.update(int(i) for i in self.tree.query(line, predicate="intersects"))
        if len(coordinates) == 1:
            return self.point(*coordinates[0])
        by_unit = {}
        for i in sorted(found):
            by_unit.setdefault(self.properties[i]["unit"], self.properties[i])
        return list(by_unit.values())


def expedition(terrain, points, max_grade_deg, slope_weight, geology=None, budget_s=18,route_options=None):
    began = monotonic()
    legs, profile, coordinates = [], [], []
    expanded, total, ascent, descent, interpolated = 0, 0., 0., 0., 0
    snaps = []
    terrain_distance=0.
    max_surface_slope=0.
    checks={}
    for i, (a, b) in enumerate(zip(points, points[1:])):
        remaining = budget_s-(monotonic()-began)
        if remaining <= 0:
            return {"status": "search_limit", "expanded_cells": expanded, "failed_leg": i}
        result = terrain.route(a, b, max_grade_deg, slope_weight, time_budget_s=remaining,**(route_options or {}))
        expanded += result.get("expanded_cells", 0)
        if result["status"] != "ok":
            return {**result, "failed_leg": i, "expanded_cells": expanded}
        metrics = result["metrics"]
        max_surface_slope=max(max_surface_slope,metrics.get("max_surface_slope_deg",metrics["max_grade_deg"]))
        for check in result.get("terrain_checks",[]):checks[check["id"]]=check
        line = result["route"]["geometry"]
        leg_coordinates = line["coordinates"] if line["type"] == "LineString" else [line["coordinates"]]
        # All legs snap to the same containing cell at a stop.
        coordinates.extend(leg_coordinates[1:] if coordinates else leg_coordinates)
        profile.extend([{**p, "distance_m": p["distance_m"]+total}
                        for p in (result["profile"][1:] if profile else result["profile"])])
        legs.append({"index": i, "distance_m": metrics["distance_m"], "ascent_m": metrics["ascent_m"],
                     "max_grade_deg": metrics["max_grade_deg"], "start": a, "end": b})
        total += metrics["distance_m"]
        terrain_distance+=metrics.get("terrain_distance_m",metrics["distance_m"])
        ascent += metrics["ascent_m"]
        descent += metrics["descent_m"]
        snaps.append(metrics["snap_offsets_m"][0])
    snaps.append(metrics["snap_offsets_m"][1])
    cells = [terrain.index(p) for p in coordinates]
    interpolated = sum(p["interpolated"] for p in profile)
    properties = {**result["route"]["properties"], "ordered_stops": points,
                  "max_grade_deg": max_grade_deg, "slope_weight": slope_weight,
                  "resolution_deg": terrain.step, "vertical_datum": terrain.metadata.get("vertical_datum")}
    output = {**result, "route": {"type": "Feature", "geometry": {
        "type": "LineString" if len(coordinates) > 1 else "Point",
        "coordinates": coordinates if len(coordinates) > 1 else coordinates[0]}, "properties": properties},
        "legs": legs, "profile": profile, "expanded_cells": expanded,
        "terrain_checks":list(checks.values()),
        "elapsed_ms": round((monotonic()-began)*1000),
        "metrics": {**result["metrics"], "distance_m": total, "direct_distance_m": distance(points[0], points[-1]),
                    "ascent_m": ascent, "descent_m": descent,"terrain_distance_m":terrain_distance,
                    "min_elevation_m": min(p["elevation_m"] for p in profile),
                    "max_elevation_m": max(p["elevation_m"] for p in profile),
                    "max_grade_deg": max(leg["max_grade_deg"] for leg in legs),
                    "max_surface_slope_deg":max_surface_slope,
                    "interpolated_cells": int(interpolated), "cells": len(coordinates), "snap_offsets_m": snaps},
        "data_quality": {"resolution_deg": terrain.step,
                         "equatorial_spacing_m": terrain.metadata.get("equatorial_spacing_m"),
                         "vertical_datum": terrain.metadata.get("vertical_datum"),
                         "source": terrain.metadata.get("source_page"),
                          "product": terrain.metadata.get("product")},
        "model_notice":"Gradient and measured DEM data quality are used. Absolute altitude is not blocked. "
                       "Rock size, soil bearing strength, wheel traction and live hazards are unknown, not inferred from imagery.",
    }
    if geology:
        output["geological_units"] = geology.along(coordinates)
    return output
