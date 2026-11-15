# Crater-crossing report: model limitations and display correction

Reported endpoints (longitude, latitude, Mars planetocentric):

- A: `(-97.150761, 24.024217)`
- B: `(150.624967, 9.070396)`

Both are outside the **loaded** Jezero CTX/HiRISE DEM coverage. This does
not imply that no other regional DEM exists in external archives.
The current auto route therefore uses MOLA 16 ppd (`0.0625°`,
about `3704.5 m` equatorial spacing).

Reproduction with the default 15° gradient limit and slope weight 5:

- Route length: approximately 6518 km; direct distance: 6287 km.
- 1797 grid cells, including 31 officially interpolated bins.
- Maximum **between-bin** gradient: approximately 11.25°.
- Endpoint snapping offsets: approximately 512 m and 2292 m.

These values do not verify the photographed crater rim's gradient or rover
passability. Endpoint coordinates alone do not identify the exact crater in
the screenshot. A coarse valid graph path can cross a sub-cell cliff; changing
the graph search does not reconstruct missing elevations. No obstacle was
invented or automatic safe bypass claimed.

## Correction

Graph-search `status: ok` is now explicitly separate from the assessment:
`traversability.status: unverified`. Global results have scope
`strategic_corridor`, not a validated rover path. The assessment also lives
in GeoJSON properties and survives ordered multi-leg assembly.

The global line is amber/dashed in the globe, 2D atlas and exported report.
A prominent map notice explains that the line can cross impassable terrain.
The gradient readout explicitly describes MOLA-bin gradients, not maximum
local slopes. Local DEM paths remain unverified for physical traversability
because boulders and soil traction are not measured by the current model.

This fixes a misleading presentation, **not the missing detailed DEM or the
actual crater crossing**. A verified bypass needs georeferenced local terrain
and hazard measurements, or explicitly reviewed exclusion geometry.

Regression coverage:

- `tests/test_global_routing.py`: exact reported endpoints, plus a completely
  flat observed grid that must still not become a verified rover path.
- `tests/test_atlas.py`: local DEM graph optimality does not imply safety.
- `tests/smoke_traversability_browser.py`: the exact endpoints, persistent
  warning, dashed report and machine-readable GeoJSON assessment.
