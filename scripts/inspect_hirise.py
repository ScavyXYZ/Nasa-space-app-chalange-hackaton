"""Inspect optional HiRISE via bounded HTTP range requests (no full download)."""
import json
from pathlib import Path
import requests
import rasterio
from rasterio.io import MemoryFile
from pyproj import Transformer
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
URL = "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif"


def main():
    record = {"url": URL, "full_download": False}
    with requests.get(URL, headers={"Range": "bytes=0-262143"}, stream=True, timeout=(20, 60)) as r:
        r.raise_for_status()
        record.update(http_status=r.status_code, content_range=r.headers.get("Content-Range"))
        if r.status_code != 206:
            record["status"] = "Server did not honour Range; stopped without full transfer."
        else:
            header = r.raw.read(262144)
            with MemoryFile(header) as memory, memory.open() as src:
                record.update(width=src.width, height=src.height, pixel_size_m=list(src.res),
                              crs_wkt=src.crs.to_wkt(), bounds=list(src.bounds), nodata=src.nodata,
                              status="Header inspected; suitable for future small-window acquisition, not part of MVP terrain.")
                with rasterio.open(ROOT / "data/processed/jezero_dem_crop.tif") as dem:
                    t = Transformer.from_crs(dem.crs, src.crs, always_xy=True)
                    x0, y0 = t.transform(dem.bounds.left, dem.bounds.bottom)
                    x1, y1 = t.transform(dem.bounds.right, dem.bounds.top)
                    record["selected_aoi_within_hirise_rectangular_bounds"] = box(*src.bounds).covers(box(x0,y0,x1,y1))
                    record["caveat"] = "Rectangular bounds coverage only; HiRISE valid-height coverage not sampled."
    (ROOT / "data/processed/hirise_feasibility.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
