"""Render real terrain to geographic Mars PNGs for QA (never analytical DEMs)."""
import json
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parents[1]


def build(dataset, relative, prefix, destination):
    source = ROOT / relative
    out = ROOT / destination
    out.mkdir(parents=True, exist_ok=True)
    config = {"dataset":dataset,"coordinate_system":"Mars planetocentric degrees; east-positive; NOT WGS84",
              "rendering":"Geographic PNGs for EPSG4326-style angular display; never sample these as elevation.",
              "overlays":[]}
    for kind, suffix, cmap, units in [
        ("elevation","dem_crop","terrain","m"), ("slope","slope","magma","degrees")
    ]:
        with rasterio.open(source / f"{prefix}_{suffix}.tif") as src:
            crs = CRS(src.crs)
            geo = Transformer.from_crs(crs,crs.geodetic_crs,always_xy=True)
            west,south = geo.transform(src.bounds.left,src.bounds.bottom)
            east,north = geo.transform(src.bounds.right,src.bounds.top)
            size = min(src.width,1000)
            dest = np.full((size,size),np.nan,dtype="float32")
            transform = from_bounds(west,south,east,north,size,size)
            reproject(rasterio.band(src,1),dest,src_nodata=src.nodata,dst_nodata=np.nan,
                      dst_transform=transform,dst_crs=crs.geodetic_crs.to_wkt(),
                      resampling=Resampling.nearest)
        valid = np.isfinite(dest)
        low,high = (float(np.nanmin(dest)),float(np.nanmax(dest))) if kind=="elevation" else (0.,45.)
        scaled = np.where(valid,np.clip((dest-low)/max(high-low,1e-8),0,1),0)
        rgba = colormaps[cmap](scaled,bytes=True)
        rgba[~valid,3] = 0
        Image.fromarray(rgba).save(out / f"{kind}_overlay.png")
        config["overlays"].append({
            "name":kind,"url":f"/api/assets/{dataset}-{kind}.png",
            "bounds_lat_lon":[[south,west],[north,east]],
            "legend":{"units":units,"min":low,"max":high,"colormap":cmap,
                      "note":"Display scale; slopes above 45deg saturate. NoData transparent."},
        })
    (out / "overlay_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    print(f"Built Mars-geographic {dataset} overlays in {out}")


if __name__ == "__main__":
    build("ctx","data/processed","jezero","data/processed/gis")
    if (ROOT / "data/processed/hirise/terrain_metadata.json").is_file():
        build("hirise","data/processed/hirise","jezero_hirise","data/processed/hirise")
