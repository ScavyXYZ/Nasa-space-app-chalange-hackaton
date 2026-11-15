"""Bounded coarse-to-fine spherical routing over official MOLA topography.

Longitude wraps; pole crossings reflect into the opposite longitude. Coarse
search guides a native-grid corridor, widened on failure. This is explicitly
approximate globally: the corridor does not guarantee global optimality.
Each corridor is solved exactly with a balanced bidirectional metric potential.
"""
import hashlib
import json
import math
from time import monotonic

import numpy as np

from .terrain import ROOT, TerrainError
from .bidirectional import bidirectional_search
from .assessment import traversability_assessment

RADIUS = 3396000.0  # MOLA product label; distinct from the local CTX sphere.
STEPS = tuple((r, c) for r in (-1, 0, 1) for c in (-1, 0, 1) if r or c)


def distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*RADIUS*math.asin(math.sqrt(min(1.0, max(0.0, h))))


class GlobalTerrain:
    def __init__(self, elevation, counts, metadata=None, hazards=None):
        self.elevation = np.asarray(elevation)
        self.counts = np.asarray(counts)
        if (self.elevation.ndim != 2 or self.elevation.shape != self.counts.shape
                or self.elevation.shape[1] != 2*self.elevation.shape[0]
                or not np.isfinite(self.elevation).all() or np.any(self.counts < 0)):
            raise ValueError("Invalid global topography/counts")
        self.rows, self.cols = self.elevation.shape
        self.step = 180/self.rows
        self.metadata = metadata or {}
        self.hazards=hazards

    @classmethod
    def load(cls, root=ROOT):
        folder = root / "data/processed/global"
        try:
            metadata = json.loads((folder/"metadata.json").read_text(encoding="utf-8"))
            path = folder/metadata.get("runtime_archive", "mola_4ppd.npz")
            if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["runtime_sha256"]:
                raise ValueError("MOLA checksum mismatch")
            from .craters import CraterCatalog
            hazards=CraterCatalog.load(root) if (root/"data/processed/craters/metadata.json").is_file() else None
            with np.load(path, allow_pickle=False) as data:
                return cls(data["elevation"], data["counts"], metadata,hazards)
        except (OSError, ValueError, KeyError) as exc:
            raise TerrainError("global_unavailable", "Run python scripts/prepare_global_terrain.py", 503) from exc

    def index(self, point):
        lon, lat = point
        if not math.isfinite(lon) or not math.isfinite(lat) or abs(lon) > 180 or abs(lat) > 90:
            raise TerrainError("invalid_coordinate", "Expected finite Mars longitude/latitude")
        return min(self.rows-1, int((90-lat)/self.step)), int((lon % 360)/self.step) % self.cols

    def coordinate(self, cell):
        r, c = cell
        return ((c+.5)*self.step+180) % 360-180, 90-(r+.5)*self.step

    def sample(self, point):
        cell = self.index(point)
        return {"lon": point[0], "lat": point[1], "elevation_m": float(self.elevation[cell]),
                "observations": int(self.counts[cell]), "interpolated": bool(self.counts[cell] == 0),
                "cell_center": self.coordinate(cell), "resolution_deg": self.step}

    def display(self):
        stride = max(1, self.rows//180)
        return {**self.metadata, "shape": list(self.elevation[::stride, ::stride].shape),
                "latitudes": [self.coordinate((r, 0))[1] for r in range(0, self.rows, stride)],
                "longitudes": [self.coordinate((0, c))[0] for c in range(0, self.cols, stride)],
                "elevations_m": self.elevation[::stride, ::stride].ravel().tolist()}

    @staticmethod
    def neighbour(cell, dr, dc, rows, cols):
        r, c = cell[0]+dr, cell[1]+dc
        if r < 0:
            r, c = -r-1, c+cols//2
        elif r >= rows:
            r, c = 2*rows-r-1, c+cols//2
        return r, c % cols

    def _search(self, start, goal, stride, limit, weight, deadline, allowed=None, uncertainty_weight=0.25,
                avoid_craters=True):
        heights=self.elevation[::stride,::stride]
        rows,cols=heights.shape
        a,b=(start[0]//stride,start[1]//stride),(goal[0]//stride,goal[1]//stride)
        def coord(cell):
            return self.coordinate((cell[0]*stride,cell[1]*stride))
        def neighbours(cell):
            for dr,dc in STEPS:
                other=self.neighbour(cell,dr,dc,rows,cols)
                if other!=cell and (allowed is None or allowed[other]):
                    yield other
        lengths={};hazard_edges={}
        def cost(cell,other):
            key=(cell[0],other[0],min((other[1]-cell[1])%cols,(cell[1]-other[1])%cols))
            if key not in lengths:
                lengths[key]=distance(coord(cell),coord(other))
            length=lengths[key]
            rise=abs(float(heights[other])-float(heights[cell]))
            grade=math.degrees(math.atan2(rise,length))
            if grade>limit:
                return None
            if stride==1 and avoid_craters and self.hazards is not None:
                edge=tuple(sorted((cell,other)))
                if edge not in hazard_edges:
                    hazard_edges[edge]=bool(self.hazards.intersections(coord(cell),coord(other)))
                if hazard_edges[edge]:return None
            unknown=(int(self.counts[cell[0]*stride,cell[1]*stride]==0)
                     +int(self.counts[other[0]*stride,other[1]*stride]==0))/2
            return math.hypot(length,rise)*(1+weight*(grade/45)**2+uncertainty_weight*unknown)
        path,expanded,limited=bidirectional_search(a,b,neighbours,cost,
            lambda x,y:distance(coord(x),coord(y)),deadline=deadline)
        return [(r*stride,c*stride) for r,c in path],expanded,limited

    def _corridor(self, path, width):
        allowed = np.zeros(self.elevation.shape, dtype=bool)
        for r, c in path:
            for dr in range(-width, width+1):
                nr, nc = self.neighbour((r, c), dr, 0, self.rows, self.cols)
                allowed[nr, (np.arange(nc-width, nc+width+1) % self.cols)] = True
        return allowed

    def route(self, start, end, max_grade_deg=15, slope_weight=5, time_budget_s=12,
              uncertainty_weight=0.25,avoid_craters=True):
        if not 0 <= max_grade_deg <= 90 or not math.isfinite(slope_weight) or not 0 <= slope_weight <= 100:
            raise TerrainError("invalid_parameters", "Invalid slope parameters")
        if not math.isfinite(uncertainty_weight) or not 0<=uncertainty_weight<=10:
            raise TerrainError("invalid_parameters","Invalid interpolation penalty")
        began = monotonic()
        deadline = began+time_budget_s
        a, b = self.index(start), self.index(end)
        if avoid_craters and self.hazards is not None:
            for endpoint,point,cell in [("start",start,a),("end",end,b)]:
                hits=self.hazards.containing(point) or self.hazards.containing(self.coordinate(cell))
                if hits:
                    return {"status":"blocked_endpoint","endpoint":endpoint,"reason":"crater_exclusion",
                            "expanded_cells":0,"hazards":hits,"hazard_policy":self.hazards.policy(),
                            "message":"Точка або її клітинка DEM лежить у каталожному контурі кратера. "
                                      "Без локально перевіреного виїзду шлях через його борт не будується."}
        stride = max(1, self.rows//90) if self.rows % 90 == 0 else (8 if self.rows % 8 == 0 else 1)
        coarse, expanded, limited = self._search(a, b, stride, max_grade_deg, slope_weight, deadline,
                                                 uncertainty_weight=uncertainty_weight,avoid_craters=avoid_craters)
        if limited:
            return {"status": "search_limit", "expanded_cells": expanded}
        path = coarse
        if stride > 1:
            path = []
            for width in (16, 40):
                if not coarse:
                    break
                allowed = self._corridor(coarse+[a, b], min(max(width,stride*2), self.rows-1))
                path, count, limited = self._search(a, b, 1, max_grade_deg, slope_weight, deadline, allowed,
                                                   uncertainty_weight,avoid_craters)
                expanded += count
                if path or limited:
                    break
            if not path and not limited:
                path, count, limited = self._search(a, b, 1, max_grade_deg, slope_weight, deadline,
                                                    uncertainty_weight=uncertainty_weight,avoid_craters=avoid_craters)
                expanded += count
        if not path:
            return {"status": "search_limit" if limited else "no_route", "expanded_cells": expanded}
        coordinates = [self.coordinate(cell) for cell in path]
        lengths = [distance(p, q) for p, q in zip(coordinates, coordinates[1:])]
        heights = [float(self.elevation[cell]) for cell in path]
        grades = [math.degrees(math.atan2(abs(y-x), d)) for x, y, d in zip(heights, heights[1:], lengths)]
        changes = np.diff(heights)
        cumulative = np.r_[0., np.cumsum(lengths)]
        interpolated = sum(self.counts[cell] == 0 for cell in path)
        terrain_distance=sum(math.hypot(d,y-x) for d,x,y in zip(lengths,heights,heights[1:]))
        snap = [distance(start, coordinates[0]), distance(end, coordinates[-1])]
        assessment=traversability_assessment(self.step*math.pi/180*RADIUS,global_model=True)
        policy=self.hazards.policy() if avoid_craters and self.hazards is not None else {"enabled":False}
        if policy["enabled"]:
            assessment["terrain_constraints_checked"].append("catalogue_crater_footprint_exclusion")
            assessment["message"]="Каталожні контури кратерів обійдено. Між клітинками перевіряються перетини, а не лише висоти. Невідомі уступи, дрібні кратери та ґрунт потребують детальнішої перевірки."
        return {
            "status": "ok", "dataset": "mola", "algorithm": "coarse-to-fine balanced bidirectional search",
            "approximate": True, "expanded_cells": expanded, "elapsed_ms": round((monotonic()-began)*1000),
            "traversability":assessment,
            "hazard_policy":policy,
            "route": {"type": "Feature", "geometry": {
                "type": "Point" if len(path) == 1 else "LineString",
                "coordinates": coordinates[0] if len(path) == 1 else coordinates},
                "properties": {"coordinate_system": "Mars planetocentric, NOT WGS84",
                               "source": self.metadata.get("source_page"), "resolution_deg": self.step,
                                "approximate": True, "max_grade_deg": max_grade_deg,
                                 "traversability":assessment,
                                 "hazard_policy":policy,
                               "slope_weight": slope_weight,"uncertainty_weight":uncertainty_weight,
                               "cost_model":"sqrt(horizontal_distance^2 + rise^2) * (1 + slope_weight*(grade/45)^2 + uncertainty_weight*interpolated_endpoint_fraction)",
                               "vertical_datum": self.metadata.get("vertical_datum")}},
            "metrics": {"distance_m": float(cumulative[-1]), "direct_distance_m": distance(start, end),
                        "terrain_distance_m":terrain_distance,
                        "min_elevation_m": min(heights), "max_elevation_m": max(heights),
                        "ascent_m": float(changes[changes > 0].sum()), "descent_m": float(-changes[changes < 0].sum()),
                        "max_grade_deg": max(grades, default=0), "interpolated_cells": int(interpolated),
                        "cells": len(path), "snap_offsets_m": snap},
            "profile": [{"distance_m": float(d), "elevation_m": h, "interpolated": bool(self.counts[cell] == 0)}
                        for d, h, cell in zip(cumulative, heights, path)],
            "warnings": ["Approximate global route, not a local traversability assessment.",
                         "Search is exact in the selected corridor; coarse guidance does not guarantee global optimality.",
                         "Absolute elevation is not an obstacle; constraints apply to gradient, not altitude.",
                         "Optical imagery and coarse geology are context, not measured rock/soil traction or hazard masks.",
                         f"Native {self.step}-degree MOLA bins may contain official interpolation.",
                         "Distance excludes endpoint snapping offsets; heights are relative to the MOLA areoid."],
        }
