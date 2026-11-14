"""Export SIM 3464 mapped regions, retaining source geometry and attributes.

GeoJSON coordinates are Mars east-positive longitude, planetocentric latitude,
NOT terrestrial WGS84. Science entries are documented REGIONS, not invented
point positions. Original mapped geometry is clipped to the terrain footprint.
"""
import json
from pathlib import Path

import numpy as np
import rasterio
from pyogrio.raw import read
from pyproj import CRS, Transformer
from shapely import from_wkb, make_valid
from shapely.geometry import box, mapping
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed"
DOI = "https://doi.org/10.3133/sim3464"
DISCLAIMER = "SIM3464 semi-controlled mapping has ~100–200 m offsets from the TRN CTX mosaic; no alignment correction applied."


def collection(features):
    return {"type": "FeatureCollection", "features": features,
            "coordinate_system": "Mars 2000 sphere; east-positive longitude, planetocentric latitude, degrees; NOT WGS84",
            "source": DOI, "registration_warning": DISCLAIMER}


def main(out=OUT,science_path=None):
    out=Path(out)
    science_path=Path(science_path) if science_path else ROOT/"science/points_of_interest.geojson"
    gdb = next((ROOT / "data/raw/geology/extracted").rglob("*.gdb"))
    meta, fids, wkbs, attrs = read(gdb, layer="GeoUnits_v1", return_fids=True)
    with rasterio.open(out / "jezero_dem_crop.tif") as dem:
        dem_crs = CRS(dem.crs)
        to_dem = Transformer.from_crs(meta["crs"], dem_crs, always_xy=True)
        to_geo = Transformer.from_crs(dem_crs, dem_crs.geodetic_crs, always_xy=True)
        aoi = box(*dem.bounds)
    features, by_name = [], {}
    for i, wkb in enumerate(wkbs):
        geom = transform(to_dem.transform, make_valid(from_wkb(wkb)))
        if not geom.intersects(aoi):
            continue
        clipped = geom.intersection(aoi)
        if clipped.area <= 0:
            continue
        properties = {}
        for field, values in zip(meta["fields"], attrs):
            value = values[i]
            if isinstance(value, np.generic):
                value = value.item()
            properties[field] = value
        properties.update(source=DOI, source_layer="GeoUnits_v1",
                          source_fid=int(fids[i]), registration_warning=DISCLAIMER)
        features.append({"type": "Feature", "geometry": mapping(transform(to_geo.transform, clipped)),
                         "properties": properties})
        by_name.setdefault(properties["name"], []).append((clipped, properties))
    (out / "geology.geojson").write_text(json.dumps(collection(features), indent=2), encoding="utf-8")
    # These are real mapped geological regions with original published names.
    # No centroids or arbitrary point coordinates are presented as named targets.
    interests = {
        "Jezero fan 1 unit": ("Published mapped fan deposit in Jezero crater.",
                             "Investigate the mapped fan stratigraphy and its relation to former sediment transport."),
        "Jezero fan 2 unit": ("Published second mapped fan unit in Jezero crater.",
                             "Compare spatial relationships between the two mapped fan units."),
        "Jezero floor unit": ("Published geologic unit on the floor of Jezero crater.",
                              "Study the mapped crater-floor context relative to fan deposits."),
        "Eolian bedform unit": ("Published mapped eolian bedform region.",
                               "Investigate wind-driven surface modification and possible traverse complexity."),
        "Smooth unit, undivided": ("Published undivided smooth terrain unit.",
                                  "Compare mapped surface morphology with adjacent units."),
        "Crater interior unit": ("Published crater-interior geologic unit.",
                                "Study crater-interior material and its mapped relation to surrounding terrain."),
    }
    pois = []
    for name, regions in by_name.items():
        geom = unary_union([g for g, _ in regions])
        desc, interest = interests.get(name, (
            f"Region mapped as '{name}' in USGS SIM 3464.",
            "Compare this mapped geologic unit with adjacent terrain; interpretation should follow the source map."))
        pois.append({"type": "Feature", "geometry": mapping(transform(to_geo.transform, geom)),
                     "properties": {"name": name, "description": desc, "research_interest": interest,
                                    "location_type": "source-mapped region clipped to AOI, not a point",
                                    "source": DOI,
                                    "source_download": "https://pubs.usgs.gov/sim/3464/sim3464_database.zip",
                                    "source_layer": "GeoUnits_v1",
                                    "source_fids": [p["source_fid"] for _, p in regions],
                                    "photo_url": None, "registration_warning": DISCLAIMER}})
    science_path.write_text(
        json.dumps(collection(pois), indent=2), encoding="utf-8")
    legend = [{"name": name, "symbols": sorted({p["symbol"] for _, p in rows}),
               "source": DOI, "color_note": "Use application display colors; original map symbols retained."}
              for name, rows in by_name.items()]
    (out / "geology_legend.json").write_text(json.dumps(legend, indent=2), encoding="utf-8")
    print(f"Exported {len(features)} polygons and {len(pois)} sourced scientific regions: {list(by_name)}")
    if len(pois) < 3:
        raise ValueError("AOI contains fewer than 3 mapped scientific regions; revise AOI.")


if __name__ == "__main__":
    main()
