"""Render the existing regional USGS CTX mosaic, without extending DEM coverage."""
import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/imagery/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif"
OUT = ROOT / "data/processed/gis"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with rasterio.open(SOURCE) as src:
        crs = CRS(src.crs)
        geo = Transformer.from_crs(crs,crs.geodetic_crs,always_xy=True)
        west,south = geo.transform(src.bounds.left,src.bounds.bottom)
        east,north = geo.transform(src.bounds.right,src.bounds.top)
        width = 2200
        height = round(width*src.height/src.width)
        image = np.zeros((height,width),dtype="uint8")
        reproject(rasterio.band(src,1),image,src_nodata=src.nodata,dst_nodata=0,
                  dst_transform=from_bounds(west,south,east,north,width,height),
                  dst_crs=crs.geodetic_crs.to_wkt(),resampling=Resampling.bilinear)
        config = {
            "title":"USGS regional CTX optical context",
            "url":"/api/assets/ctx-context.png",
            "bounds_lat_lon":[[south,west],[north,east]],
            "source_native_resolution_m":6,
            "render_dimensions":[height,width],
            "regional_projected_size_m":[src.bounds.right-src.bounds.left,src.bounds.top-src.bounds.bottom],
            "source_url":"https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif",
            "coordinate_system":"Mars sphere 3396190m, planetocentric, east-positive. Not WGS84.",
            "coverage_note":"Optical context only; routing/elevation remain limited to the CTX or HiRISE DEM footprint.",
            "nodata":"Original zero-valued NoData is transparent; no missing surface generated.",
        }
    rgba = np.stack([image,image,image,np.where(image!=0,255,0).astype("uint8")],axis=-1)
    Image.fromarray(rgba).save(OUT/"context_overlay.png")
    (OUT/"context_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    print(json.dumps(config,indent=2))


if __name__=="__main__":
    main()
