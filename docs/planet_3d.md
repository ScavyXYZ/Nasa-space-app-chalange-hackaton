# Continuous adaptive Mars 3D

**Historical implementation.** Terrain relief, oblique views and the local
3D viewer have been removed from the current interface at the user's request.
The ordinary imagery globe and 2D atlas remain; numeric DEM routing is unchanged.
See `design-system/mars-explorer/pages/workspace.md` for the current UI scope.

The planetary view now renders **one connected global surface**, rather than a
coarse sphere underneath independently raised regional terrain patches. There
are no separate terrain tiles, skirts, holes while loading or triangle cracks
between LOD levels. Source imagery remains separate from numerical relief.

## Geometry and provenance

- `algorithms/planet_surface.py`: a globally connected nonuniform geographic
  grid. A 2° background covers both hemispheres; nested, dyadic axis samples
  concentrate vertices near the current view.
- Levels 0–8. Finest display axis step is 1/128°, matching the native MOLA grid.
  The source spacing is approximately 463m north/south and shrinks east/west
  with latitude. Higher visual zoom does not create new measured terrain.
- Height samples use bilinear interpolation of the actual memory-mapped NASA
  PDS MEGDR numerical heights. Observation-count zero remains official source
  interpolation; display interpolation does not establish traversability.
- Native coverage is −88°…88°. The uncovered polar caps blend to the existing
  coarse MOLA overview and meet at a shared pole height. This is explicitly a
  display fallback, never an extension of native routing coverage.
- `GET /api/global/surface?lon=…&lat=…&level=0…8`: bounded full-sphere data,
  quantised focus, eight-entry encoded response cache and two generation slots.
  Sparse numerical sampling does not read huge rectangular source windows.
- `adaptiveGlobe.ts` retains the previous complete mesh until a complete new
  one is ready, then swaps atomically. It does not continuously geomorph
  triangles or claim photogrammetry from optical images.
- Fewer than 220,000 vertices per mesh; four recently used surface responses
  retained in the browser. Old GPU geometry is disposed on replacement.
- Duplicate antimeridian coordinates and normals agree. All grid cells share
  their interior edges; no per-tile terrain seams or height offsets.

## Texture

Run once using the original, already retained official browse:

```powershell
python scripts/prepare_planet_imagery.py
```

This creates `data/processed/globe/imagery/`: all 2,730 local image chunks for
levels 0–5 and their provenance manifest. Highest full-planet level is
16,384×8,192, approximately **1,302m/pixel at the equator**. It is a downsampled
official 1km Viking browse, not the original 232m product and not true color.

The browser composes georeferenced image chunks into one bounded surface texture.
Internal chunking is necessary for memory and is not hidden as an accuracy
claim. The distant view uses local Viking levels without external imagery.
**Close zoom automatically replaces Viking with actual grayscale CTX photos
on the same 3D mesh**, then controlled CTX / HiRISE where those sources cover
the view. No manual HD activation is required. Source levels above the local
Viking maximum (5) select the appropriate optical source.

“Автознімки HD” is enabled by default; disabling it is an explicit local-only
option. Online imagery retains genuine source gaps, fallback behavior and
registration limits. It does not improve numerical elevation accuracy.
Topography is a separate user-selected mode using local MOLA colors.

The brown-to-photo transition waits for a coherent coarse optical overview,
then crossfades for 280ms (immediate with reduced motion). Coarse CTX is drawn
**above** opaque Viking pixels; finer original cached/native imagery is restored
above it. This avoids an initially brown preview or an isolated grey checkerboard.
At most two composed GPU atlases are retained during the short transition.
Native photos refine the overview without clearing loaded overlap.

## Interaction

“Ракурс 3D” enables an oblique inspection view when zoomed in. The rendering
camera pivots around the actual currently rendered geographic centre; the
navigation camera, zoom and chosen points remain unchanged. LOD selection
uses the local rendered radius, including visual height exaggeration, not a
datum sphere underneath a mountain. Picking uses the same displayed camera
and actual mesh triangles.

`globeSurface.ts` follows mesh replacement and finds the correct nonuniform
cell. Routes, snaps, pins and crater outlines are re-draped before drawing the
new surface. **Route computations and exported source geometry are unchanged**.
Neither a smooth 3D appearance nor a finer display mesh certifies a crater exit.

## Verification

```powershell
python -m unittest discover -s tests -v
npm --prefix frontend run build
python tests/smoke_planet_browser.py --url http://127.0.0.1:8004
python tests/smoke_point_viewport.py --url http://127.0.0.1:8004
python tests/smoke_route_viewport.py --url http://127.0.0.1:8004
python tests/smoke_route_alignment.py --url http://127.0.0.1:8004
python tests/smoke_photo_globe_browser.py --url http://127.0.0.1:8003
```

`tests/test_planet_surface.ts` independently raycasts the nonuniform mesh
after geometry replacement and checks seam positions/normals. Bundle with the
existing esbuild dependency and define `import.meta.env` as `{}` for Node.
Browser evidence is in `artifacts/planet/`.

Verified locally:

- Production TypeScript/Vite build; full 96-test Python suite and focused
  surface tests after increasing intermediate mesh density.
- New browser scenario: 16,471 initial vertices → 94,962 native-detail vertices;
  zero distant-overview WMTS requests; numeric failure retains the last mesh;
  automatic close-up photos; oblique/picking camera invariance; mobile/tablet.
- Actual Gale CTX photos rendered on MOLA: approximately 99.7% of the tested
  central area has grayscale photographic pixels, not brown Viking fallback.
  Zoom-out restores Viking; topography/satellite round-trip retains the camera.
- Independent nonuniform geometry raycast error <1e-9 sphere radii, identical
  seam positions/normals, and draping follows geometry replacement.
- Existing point/route viewport, exact export alignment, crater detour/floor/
  rejected-exit, design/contrast, optical HD zoom and local Jezero 3D scenarios.
- Local image pyramid: 2,730 images, 50.78MB total. Native numerical sources
  were reused unchanged; no new imagery service or download subscription.
