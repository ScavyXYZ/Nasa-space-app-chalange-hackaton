# Planetary routing v2 — data selection, gradients and global imagery

## What actually changed

The former global weighted A* was replaced by balanced bidirectional search:
two frontiers use a feasible geodesic potential. This is a bidirectional
heuristic shortest-path algorithm (related to A*), not a universally superior
replacement for all applications. Local A* is retained because its optimality
tests and corner/surface-slope rules are already appropriate to local DEMs.

Each coarse or native corridor search is exact for its graph. Coarse corridor
selection still makes the whole-planet solution approximate. No claim of
globally optimal or physically safe rover navigation is made.

### Cost and smooth climbs

For horizontal geodesic distance `d`, elevation difference `dh`, endpoint
interpolation fraction `q` in {0,0.5,1}, and slope weight `w`:

```
grade = atan2(abs(dh), d) in degrees
cost = hypot(d, dh) * (1 + w * (grade/45)^2 + 0.25*q)
```

An edge is excluded if its grade exceeds the requested limit.
**Absolute altitude never excludes a cell or adds an altitude penalty.**
A long gradual ascent remains possible. The slope penalty is quadratic, so
steep transitions are penalized more than shallow ones. The data-quality
penalty encourages measured bins over officially interpolated bins; it is
an explicit application preference, not NASA's safety or rover energy model.

CTX/HiRISE additionally enforce the measured surface-slope mask and no
diagonal corner cutting. Unknown boulders, soil mechanics, wheel traction,
live weather and hazards are not fabricated from a photograph or coarse
geological unit. Geology remains scientific context, not an arbitrary
passability multiplier.

### Search guarantees

`p(v) = (distance(v,goal)-distance(v,start))/2`.
Forward keys `gF+p`, backward keys `gB-p`. All edge costs >= the geodesic
metric, giving nonnegative reduced costs. Stop when the sum of frontier
minimum keys >= best joined cost. Backward traversal evaluates the original
forward edge cost, including for asymmetric test graphs.

Tests compare with an independent Dijkstra on 30 randomized obstacle graphs,
including asymmetric costs. Smooth-climb, altitude-translation invariance,
steep-wall and budget regressions are in `tests/test_bidirectional.py`.

Benchmarks in `artifacts/global/routing_benchmark.json` are a new cost model
and a different optimality/performance tradeoff. They are **not a speedup
comparison** against the previous weighted model. A single local run measured
~1 s for Tharsis and ~4.9 s for Olympus–Valles; the latter previously hit the
search expansion limit. Other hosts and concurrent requests vary.

## Best available data means best data actually loaded

Point inspection returns all available DEM samples plus the finest valid:
HiRISE 1 m → regional CTX 20 m → global MOLA 16 ppd (~3.7 km).
NoData in a finer product does not become an invented fine sample.
Coordinates are retained to six decimals, which is representation precision,
**not a claim of sub-metre measurement accuracy**.

Route auto-selection uses the finest single dataset covering all stops.
It does not silently blend datums or switch to a coarse dataset when the
fine dataset reports blocked terrain. Explicit source selection is available.
The native graph snaps endpoints to cell centres and reports the offsets.

This is not an automatic ingestion of every DEM in NASA's archives.
Finer global MOLA products and new regional DEMs require separate acquisition
and validation. Optical CTX coverage is far more extensive than detailed
numerical DEM coverage.

## Global detailed viewing

The NASA Trek CTX capabilities advertised only 12 levels. Its referenced
Esri/Murray Lab service exposes 18 levels with **512 px** tiles. The native
service metadata is now saved/validated and used for the catalog. Very high
levels oversample the original images; auto viewing caps the useful source
level rather than describing every level as a new scientific resolution.

The application renders a normalized 256px tile grid, so the stated pixel
spacing is for the rendered grid, not the original 512px source.
High-detail global CTX was tested at zoom 12 near Gale, outside Jezero.
Coverage holes, mosaicking seams, uncontrolled registration and polar gaps
can still exist: “whole planet” does not mean identical precision everywhere.

Globe textures keep the prior regional atlas underneath new imagery and load
centre tiles first. Rapid camera changes are coalesced before network requests.
A 192 MB bounded temporary disk cache retains successful tile responses
across backend restarts; only files created in the app's cache are evicted.
Scientific source data are never deleted by cache eviction.

Tests:

```
python -m unittest discover -s tests -v
python tests/smoke_zoom_browser.py
python tests/smoke_atlas_browser.py
```
