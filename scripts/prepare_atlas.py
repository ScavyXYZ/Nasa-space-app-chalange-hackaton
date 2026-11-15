"""Build reproducible global geology display, query index and WMTS catalog."""
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pyogrio
from pyogrio.raw import read
from PIL import Image, ImageDraw
from shapely import make_valid, to_wkb, from_wkb
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]


def main():
    raw = ROOT/"data/raw/atlas"
    out = ROOT/"data/processed/atlas"
    out.mkdir(parents=True, exist_ok=True)
    meta, _, source_wkb, attrs = read(raw/"geology/SIM3292_Global_Geology.shp")
    rows = [dict(zip(meta["fields"], values)) for values in zip(*attrs)]
    if "3396190" not in meta["crs"] or len(rows) != 1311:
        raise ValueError("Unexpected global geology source")
    palette = ["#bd8267", "#829fa2", "#a1a27d", "#b9a0bc", "#b6aa87", "#73979d",
               "#bd9480", "#9ba9ba", "#c8b684", "#8f9f83", "#c28e98", "#a29eae"]
    units = sorted({row["Unit"] for row in rows})
    colors = {u: palette[i % len(palette)] for i, u in enumerate(units)}
    legend = [{"unit": u, "description": str(next(r["UnitDesc"] for r in rows if r["Unit"] == u)),
               "color": colors[u]} for u in units]
    features, wkbs, properties = [], [], []
    image = Image.new("RGBA", (2048, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for row, wkb in zip(rows, source_wkb):
        geom = make_valid(from_wkb(wkb))
        prop = {"id": int(row["OBJECTID"]), "unit": str(row["Unit"]), "description": str(row["UnitDesc"]),
                "source": "https://doi.org/10.3133/sim3292", "color": colors[row["Unit"]]}
        wkbs.append(to_wkb(geom).hex())
        properties.append(prop)
        simplified = geom.simplify(.035, preserve_topology=True)
        features.append({"type": "Feature", "geometry": mapping(simplified), "properties": prop})
        parts = list(simplified.geoms) if hasattr(simplified, "geoms") else [simplified]
        for polygon in parts:
            if polygon.geom_type != "Polygon":
                continue
            def pixels(ring):
                return [((lon+180)/360*2048, (90-lat)/180*1024) for lon, lat, *_ in ring.coords]
            draw.polygon(pixels(polygon.exterior), fill=prop["color"], outline="#192631")
            for hole in polygon.interiors:
                draw.polygon(pixels(hole), fill=(0, 0, 0, 0))
    image.save(out/"geology.png")
    collection = {"type": "FeatureCollection", "features": features,
                  "notice": "Display simplified 0.035 degrees. Queries use original source polygons. Mars, not WGS84."}
    (out/"geology_display.geojson").write_text(json.dumps(collection, separators=(",", ":")), encoding="utf-8")
    with gzip.open(out/"geology_query.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"wkb": wkbs, "properties": properties}, stream, separators=(",", ":"))
    (out/"geology_legend.json").write_text(json.dumps(legend, indent=2), encoding="utf-8")
    services = json.loads((raw/"verified_tile_services.json").read_text())
    ns = {"w": "http://www.opengis.net/wmts/1.0", "o": "http://www.opengis.net/ows/1.1"}
    catalog = []
    for i, service in enumerate(services):
        doc = ET.parse(raw/f"{service['product']}_capabilities.xml")
        layer = doc.find(".//w:Layer", ns)
        style = layer.find("w:Style/o:Identifier", ns).text
        matrix_set = layer.find("w:TileMatrixSetLink/w:TileMatrixSet", ns).text
        matrices = doc.findall(".//w:Contents/w:TileMatrixSet/w:TileMatrix", ns)
        matrix_ids = [m.findtext("o:Identifier", namespaces=ns) for m in matrices]
        catalog.append({"id": ["hrsc", "mola", "themis-day", "themis-night"][i],
                        "title": service["title"], "endpoint": service["endpoint"],
                        "template": service["resources"][0]["template"].replace("//{Style}", "/{Style}"),
                        "style": style, "matrix_set": matrix_set, "matrices": matrix_ids,
                        "format": service["resources"][0]["format"],
                        "source": service["capabilities_url"],
                        "note": "Rendered imagery, not numeric heights or live temperature."})
    metadata = {"source": "https://doi.org/10.3133/sim3292", "features": len(features),
                "scale": "1:20,000,000", "units": len(units), "display_tolerance_deg": .035,
                "coordinate_system": "Mars 2000 sphere 3396190m, planetocentric/east-positive",
                "notice": "Global geological context; not local hazards or a safety assessment.",
                "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in out.iterdir() if p.is_file() and p.name != "metadata.json"}}
    (out/"tiles.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    (out/"metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"geology": metadata, "tiles": catalog}, indent=2))


if __name__ == "__main__":
    main()
