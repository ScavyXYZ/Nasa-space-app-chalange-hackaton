"""Acquire official USGS/NASA Ames Viking colorized global browse; no 12GB TIFF.

This is a COLORIZED scientific mosaic, not true-color or global high-res DEM.
"""
import hashlib
import json
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
URL="https://astrogeology.usgs.gov/ckan/dataset/7131d503-cdc9-45a5-8f83-5126c0fd397e/resource/5ea881c6-01b3-41fa-a7af-42d2131b54f1/download/mars_viking_mdim21_clrmosaic_1km.jpg"
PAGE="https://astrogeology.usgs.gov/search/map/mars_viking_colorized_global_mosaic_232m"
AUX_URL="https://astrogeology.usgs.gov/ckan/dataset/7131d503-cdc9-45a5-8f83-5126c0fd397e/resource/69f3953f-9791-4d92-bffe-ebe24945eb95/download/mars_viking_mdim21_clrmosaic_1km.jpg.aux.xml"
# Known official 1km browse is ~228M pixels; retain a finite 240M pixel cap.
Image.MAX_IMAGE_PIXELS=240_000_000


def main():
    raw=ROOT/"data/raw/globe/mars_viking_mdim21_colorized_1km.jpg"
    out=ROOT/"data/processed/globe"
    raw.parent.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    aux=raw.with_suffix(".jpg.aux.xml")
    if not aux.exists():
        r=requests.get(AUX_URL,timeout=(20,60));r.raise_for_status()
        ET.fromstring(r.content)
        aux.write_bytes(r.content)
    doc=ET.parse(aux)
    transform=[float(v) for v in doc.findtext("GeoTransform","").split(",")]
    if len(transform)!=6 or transform[1]!=1000 or transform[5]!=-1000 or "3396190" not in doc.findtext("SRS",""):
        raise ValueError("Unexpected global browse spatial reference")
    if not raw.exists():
        temp=raw.with_suffix(".jpg.part")
        count=0
        with requests.get(URL,stream=True,timeout=(20,120)) as response,temp.open("wb") as stream:
            response.raise_for_status()
            for chunk in response.iter_content(1024*1024):
                count+=len(chunk)
                if count>60_000_000:
                    raise ValueError("Global browse exceeds 60MB budget")
                stream.write(chunk)
        with Image.open(temp) as image:
            image.verify()
        temp.rename(raw)
    with Image.open(raw) as image:
        native_size=list(image.size)
        if abs(image.width/image.height-2)>.02:
            raise ValueError("Expected full equirectangular 2:1 global coverage")
        if image.width*image.height>240_000_000:
            raise ValueError("Official browse exceeds expected pixel budget")
        # Downsample only for display. Original retained unchanged.
        image.draft("RGB",(4096,2048))
        display=image.convert("RGB").resize((4096,2048),Image.Resampling.LANCZOS)
        display.save(out/"mars_viking_colorized.jpg",quality=91,optimize=True)
    metadata={
        "title":"Mars Viking Colorized Global Mosaic (MDIM 2.1)",
        "provider":"USGS Astrogeology / NASA Ames / Viking Orbiter",
        "source_page":PAGE,"download_url":URL,
        "georeferencing_url":AUX_URL,"source_geotransform":transform,
        "raw_path":raw.relative_to(ROOT).as_posix(),"raw_size_bytes":raw.stat().st_size,
        "raw_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),
        "source_browse_dimensions":native_size,"display_dimensions":[4096,2048],
        "url":"/api/assets/mars-global.jpg",
        "bounds_lon_lat_deg":[-180,-90,180,90],
        "coordinate_system":"Planetocentric latitude, east-positive longitude; equirectangular",
        "color_note":"Official artistically colorized Viking/MDIM mosaic; NOT true-color photography.",
        "geometry_note":"Viking is an optical texture. Not a global DEM. Relief comes from the separate MOLA product.",
        "routing_note":"Approximate global routing uses MOLA through /api/global/route; detailed CTX/HiRISE routing remains in Jezero.",
        "source_product_native_m_per_pixel":231.5417872,
        "resolution_note":"Texture uses the official 1km browse resampled to 4096x2048; NOT 232m display resolution.",
    }
    (out/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(metadata,indent=2))


if __name__=="__main__":
    main()
