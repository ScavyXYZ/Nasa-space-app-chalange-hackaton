# Official atlas resources — staged, not yet runtime integrated

Reproduce with `python scripts/acquire_atlas_resources.py`.
URLs, byte counts and SHA-256 hashes are in `acquisition_manifest.json`.
The manifest's archive transfer count describes the latest run; reruns reuse
existing extracted members after checking their ZIP CRC.

## Downloaded

- USGS SIM 3292 global geology shapefile and companion files, metadata/readme.
  Verified using GDAL/pyogrio: **1,311 polygons**, fields `Unit`, `UnitDesc`,
  `SphArea_km`; Mars 2000 sphere (radius 3,396,190 m), geographic degrees.
  Map scale **1:20,000,000**. Not a local hazard or traversability map.
  Source: https://pubs.usgs.gov/sim/3292/
- NASA Mars Trek catalog: **146 layers**. `trek_shortlist.json` is a discovery
  shortlist; absence of service URLs there does not imply no service.
- Four independently retrieved WMTS capability documents and service records:
  MOLA/HRSC color hillshade blend (nominal 200 m/pixel), MOLA color hillshade
  (463 m/pixel), THEMIS daytime IR mosaic (100 m/pixel), THEMIS nighttime IR
  mosaic (100 m/pixel). Templates and endpoints: `verified_tile_services.json`.

## Important distinctions

WMTS hillshade/color/IR tiles are rendered images, **not numeric elevation
rasters**. Their pixel sizes do not establish vertical accuracy, observation
density, or equally detailed underlying measurements everywhere.
THEMIS IR mosaics are not live temperature measurements.

No automatic switch to these sources has been made in the application.
No high-resolution numeric MOLA tiles or rover images were downloaded in this
acquisition. Next steps are vector preprocessing, tile-client integration,
coverage/CRS validation, and separate numeric DEM acquisition.

The first acquisition transferred about 54.6 MB from an 808.9 MB ZIP using
HTTP ranges, omitting basemap rasters and unrelated files. Original shapefile
content is retained unchanged; a future display derivative should be separate.
