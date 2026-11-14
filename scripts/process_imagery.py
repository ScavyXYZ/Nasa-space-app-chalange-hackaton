"""Small real CTX crop + Mars-geographic PNG image overlay for Leaflet."""
import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from matplotlib import pyplot as plt
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed"


def main():
    with rasterio.open(OUT / "jezero_dem_crop.tif") as dem:
        crs = CRS(dem.crs)
        to_geo = Transformer.from_crs(crs, crs.geodetic_crs, always_xy=True)
        west, south = to_geo.transform(dem.bounds.left, dem.bounds.bottom)
        east, north = to_geo.transform(dem.bounds.right, dem.bounds.top)
        transform = dem.transform
        width, height = dem.width, dem.height
        z = dem.read(1, masked=True)
    with rasterio.open(ROOT / "data/raw/imagery/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif") as src:
        profile = src.profile.copy()
        # Projected crop at 5m (rendering grid only; source remains native 6m).
        dest_transform = transform * Affine.scale(0.25, 0.25)
        profile.update(width=width*4, height=height*4, crs=crs.to_wkt(),
                       transform=dest_transform, compress="deflate")
        image = np.zeros((height*4, width*4), dtype="uint8")
        reproject(rasterio.band(src, 1), image, src_nodata=0, dst_nodata=0,
                  dst_transform=dest_transform, dst_crs=crs.to_wkt(), resampling=Resampling.bilinear)
        with rasterio.open(OUT / "jezero_ctx_crop.tif", "w", **profile) as dst:
            dst.write(image, 1)
        # Geographic grid for Leaflet EPSG4326-style angular display only.
        geographic_transform = from_bounds(west, south, east, north, width*4, height*4)
        geographic_image = np.zeros_like(image)
        reproject(rasterio.band(src, 1), geographic_image, src_nodata=0, dst_nodata=0,
                  dst_transform=geographic_transform, dst_crs=crs.geodetic_crs.to_wkt(),
                  resampling=Resampling.bilinear)
    rgba = np.stack([geographic_image]*3 + [np.where(geographic_image != 0, 255, 0).astype("uint8")], axis=-1)
    Image.fromarray(rgba).save(OUT / "jezero_ctx_overlay.png")
    config = {
        "title": "USGS Mars 2020 TRN CTX orthomosaic", "type": "imageOverlay",
        "url": "/data/processed/jezero_ctx_overlay.png",
        "bounds_lat_lon": [[south, west], [north, east]],
        "display_crs": "Leaflet L.CRS.EPSG4326 angular display with custom Mars distance",
        "coordinate_semantics": "Mars planetocentric degrees, east-positive; NOT terrestrial WGS84",
        "mars_radius_m": 3396190, "source_native_resolution_m": 6,
        "projected_render_grid_m": 5,
        "native_resolution_warning": "5m render grid is resampling, not 5m measured imagery.",
        "attribution": "NASA/MRO/CTX; USGS Astrogeology",
        "source": "https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_context_camera_orthorectified_image_mosaic",
        "valid_fraction": float((geographic_image != 0).mean()),
    }
    (OUT / "imagery_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    slope = np.load(OUT / "jezero_slope.npy")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    for ax, data, title, cmap in zip(axes, [z, slope, image],
                                     ["CTX elevation (m)", "Derived slope (degrees)", "CTX optical (native 6 m)"],
                                     ["terrain", "magma", "gray"]):
        im = ax.imshow(data, cmap=cmap, extent=[west, east, south, north])
        ax.set_title(title)
        ax.set_xlabel("East longitude (Mars)")
        ax.set_ylabel("Planetocentric latitude")
        fig.colorbar(im, ax=ax, shrink=0.7)
    fig.savefig(OUT / "terrain_quality_check.png", dpi=140)
    plt.close(fig)
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
