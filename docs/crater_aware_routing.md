# Crater-aware routing and real 128 ppd terrain refinement

> Historical model, superseded by [native terrain routing](native_mola_routing.md).
> The active API no longer blocks whole crater discs or refines only A/B patches.

## This changes the computed path, not only its warning

The global planner now tests native-grid **edges** against catalogue crater
footprints. A crater between two otherwise valid nodes cannot be jumped over.
Candidate queries use an STRtree; final intersections use spherical
great-circle arcs, including the dateline and poles. Published circle fits,
expanded by an explicit 100 m planning buffer, are conservatively excluded.
Points inside an excluded footprint are not given an invented crater exit.

Data: Robbins & Hynek, 2014 catalogue release, **384,277 validated records**
with diameter ≥1 km, obtained from the author's public distribution:
https://craters.sjrdesign.net/RobbinsCraterDatabase_20140829.tsv.zip
Reference DOI: https://doi.org/10.1029/2011JE003966
Checksums and source caveats are in `data/processed/craters/metadata.json`.

The catalogue is incomplete and includes some false positives. Circular fits
are not exact rim polygons. Small-crater depths and ellipse tilt have
published reliability issues; neither is used as a fabricated rover slope.
Excluding a footprint is a conservative planning rule, not a physical claim
that every part of every crater wall is impassable.

## Actual finer DEM around the reported endpoints

Prepared two 4° × 4° MOLA **128 ppd** patches, centred near:

- A: `(-97.150761, 24.024217)`
- B: `(150.624967, 9.070396)`

Native spacing is about **463 m** at the equator, 8× finer per axis than the
previous 16 ppd global raster. These are numerical topography and observation
count bins, not CTX images, a hillshade, or heights estimated from shadows.
The exact source byte ranges were downloaded from NASA PDS MEGDR v2, checked
against the product labels and byte counts, and preserved with checksums.

Both datasets use the MOLA GMM3 areoid. Patch extent, source ranges, count
provenance and runtime hashes are in `data/processed/mola128/{a,b}.json`.
The majority of bins in these equatorial patches are officially interpolated
(about 68%); 463 m grid spacing does **not** mean independent measurements or
463 m accuracy. Those bins remain explicitly marked in the route profile.

The planner checks whether a point can reach a patch boundary under the
requested slope/transition limit. It then **replaces covered path sections**
with exact local search in the finer grid, including surface slopes,
transition gradients and no diagonal corner cutting. Catalogue exclusions
also constrain these sections. After stitching, transitions and spherical
crater intersections are checked again. A failing section is rejected; it is
not replaced by a straight line.

For the reported A/B, a local exit exists at 15° in the finer model.
This does not mean all directions across the rim are allowed. The exact
local grid search selects a compliant path. The red 2D layer shows actual
DEM cells above the selected threshold, and the report/GeoJSON lists both
fine patches and the mixed-resolution scope.

Outside these patches the global numerical model is still 16 ppd (~3.7 km).
The catalogue provides additional explicit obstacles there, but unknown
cliffs, sub-kilometre craters, boulders and traction are not verified.
The route is not certified physical rover navigation.

## Reproduction

```
python scripts/prepare_crater_catalog.py
python scripts/prepare_mola128_patches.py
python -m unittest discover -s tests -p test_crater_hazards.py -v
python tests/smoke_traversability_browser.py
```

Global search with catalogue checks has a larger CPU cost than the earlier
height-only model. API search budget is 40 seconds, plus bounded local
refinement. Search-limit results are not reported as proof of no physical
route. No GPU routing is claimed.
