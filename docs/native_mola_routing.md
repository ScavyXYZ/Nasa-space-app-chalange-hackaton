# Current routing model: native numerical terrain along the entire route

This supersedes the earlier model in `crater_aware_routing.md`.

## What changed

The default planetary endpoint now uses **MOLA MEGDR 128 ppd throughout**,
not a 16 ppd path with finer checks only near two fixed endpoints. All 32
official topography/count files (3.114 GB) are cached locally, with PDS labels,
byte counts and SHA-256 provenance. Numerical coverage is 88°S–88°N.

The global overview/globe mesh remains coarser for rendering. Photograph
resolution, display-mesh resolution and numerical routing resolution are
separate and must not be conflated.

### Terrain plus a guard against unresolved catalogue rims

Catalogue circles are **not blocked interiors**, but their boundaries are no
longer mere decoration. The previous context-only interpretation was wrong:
small catalogue craters can have smooth/interpolated MOLA bins while optical
imagery clearly shows a rim. Equal heights are not an exit certificate.

The MOLA planner therefore excludes a conservative **rim band**, not the floor.
Its half width is the native cell-footprint half diagonal plus the explicit
100 m catalogue planning margin. This is uncertainty/clearance, not a fabricated
wall height or a measured wall width. It prevents edges (including diagonals)
from jumping a thin unknown boundary between open cell centres.

Floor-to-floor routing inside the same boundary remains possible. Crossing that
boundary requires finer numerical terrain, rather than assuming that coarse
heights prove a gradual exit. The separately prepared local CTX 20 m / HiRISE
1 m planners continue to use their numerical slopes. Missing catalogue data
fails closed. Published circle fits can contain errors and are not exact rims.

The native graph checks:

- 2D surface gradients, not only the height difference of distant endpoints;
- worst one-sided neighbouring grades, so a one-bin ridge cannot disappear
  through central-derivative cancellation;
- every native cell-to-cell transition;
- the two adjacent orthogonal cells of diagonal transitions (no corner cuts).
- unresolved catalogue rim bands, including point-to-cell anchors;
- a final independent spherical rim-intersection check of every output edge.

Absolute altitude is not a barrier: a gradual climb at high altitude remains
possible. No slope, boulder or soil property is estimated from optical shading.

### Search and resource bounds

The older coarse grid guides widening search corridors only. It does not
contribute output edges or heights. Long routes use intermediate **open native
cells** near that guide to bound computation; consecutive segments share the
same cell. There are no straight-line stitching links or mixed-resolution
transitions. Search is approximate globally, not a global shortest-path proof.

An exhausted budget, missing source tile, polar gap or disconnected checked
corridor returns an explicit failure, never the old coarse route as a fallback.
API wall-clock budget is 90 seconds for the expedition. Concurrent CPU work
can increase latency. The UI retains the user's camera and zoom on all results.

Long-search waypoints must remain in the endpoint's catalogue component, so
guidance cannot accidentally force a detour into an inaccessible crater floor.

Read-only memory mapping avoids loading the 3 GB source into RAM. Derived
256×256 slope blocks have a one-cell halo and a bounded cache.

### Display and exports

The 2D atlas requests a real native slope mask for its current close-up extent,
not just the original A/B regions. Red cells exceed the selected slope limit;
amber cells are the guarded uncertain rim band. Both are excluded from routing.
Grey cells lack usable numerical coverage. Route properties, profiles and
GeoJSON retain native-resolution validation and interpolation provenance.
The report no longer claims that whole crater discs are excluded.

## Verification

```
python scripts/prepare_mola128_global.py
python scripts/prepare_runtime_data.py
python -m unittest discover -s tests -p test_native_mola.py -v
python -m unittest discover -s tests -p test_rim_guard.py -v
python tests/smoke_traversability_browser.py
python tests/smoke_native_crater_browser.py
```

Tests cover floor-to-floor routing inside a catalogue crater, an impassable
closed rim, a real usable gap, two unrelated world locations, thin ridges,
gradual high-altitude climbs, source failure, tile seams, poles, and actual
floor routing within Gale crater.

The small-crater regression uses catalogue `02-4-06977`, diameter 1.21 km,
near `(-96.806, 24.044)`. All sampled straight-line DEM slopes are below 15°,
but that line crosses the known crater. The new path must detour and avoid
both the guarded mask and the spherical boundary. A separate synthetic case
uses an entirely flat DEM to ensure no slope-only shortcut can reappear.
Browser evidence is saved under `artifacts/global/rim-guard/`.

For the browser A/B `(-96.836, 24.044)` → `(-96.776, 24.044)`, the route
is ~4.87 km versus ~3.25 km direct. The straight segment touches guarded
cells at 104/201 test samples; the computed path touches none. The browser
also verifies matching exported guard provenance, continued floor-to-floor
routing in Gale, and rejection of an unverified exit without retaining a
stale route/report/export. The screenshot reproduces the reported failure
class on a known small crater, not the exact screenshot's unspecified A/B.

## Limits

463 m is grid spacing, **not rover-scale terrain accuracy**. Many equatorial
bins are officially interpolated. Unresolved narrow scarps, rocks and traction
remain unknown. A successful DEM path is not a certified drivable rover route,
and an unsuccessful bounded search is not proof that no physical route exists.
