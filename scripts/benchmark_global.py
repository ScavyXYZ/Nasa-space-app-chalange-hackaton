"""Small reproducible CPU global-planning benchmark (not a load test)."""
import argparse
import json
import platform
import statistics
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from algorithms.global_routing import GlobalTerrain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be 1..20")
    terrain = GlobalTerrain.load()
    scenarios = [
        ("Tharsis", (-133.8, 18.65), (-112.5, -7.5)),
        ("Olympus to Valles", (-133.8, 18.65), (-59.2, -14)),
        ("Antimeridian", (179, 5), (-179, 5)),
        ("North polar crossing", (0, 89), (180, 89)),
        ("Near antipodal", (0, 0), (179, 0)),
    ]
    rows = []
    for name, start, end in scenarios:
        timings = []
        for _ in range(args.repeats):
            began = perf_counter()
            result = terrain.route(start, end)
            timings.append(perf_counter()-began)
        rows.append({"name": name, "start": start, "end": end, "status": result["status"],
                     "median_seconds": statistics.median(timings),
                     "expanded_cells": result["expanded_cells"],
                     "distance_km": result.get("metrics", {}).get("distance_m", 0)/1000})
    report = {"scope": "Warm-data CPU coarse-to-fine routing, includes graph preparation and metrics; "
                       "excludes HTTP and browser. No GPU. Approximate routes.",
              "python": platform.python_version(), "platform": platform.platform(),
              "source_sha256": terrain.metadata["runtime_sha256"], "repeats": args.repeats,
              "results": rows}
    output = ROOT/"artifacts/global/routing_benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
