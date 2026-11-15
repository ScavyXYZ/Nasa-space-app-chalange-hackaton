"""Conservative catalogue-rim guard for DEMs that do not resolve small walls.

Flat/coincident DEM heights are NOT evidence of a crater exit. The catalogue
defines an uncertain rim band, not an invented elevation or a blocked floor.
Detailed local CTX/HiRISE planners use their own numerical terrain instead.
"""
from functools import lru_cache
import math

import numpy as np
from shapely import box

RADIUS=3396000.


class CatalogueRimGuard:
    block_size=256

    def __init__(self,catalogue,ppd=128):
        self.catalogue=catalogue;self.ppd=ppd
        self.spacing_m=2*math.pi*RADIUS/(360*ppd)
        # Cell-footprint half diagonal + the explicit catalogue planning margin.
        # This is uncertainty/clearance, not measured wall width or height.
        self.half_width_m=self.spacing_m/math.sqrt(2)+catalogue.buffer_m

    def window(self,r0,r1,c0,c1):
        mask=np.zeros((r1-r0,c1-c0),dtype=bool)
        west=(c0/self.ppd+180)%360-180
        east=west+(c1-c0)/self.ppd
        north=90-r0/self.ppd;south=90-r1/self.ppd
        pad=math.degrees(self.half_width_m/RADIUS)
        dx=pad/max(.01,math.cos(math.radians(max(abs(north),abs(south)))))
        candidates=[]
        for shift in (-360,0,360):
            candidates.extend(self.catalogue.mapping[self.catalogue.tree.query(
                box(west-dx+shift,max(-90,south-pad),east+dx+shift,min(90,north+pad)))])
        for i in np.unique(candidates).astype(int):
            lat=float(self.catalogue.lat[i])
            lon=west+((float(self.catalogue.lon[i])-west+180)%360-180)
            radius=float(self.catalogue.diameter[i])*500
            inner=max(0.,radius-self.half_width_m);outer=radius+self.half_width_m
            dy=math.degrees(outer/RADIUS)
            dx=min(180,math.degrees(math.asin(min(1.,math.sin(outer/RADIUS)/
                max(1e-12,math.cos(math.radians(lat)))))))
            if abs(lat)+dy>=90:dx=180
            ra=max(0,int(math.floor((90-lat-dy)*self.ppd))-r0)
            rb=min(mask.shape[0],int(math.ceil((90-lat+dy)*self.ppd))-r0)
            ca=max(0,int(math.floor((lon-dx-west)*self.ppd)))
            cb=min(mask.shape[1],int(math.ceil((lon+dx-west)*self.ppd)))
            if rb<=ra or cb<=ca:continue
            lats=np.radians(90-(np.arange(r0+ra,r0+rb)+.5)/self.ppd)[:,None]
            lons=np.radians(west+(np.arange(ca,cb)+.5)/self.ppd)[None,:]
            phi=math.radians(lat);lam=math.radians(lon)
            dot=np.sin(lats)*math.sin(phi)+np.cos(lats)*math.cos(phi)*np.cos(lons-lam)
            mask[ra:rb,ca:cb]|=(dot>=math.cos(outer/RADIUS)-1e-14)&(dot<=math.cos(inner/RADIUS)+1e-14)
        return mask

    @lru_cache(maxsize=128)
    def block(self,br,bc):
        size=self.block_size
        return self.window(br*size,(br+1)*size,bc*size,(bc+1)*size)

    def blocked(self,cell):
        r,c=cell;size=self.block_size
        return bool(self.block(r//size,c//size)[r%size,c%size])

    def component(self,point):
        return frozenset(h["id"] for h in self.catalogue.containing(point))

    def crossings(self,a,b):
        return self.catalogue.intersections(a,b,rim_only=True)

    def policy(self):
        return {"enabled":True,"mode":"unresolved_catalogue_rim_guard",
            "records":len(self.catalogue.lon),"rim_half_width_m":self.half_width_m,
            "source":self.catalogue.metadata.get("source","https://craters.sjrdesign.net/"),
            "rule":"Crater floors are allowed. Catalogue rim bands are guarded in MOLA; crossing requires finer numerical terrain.",
            "limitations":"Conservative circle-fit boundary, not a measured impassable wall or a safety certification."}
