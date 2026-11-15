"""Compare old geodesic A* heuristic with the exact relaxed-grid heuristic.

Reports local CPU search timings, not HTTP latency or GPU performance.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from algorithms.grid import MarsRasterGeometry
from algorithms.pathfinding import RouteGraph
from algorithms.terrain import TerrainGrid


def benchmark(repeats):
    results = []
    for dataset, start, goal in [
        ("ctx", (125, 125), (180, 180)),
        ("hirise", (500, 500), (650, 650)),
        ("regional", (300, 450), (1200, 1200)),
    ]:
        terrain = TerrainGrid.load(dataset)
        try:
            geometry = MarsRasterGeometry(terrain=terrain)
            graph = RouteGraph(terrain.elevation, terrain.slope, terrain.valid, geometry, max_slope_deg=25)
            optimized = geometry.lower_bound_m
            timings = {"geodesic": [], "relaxed_grid": []}
            searches = {}
            # Alternate execution order to reduce warm-cache/order bias.
            for repeat in range(repeats):
                modes = list(timings) if repeat % 2 == 0 else list(reversed(timings))
                for name in modes:
                    geometry.lower_bound_m = geometry.distance_m if name == "geodesic" else optimized
                    began = time.perf_counter()
                    result = graph.search(start, goal)
                    timings[name].append(time.perf_counter() - began)
                    searches[name] = result
            old, new = searches["geodesic"], searches["relaxed_grid"]
            if not old.cells or not new.cells:
                raise AssertionError(f"Benchmark endpoints must have a route: {dataset}")
            if abs(old.cost - new.cost) > 1e-6 * max(1, old.cost):
                raise AssertionError(f"Optimal route cost changed: {dataset}")
            medians = {name: statistics.median(values) for name, values in timings.items()}
            results.append({
                "dataset": dataset, "start_cell": start, "goal_cell": goal,
                "median_search_seconds": medians, "speedup": medians["geodesic"] / medians["relaxed_grid"],
                "expanded_cells": {name: value.expanded_cells for name, value in searches.items()},
                "baseline_cost": old.cost, "optimized_cost": new.cost, "repeats": repeats,
            })
        finally:
            terrain.close()
    return {"scope": "Local CPU A* only; same terrain, edge costs and parameters; no GPU.", "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    report = json.dumps(benchmark(args.repeats), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
