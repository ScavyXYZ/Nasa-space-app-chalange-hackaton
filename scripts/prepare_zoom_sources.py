"""Discover official high-detail optical WMTS sources, preserving coverage limits."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parents[1]
NS={"w":"http://www.opengis.net/wmts/1.0","o":"http://www.opengis.net/ows/1.1"}
SOURCES={
    "viking-hd":("Mars_Viking_MDIM21_ClrMosaic_global_232m",232,"colorized"),
    "ctx-global":("CTX_beta01_uncontrolled_5m_Caltech",5,"grayscale"),
    "ctx-jezero":("JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0",6,"grayscale"),
    "hirise-jezero":("JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd",.25,"grayscale"),
}


def main():
    folder=ROOT/"data/processed/atlas"
    raw=ROOT/"data/raw/atlas"
    docs=json.loads((raw/"mars_trek_layers.json").read_text())["response"]["docs"]
    catalog=json.loads((folder/"tiles.json").read_text())
    catalog=[c for c in catalog if c["id"] not in SOURCES]
    for key,(product,resolution,color) in SOURCES.items():
        source=next(d for d in docs if d["productLabel"]==product)
        url="https://trek.nasa.gov/mars/TrekServices/ws/index/getLayerServices?uuid="+source["item_UUID"]
        r=requests.get(url,timeout=(15,60));r.raise_for_status()
        endpoint=r.json()["response"]["docs"][0]["endPoint"].rstrip("/")
        if not endpoint.startswith("https://trek.nasa.gov/tiles/Mars/"):
            raise ValueError("Unexpected official endpoint")
        capabilities=endpoint+"/1.0.0/WMTSCapabilities.xml"
        r=requests.get(capabilities,timeout=(15,60));r.raise_for_status()
        (raw/f"{product}_capabilities.xml").write_bytes(r.content)
        doc=ET.fromstring(r.content)
        layer=doc.find(".//w:Layer",NS)
        box=layer.find("o:BoundingBox",NS)
        lower=[float(v) for v in box.findtext("o:LowerCorner",namespaces=NS).split()]
        upper=[float(v) for v in box.findtext("o:UpperCorner",namespaces=NS).split()]
        resource=layer.find("w:ResourceURL",NS)
        matrices=doc.findall(".//w:Contents/w:TileMatrixSet/w:TileMatrix",NS)
        entry={"id":key,"title":source["title"],"endpoint":endpoint,
                        "template":resource.attrib["template"].replace("//{Style}","/{Style}"),
                        "style":layer.findtext("w:Style/o:Identifier",namespaces=NS),
                        "matrix_set":layer.findtext("w:TileMatrixSetLink/w:TileMatrixSet",namespaces=NS),
                        "matrices":[m.findtext("o:Identifier",namespaces=NS) for m in matrices],
                        "format":resource.attrib["format"],"source":capabilities,
                        "bounds":[*lower,*upper],"nominal_m_per_pixel":resolution,"appearance":color,
                        "note":"Optical imagery only; not a numeric DEM. Coverage/registration vary; CTX global is uncontrolled."}
        if key=="ctx-global":
            service_url="https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer?f=pjson"
            response=requests.get(service_url,timeout=(15,60));response.raise_for_status()
            service=response.json()
            info=service["tileInfo"]
            if info["origin"]!={"x":-180,"y":90} or info["cols"]!=512:
                raise ValueError("Unexpected CTX tile geometry")
            (raw/"ctx_global_service.json").write_text(json.dumps(service,indent=2),encoding="utf-8")
            entry["matrices"]=[str(lod["level"]) for lod in info["lods"]]
            entry["native_tile_size"]=512
            entry["max_useful_zoom"]=13
            entry["service_metadata"]=service_url
            entry["credit"]="NASA/JPL/MSSS/Caltech Murray Lab/Esri"
            entry["note"]+=" Native service has 512px tiles; very high levels oversample the ~5m imagery."
        catalog.append(entry)
        print(key,len(matrices),lower,upper)
    (folder/"tiles.json").write_text(json.dumps(catalog,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
