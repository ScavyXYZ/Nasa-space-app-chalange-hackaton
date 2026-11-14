"""Bounded 3D display mesh from measured DEM cells, with conservative NoData holes."""
import math
import numpy as np


def terrain_mesh(terrain, max_size=220):
    rows,cols=terrain.shape
    stride=max(1,math.ceil(max(rows,cols)/max_size))
    rr=np.unique(np.r_[np.arange(0,rows,stride),rows-1]).astype(int)
    cc=np.unique(np.r_[np.arange(0,cols,stride),cols-1]).astype(int)
    valid=terrain.valid.astype(bool)
    origin_height=float(terrain.elevation[valid].min())
    x0,y0=terrain.affine*(cols/2,rows/2)
    lon0,lat0=terrain.inverse.transform(x0,y0)
    lons=[terrain.lonlat(0,int(c))[0] for c in cc]
    lats=[terrain.lonlat(int(r),0)[1] for r in rr]
    elevations=[]
    slopes=[]
    positions=[]
    for r,lat in zip(rr,lats):
        for c,lon in zip(cc,lons):
            ok=bool(valid[r,c])
            height=float(terrain.elevation[r,c]) if ok else None
            elevations.append(height)
            slopes.append(float(terrain.slope[r,c]) if ok else None)
            positions.extend([3396190*math.radians(lon-lon0)*math.cos(math.radians(lat)),
                              height-origin_height if ok else 0,
                              -3396190*math.radians(lat-lat0)])
    # A coarse display cell must not bridge even a thin native NoData gap.
    bad=np.pad((~valid).astype("int32"),((1,0),(1,0))).cumsum(0).cumsum(1)
    indices=[]
    width=len(cc)
    for i in range(len(rr)-1):
        for j in range(len(cc)-1):
            top,bottom,left,right=rr[i],rr[i+1]+1,cc[j],cc[j+1]+1
            missing=bad[bottom,right]-bad[top,right]-bad[bottom,left]+bad[top,left]
            if missing:
                continue
            a=i*width+j;b=a+1;c=a+width;d=c+1
            indices.extend([a,c,b,b,c,d])
    return {
        "dataset":terrain.dataset,"shape":[len(rr),len(cc)],"source_shape":list(terrain.shape),
        "sample_rows":rr.tolist(),"sample_cols":cc.tolist(),"stride":stride,
        "longitudes":lons,"latitudes":lats,
        "positions_m":positions,"elevations_m":elevations,"slopes_deg":slopes,"indices":indices,
        "origin_lon_lat":[lon0,lat0],"elevation_origin_m":origin_height,
        "elevation_range_m":[origin_height,float(terrain.elevation[valid].max())],
        "radius_m":3396190,"units":"metres; x=east, y=height above display origin, z=south",
        "source":"USGS CTX/HiRISE DEM; sampled original heights, no invented terrain",
        "note":"Display mesh only; triangles interpolate between native samples. NoData rectangles are omitted. A* uses the original full-resolution grid.",
    }
