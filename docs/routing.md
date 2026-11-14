# Route planner for Jezero

The Algorithms module accepts a prepared terrain grid from GIS. It searches for the minimum-cost route over that grid and returns a geometry and elevation profile for the backend.

## Run the CTX example

Use Python 3.14. From the repository root, install `requirements.txt` and download the prepared arrays with `git lfs pull`. See [the data report](nasa_data_report.md) for instructions to recreate the arrays from source.

```sh
python -m algorithms --start 77.450812 18.444801 --end 77.470379 18.426243 --mode astar
python -m algorithms --start 77.450812 18.444801 --end 77.470379 18.426243 --mode hierarchical
python -m unittest discover -s tests
```

Each command prints a JSON route. The start and end arguments are longitude followed by latitude.

With the GIS API running (`python -m uvicorn backend.main:app`), send this JSON to `POST /api/route`:

```json
{"dataset":"ctx","start":{"lon":77.450812,"lat":18.444801},"end":{"lon":77.470379,"lat":18.426243},"mode":"astar"}
```

## Backend and GIS interface

```python
from pathlib import Path
from algorithms import load_jezero_grid, plan_route

grid = load_jezero_grid(Path("data/processed"))
result = plan_route(*grid, (77.450812, 18.444801), (77.470379, 18.426243))
```

To use another GIS implementation, pass `(elevation, slope, valid, geometry)` directly. The arrays share a two-dimensional `[row, column]` grid. Elevation is in metres, slope is in degrees, and the validity mask uses 0/1 or Boolean values. `geometry` supplies `lonlat_to_pixel(lon, lat)` with `ValueError` for points outside the grid, `pixel_to_lonlat(row, col)` for cell centres, and `distance_m(a, b)`, a metric distance between cells. For prepared HiRISE arrays use `load_jezero_grid(Path("data/processed/hirise"), "jezero_hirise")`.

`status` is `ok`, `outside_grid`, `blocked_endpoint`, or `no_route`. On success, `route` contains a GeoJSON-shaped Feature using Mars coordinates `[east_longitude, planetocentric_latitude]`. It is a `LineString`, or a `Point` when both inputs fall in the same cell. `snapped_start` and `snapped_end` give the exact cell centres. `metrics` contains surface distance, elevation extrema, ascent/descent, peak raster slope, peak grade between cells, and the elevation profile. `steep_segment_indices` lists zero-based segments that reach at least 80% of the configured slope limit. Segment `i` joins profile entries `i` and `i + 1`.

## Search model

The graph allows eight directions. Invalid cells and cells above `max_slope_deg` are blocked. A diagonal requires both adjacent orthogonal cells to be traversable. The elevation change over the distance between cell centres gives a segment grade that must also respect the limit. An edge costs `distance * (1 + slope_weight * max(segment_grade, mean_cell_slope) / 90)`. Grades in the cost are absolute. The default limit of 15° is a model parameter. Set `slope_weight=0` to minimize distance among allowed paths.

In `astar` mode, the heuristic is the direct distance to the goal. In `hierarchical` mode, the planner also computes a lower bound on a graph of blocks. Within each block, movement is treated as free. Each crossing uses the cheapest real edge joining the two blocks. The minimum cost on the block graph therefore cannot exceed the actual route cost. Fine-grid A* uses the larger of the two bounds and can still search the whole grid. This preserves optimality for the same cost model and keeps narrow passages available.

Ordinary A* is the default. On four tested pairs on the 250 × 250 CTX grid, both modes returned equal costs, and building the block graph added time. Compare `expanded_cells` and wall time before selecting the hierarchical mode for a different terrain or resolution.
