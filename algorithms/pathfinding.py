"""Exact A* with an optional lower bound from a coarser block graph."""

from dataclasses import dataclass
from heapq import heappop, heappush
from math import atan2, degrees, isfinite
from typing import Literal

import numpy as np

from .grid import Cell, GridGeometry

Mode = Literal["astar", "hierarchical"]
_STEPS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
# One direction per undirected edge.
_FORWARD_STEPS = ((0, 1), (1, -1), (1, 0), (1, 1))


@dataclass(frozen=True)
class SearchResult:
    cells: tuple[Cell, ...]
    cost: float | None
    expanded_cells: int


class RouteGraph:
    def __init__(self, elevation, slope, valid, geometry: GridGeometry, *,
                 max_slope_deg: float = 15.0, slope_weight: float = 1.0):
        if not 0 <= max_slope_deg <= 90:
            raise ValueError("max_slope_deg must be in [0, 90]")
        if not isfinite(slope_weight) or slope_weight < 0:
            raise ValueError("slope_weight must be finite and nonnegative")
        self.elevation = np.asarray(elevation)
        self.slope = np.asarray(slope)
        valid = np.asarray(valid, dtype=bool)
        shape = self.elevation.shape
        if self.elevation.ndim != 2 or 0 in shape or shape != self.slope.shape or shape != valid.shape:
            raise ValueError("Elevation, slope and mask must have the same nonempty 2D shape")
        self.geometry = geometry
        self.rows, self.cols = shape
        self.max_slope_deg = max_slope_deg
        self.slope_weight = slope_weight
        self.open = (valid & np.isfinite(self.elevation) & np.isfinite(self.slope)
                     & (self.slope >= 0) & (self.slope <= max_slope_deg))

    def contains(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.rows and 0 <= cell[1] < self.cols

    def edge_cost(self, a: Cell, b: Cell) -> float | None:
        """Cost of a transition between neighbouring cells, or None if blocked."""
        r, c = a
        nr, nc = b
        if not self.open[b]:
            return None
        if r != nr and c != nc and not (self.open[r, nc] and self.open[nr, c]):
            return None
        distance = self.geometry.distance_m(a, b)
        rise = abs(float(self.elevation[b]) - float(self.elevation[a]))
        grade = degrees(atan2(rise, distance))
        if grade > self.max_slope_deg:
            return None
        mean_slope = (float(self.slope[a]) + float(self.slope[b])) / 2
        return distance * (1 + self.slope_weight * max(grade, mean_slope) / 90)

    def _coarse_lower_bounds(self, goal: Cell, size: int) -> dict[Cell, float]:
        """Collapse each block to a node with free movement inside it.

        The minimum cost of any real crossing is the block edge weight.
        Ignoring internal costs/obstacles gives a lower bound and never removes
        a real route from consideration, even in narrow passages.
        """
        edges: dict[Cell, dict[Cell, float]] = {}
        # Only visit cells along block boundaries (and their adjacent rows).
        for dr, dc in _FORWARD_STEPS:
            for r in range(self.rows - dr):
                row_crosses = r // size != (r + dr) // size
                if row_crosses:
                    columns = range(max(0, -dc), min(self.cols, self.cols - dc))
                elif dc > 0:
                    columns = range(size - 1, self.cols - 1, size)
                elif dc < 0:
                    columns = range(size, self.cols, size)
                else:
                    continue
                for c in columns:
                    a, b = (r, c), (r + dr, c + dc)
                    if not self.open[a]:
                        continue
                    cost = self.edge_cost(a, b)
                    if cost is None:
                        continue
                    u, v = (r // size, c // size), (b[0] // size, b[1] // size)
                    outgoing = edges.setdefault(u, {})
                    if cost < outgoing.get(v, np.inf):
                        outgoing[v] = cost
                        edges.setdefault(v, {})[u] = cost

        end = goal[0] // size, goal[1] // size
        distances = {end: 0.0}
        queue = [(0.0, end)]
        while queue:
            distance, u = heappop(queue)
            if distance != distances[u]:
                continue
            for v, weight in edges.get(u, {}).items():
                candidate = distance + weight
                if candidate < distances.get(v, np.inf):
                    distances[v] = candidate
                    heappush(queue, (candidate, v))
        return distances

    def search(self, start: Cell, goal: Cell, *, mode: Mode = "astar", block_size: int = 16) -> SearchResult:
        if mode not in ("astar", "hierarchical"):
            raise ValueError(f"Unknown search mode: {mode}")
        if not isinstance(block_size, int) or block_size < 2:
            raise ValueError("block_size must be an integer of at least 2")
        for cell in (start, goal):
            if not self.contains(cell) or not self.open[cell]:
                raise ValueError(f"Endpoint is outside the grid or blocked: {cell}")
        if start == goal:
            return SearchResult((start,), 0.0, 0)

        coarse = self._coarse_lower_bounds(goal, block_size) if mode == "hierarchical" else None

        def heuristic(cell: Cell) -> float:
            direct = self.geometry.distance_m(cell, goal)
            if coarse is None:
                return direct
            return max(direct, coarse.get((cell[0] // block_size, cell[1] // block_size), np.inf))

        start_bound = heuristic(start)
        if not isfinite(start_bound):
            return SearchResult((), None, 0)
        best = np.full(self.open.shape, np.inf)
        best[start] = 0.0
        parents: dict[Cell, Cell] = {}
        queue = [(start_bound, 0.0, start)]
        expanded = 0
        while queue:
            _, negative_cost, cell = heappop(queue)
            cost = -negative_cost
            if cost != best[cell]:
                continue
            if cell == goal:
                path = [goal]
                while path[-1] != start:
                    path.append(parents[path[-1]])
                return SearchResult(tuple(reversed(path)), cost, expanded)
            expanded += 1
            for dr, dc in _STEPS:
                neighbour = cell[0] + dr, cell[1] + dc
                if not self.contains(neighbour):
                    continue
                transition = self.edge_cost(cell, neighbour)
                if transition is None:
                    continue
                candidate = cost + transition
                if candidate >= best[neighbour]:
                    continue
                bound = heuristic(neighbour)
                if isfinite(bound):
                    best[neighbour] = candidate
                    parents[neighbour] = cell
                    heappush(queue, (candidate + bound, -candidate, neighbour))
        return SearchResult((), None, expanded)
