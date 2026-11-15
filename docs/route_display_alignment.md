# Route/marker alignment on the globe

Route drawing no longer adds a radial offset of 0.002 world units (~6.8 km)
while pins add 0.008 (~27 km). Those unequal lifts caused perspective
displacement, especially at high zoom and away from the view centre.

`globeSurface.ts` projects both onto the actual deformed SphereGeometry
triangles. Adaptive subdivision follows the same spherical edge without
smoothing corners or skipping search vertices. A depth-only shader bias
prevents terrain z-fighting without changing projected X/Y. The camera near
plane is 0.01, with the existing minimum orbital radius preserved, improving
depth precision. Far-side route segments remain occluded.

Selected coordinates and DEM cell centres can legitimately differ. Separate
grey links show that association in both globe and atlas; they are explicitly
unverified, not included in route distance and not inserted into the exported
route geometry. Intermediate stops use cumulative leg/profile correspondence;
if that correspondence is absent, no invented intermediate link is drawn.
The atlas splits date-line crossings at ±180°, including coincident seam
coordinates, rather than joining across the whole map.

## Checks

```
node frontend/node_modules/esbuild/bin/esbuild tests/test_globe_surface.ts --bundle --platform=node --format=cjs --outfile=artifacts/zoom/test-globe-surface.cjs
node artifacts/zoom/test-globe-surface.cjs
python tests/smoke_globe_line.py
python tests/smoke_route_alignment.py
python tests/smoke_point_viewport.py
python tests/smoke_route_viewport.py
```

Geometry is compared with independent full-mesh raycasting on deformed terrain,
including exact mesh boundaries, poles and the date line. GPU tests inspect
actual route pixels at camera zoom 1–8192 and ensure far-side lines stay hidden.
The integrated browser scenario uses a real 463 m MOLA route and verifies that
the camera and exported geometry/distance remain unchanged.

Screenshots: `artifacts/zoom/route-alignment-{globe,atlas}.png`.
These reproduce the displacement class with a nearby route around the supplied
A coordinates, not the exact latest screenshot's unspecified A/B coordinates.
