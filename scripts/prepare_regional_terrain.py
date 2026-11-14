"""Extend CTX routing to the entire existing regional optical footprint.

Native 20m elevations are copied, never invented or resampled. The original
5km products remain untouched. A source halo supplies slopes at the boundary.
"""
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window, from_bounds

from process_dem import derive_slope
from download_nasa_data import checksum
from process_geology import main as process_geology
from build_gis_overlays import build
from shapely.geometry import shape, mapping
from shapely.ops import transform as transform_geometry

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/processed/regional"
SOURCE=ROOT/"data/raw/dem/M20_JezeroCrater_CTXDEM_20m.tif"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    context=json.loads((ROOT/"data/processed/gis/context_config.json").read_text())
    (south,west),(north,east)=context["bounds_lat_lon"]
    with rasterio.open(SOURCE) as src:
        crs=CRS(src.crs)
        if crs.ellipsoid.semi_major_metre!=3396190 or not np.allclose(src.res,[20,20]):
            raise ValueError("Expected native Mars CTX 20m DEM")
        forward=Transformer.from_crs(crs.geodetic_crs,crs,always_xy=True)
        inverse=Transformer.from_crs(crs,crs.geodetic_crs,always_xy=True)
        left,bottom=forward.transform(west,south);right,top=forward.transform(east,north)
        fractional=from_bounds(left,bottom,right,top,src.transform)
        col0,row0=math.floor(fractional.col_off),math.floor(fractional.row_off)
        col1,row1=math.ceil(fractional.col_off+fractional.width),math.ceil(fractional.row_off+fractional.height)
        window=Window(col0,row0,col1-col0,row1-row0)
        halo=Window(col0-1,row0-1,window.width+2,window.height+2)
        if halo.intersection(Window(0,0,src.width,src.height))!=halo:
            raise ValueError("Source DEM does not cover regional optical footprint plus halo")
        source=src.read(1,window=halo,masked=True)
        original=source.filled(np.nan)
        slopes,valid,scales=derive_slope(original,src.window_transform(halo))
        z=original[1:-1,1:-1].copy()
        s=slopes[1:-1,1:-1].copy()
        mask=valid[1:-1,1:-1]
        source_mask=~np.ma.getmaskarray(source)[1:-1,1:-1]
        z[~mask]=np.nan;s[~mask]=np.nan
        if mask.mean()<.9:
            raise ValueError(f"Regional DEM coverage too incomplete: {mask.mean():.2%}")
        transform=src.window_transform(window)
        profile=src.profile.copy()
        profile.update(width=z.shape[1],height=z.shape[0],transform=transform,
                       tiled=True,blockxsize=256,blockysize=256,compress="deflate")
        with rasterio.open(OUT/"jezero_dem_crop.tif","w",**profile) as dst:
            dst.write(np.where(mask,z,src.nodata),1)
            dst.update_tags(source_url="https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif",
                            acquisition="Native regional pixel window; source preserved")
        profile.update(nodata=-9999.)
        with rasterio.open(OUT/"jezero_slope.tif","w",**profile) as dst:
            dst.write(np.where(mask,s,-9999),1)
        np.save(OUT/"jezero_elevation.npy",z)
        np.save(OUT/"jezero_slope.npy",s)
        np.save(OUT/"jezero_valid_mask.npy",mask.astype("uint8"))
        np.save(OUT/"jezero_source_valid_mask.npy",source_mask)
        bounds=rasterio.windows.bounds(window,src.transform)
        bl=inverse.transform(bounds[0],bounds[1]);tr=inverse.transform(bounds[2],bounds[3])
        metadata={
            "source":"USGS Mars 2020 Science Investigation CTX DEM Mosaic",
            "source_url":"https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/ScienceInvestigationMaps_JPL/M20_JezeroCrater_CTXDEM_20m.tif",
            "dataset":"regional","shape_rows_cols":list(z.shape),"pixel_size_m":[20,20],
            "transform":list(transform),"crs_wkt":crs.to_wkt(),"geographic_crs_wkt":crs.geodetic_crs.to_wkt(),
            "mars_radius_m":3396190,"standard_parallel_deg":18.4663,
            "bounds_projected_m":list(bounds),"bounds_lon_lat_deg":[*bl,*tr],
            "optical_bounds_lon_lat_deg":[west,south,east,north],
            "nodata":src.nodata,"slope_nodata":-9999,"elevation_units":"m","slope_units":"degrees",
            "slope_method":"Central differences with native 1px source halo and Mars cos(latitude)/cos(18.4663) ground scale",
            "valid_pixels":int(mask.sum()),"total_pixels":int(mask.size),"valid_fraction":float(mask.mean()),
            "elevation_range_m":[float(np.nanmin(z)),float(np.nanmax(z))],
            "slope_range_deg":[float(np.nanmin(s)),float(np.nanmax(s))],
            "east_west_ground_cell_size_range_m":[float(20*scales[1:-1].min()),float(20*scales[1:-1].max())],
            "extent_projected_km":[z.shape[1]*.02,z.shape[0]*.02],
            "source_window_col_row_width_height":list(window.flatten()),
            "vertical_reference":"Original USGS MOLA-localized elevations retained; no vertical datum conversion",
            "caveat":"Coverage is not traversability. Slope, neighbour grade and NoData may prevent particular routes.",
        }
        (OUT/"terrain_metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
        # Independent derivation from original halo; no call to derive_slope.
        lat=(transform.f+(np.arange(z.shape[0])+.5)*transform.e)/3396190
        dx=20*np.cos(lat)/np.cos(np.deg2rad(18.4663))
        gx=(original[1:-1,2:]-original[1:-1,:-2])/(2*dx[:,None])
        gy=(original[2:,1:-1]-original[:-2,1:-1])/40
        expected=np.degrees(np.arctan(np.hypot(gx,gy)))
        assert np.allclose(s[mask],expected[mask],atol=1e-4)
        assert np.array_equal(z[mask],original[1:-1,1:-1][mask])
    process_geology(out=OUT,science_path=OUT/"points_of_interest.geojson")
    # Keep exact geometry for analysis/provenance, simplify only browser display.
    for filename in ["geology","points_of_interest"]:
        collection=json.loads((OUT/f"{filename}.geojson").read_text())
        for feature in collection["features"]:
            projected=transform_geometry(forward.transform,shape(feature["geometry"]))
            display=projected.simplify(15,preserve_topology=True)
            feature["geometry"]=mapping(transform_geometry(inverse.transform,display))
            feature["properties"]["display_geometry_note"]="Topology-preserving 15m simplification in Mars projected metres; exact geometry retained in regional source export."
        (OUT/f"{filename}_display.geojson").write_text(json.dumps(collection,separators=(",",":")),encoding="utf-8")
    build("regional","data/processed/regional","jezero","data/processed/regional")
    # Full-resolution missing-data overlay for honest routing coverage.
    from PIL import Image
    rgba=np.zeros((*mask.shape,4),dtype="uint8")
    rgba[~mask]=[255,80,90,160]
    Image.fromarray(rgba).save(OUT/"nodata_overlay.png")
    outputs=[p for p in OUT.glob("*") if p.is_file() and p.name!="validation_report.json"]
    report={"status":"passed","shape":list(z.shape),"valid_cells":int(mask.sum()),"valid_fraction":float(mask.mean()),
            "checks":["source_pixel_equality","Mars_CRS","native_20m_resolution","optical_footprint_covered",
                      "slope_independent_recalculation_with_halo","common_masks","original_5km_products_unchanged"],
            "files":[{"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":checksum(p)} for p in outputs]}
    (OUT/"validation_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(metadata,indent=2))


if __name__=="__main__":
    main()
