"""Real 128 ppd endpoint terrain checks, not slopes inferred from photographs."""
from collections import deque
from functools import lru_cache
import hashlib
from heapq import heappop,heappush
import json
import math
from time import monotonic

import numpy as np

from . import plan_route
from .global_routing import distance,RADIUS,STEPS
from .pathfinding import RouteGraph
from .terrain import ROOT
from .assessment import traversability_assessment


class FineMolaPatch:
    def __init__(self,elevation,counts,metadata):
        self.elevation=np.asarray(elevation);self.counts=np.asarray(counts)
        self.metadata=metadata;self.shape=self.elevation.shape
        self.west,self.south,self.east,self.north=metadata["bounds"]
        self.ppd=metadata["ppd"]
        self.step_m=RADIUS*math.pi/(180*self.ppd)
        self._lats=self.north-(np.arange(self.shape[0])+.5)/self.ppd
        self._h=self.step_m*np.cos(np.radians(self._lats))
        dy,dx=np.gradient(self.elevation)
        self.slope=np.degrees(np.arctan(np.hypot(dy/self.step_m,dx/self._h[:,None])))
        self.valid=np.isfinite(self.elevation)&np.isfinite(self.slope)

    @classmethod
    def load_all(cls,root=ROOT):
        folder=root/"data/processed/mola128";patches=[]
        for path in sorted(folder.glob("*.json")):
            metadata=json.loads(path.read_text(encoding="utf-8"))
            archive=path.with_suffix(".npz")
            if hashlib.sha256(archive.read_bytes()).hexdigest()!=metadata["runtime_sha256"]:
                raise ValueError("Fine MOLA checksum mismatch")
            with np.load(archive,allow_pickle=False) as data:
                patches.append(cls(data["elevation"],data["counts"],metadata))
        return patches

    def contains(self,p):
        return self.west<=p[0]<self.east and self.south<p[1]<=self.north

    def pixel_to_lonlat(self,row,col):
        return self.west+(col+.5)/self.ppd,self.north-(row+.5)/self.ppd

    def lonlat_to_pixel(self,lon,lat):
        if not self.contains((lon,lat)):raise ValueError("Outside fine MOLA patch")
        return min(self.shape[0]-1,int((self.north-lat)*self.ppd)),int((lon-self.west)*self.ppd)

    def distance_m(self,a,b):
        return distance(self.pixel_to_lonlat(*a),self.pixel_to_lonlat(*b))

    def sample(self,p):
        cell=self.lonlat_to_pixel(*p)
        return {"dataset":"mola128","spacing_m":self.step_m,"valid":True,
                "elevation_m":float(self.elevation[cell]),"slope_deg":float(self.slope[cell]),
                "interpolated":bool(self.counts[cell]==0),"observations":int(self.counts[cell])}

    def details(self,grade):
        return {"id":self.metadata["id"],"bounds":self.metadata["bounds"],
                "spacing_m":self.step_m,"max_grade_deg":grade,"source":self.metadata["source"],
                "overlay_url":f"/api/hazards/mola128/{self.metadata['id']}/slopes?max_grade_deg={grade}",
                "interpolated_fraction":float((self.counts==0).mean()),
                "notice":"Measured MOLA elevation bins with official interpolation; red mask is slope in the 463 m DEM, not a boulder/soil map."}

    def exit_check(self,point,grade,budget_s=4):
        cell=self.lonlat_to_pixel(*point)
        result=self._exit_check(cell,float(grade),budget_s)
        return {**result,"terrain_check":self.details(grade),"sample":self.sample(point)}

    @lru_cache(maxsize=64)
    def _exit_check(self,start,grade,budget_s):
        graph=RouteGraph(self.elevation,self.slope,self.valid,self,max_slope_deg=grade,slope_weight=0)
        if not graph.open[start]:
            return {"status":"blocked_endpoint","reason":"fine_dem_slope","expanded_cells":0}
        rows,cols=self.shape
        minimum_h=float(self._h.min())
        def heuristic(cell):
            r,c=cell
            return min(min(r,rows-1-r)*self.step_m,min(c,cols-1-c)*minimum_h)
        queue=[(heuristic(start),0.,start)];best={start:0.}
        deadline=monotonic()+budget_s;expanded=0
        while queue:
            _,cost,cell=heappop(queue)
            if cost!=best[cell]:continue
            if expanded%128==0 and monotonic()>=deadline:
                return {"status":"search_limit","reason":"fine_exit_budget","expanded_cells":expanded}
            r,c=cell
            if r in (0,rows-1) or c in (0,cols-1):
                return {"status":"ok","expanded_cells":expanded,"exit":self.pixel_to_lonlat(r,c)}
            expanded+=1
            for dr,dc in STEPS:
                other=(r+dr,c+dc)
                if not graph.contains(other):continue
                edge=graph.edge_cost(cell,other)
                if edge is None:continue
                candidate=cost+edge
                if candidate<best.get(other,math.inf):
                    best[other]=candidate;heappush(queue,(candidate+heuristic(other),candidate,other))
        return {"status":"no_route","reason":"local_exit_blocked","expanded_cells":expanded}

    @lru_cache(maxsize=4)
    def hazard_valid(self,catalogue):
        from shapely import box
        indices=np.unique(catalogue.mapping[catalogue.tree.query(
            box(self.west-.02,self.south-.02,self.east+.02,self.north+.02))])
        valid=self.valid.copy()
        extra=self.step_m/math.sqrt(2)
        for i in indices:
            radius=catalogue.radii[i]+extra
            delta=math.degrees(radius/RADIUS)
            dx=delta/max(.01,math.cos(math.radians(catalogue.lat[i])))
            r0=max(0,int((self.north-catalogue.lat[i]-delta)*self.ppd))
            r1=min(self.shape[0],int((self.north-catalogue.lat[i]+delta)*self.ppd)+2)
            c0=max(0,int((catalogue.lon[i]-dx-self.west)*self.ppd))
            c1=min(self.shape[1],int((catalogue.lon[i]+dx-self.west)*self.ppd)+2)
            if r1<=r0 or c1<=c0:continue
            lats=np.radians(self.north-(np.arange(r0,r1)+.5)/self.ppd)[:,None]
            lons=np.radians(self.west+(np.arange(c0,c1)+.5)/self.ppd)[None,:]
            clat=math.radians(catalogue.lat[i]);clon=math.radians(catalogue.lon[i])
            dot=np.sin(lats)*math.sin(clat)+np.cos(lats)*math.cos(clat)*np.cos(lons-clon)
            valid[r0:r1,c0:c1]&=dot<math.cos(radius/RADIUS)
        return valid

    def route(self,a,b,grade,weight,budget_s=5,catalogue=None):
        valid=self.valid if catalogue is None else self.hazard_valid(catalogue)
        return plan_route(self.elevation,self.slope,valid,self,a,b,max_slope_deg=grade,
                          slope_weight=weight,max_expansions=300000,time_budget_s=budget_s)

    def local_result(self,a,b,grade,weight,catalogue=None,budget_s=8):
        result=self.route(a,b,grade,weight,budget_s,catalogue)
        check={**self.details(grade),"status":result["status"]}
        if result["status"]!="ok":
            return {**result,"terrain_checks":[check],"dataset":"mola128",
                    "message":"За детальною MOLA 463 м цей шлях не проходить обрані обмеження схилів або кратерів."}
        m=result["metrics"];profile=[]
        for p in m["elevation_profile"]:
            # Profile stores distances/elevations, so use the actual route cells.
            profile.append({**p})
        geometry=result["route"]["geometry"]
        coords=geometry["coordinates"] if geometry["type"]=="LineString" else [geometry["coordinates"]]
        for p,c in zip(profile,coords):
            p.update(interpolated=bool(self.counts[self.lonlat_to_pixel(*c)]==0),dataset="mola128")
        if catalogue and any(catalogue.intersections(x,y) for x,y in zip(coords,coords[1:])):
            return {"status":"no_route","reason":"crater_intersection","expanded_cells":result["expanded_cells"],
                    "terrain_checks":[check],"message":"Детальний шлях перетинає каталожний контур; варіант відхилено."}
        assessment=traversability_assessment(self.step_m,global_model=False)
        policy=catalogue.policy() if catalogue else {"enabled":False}
        properties={"coordinate_system":"Mars planetocentric, NOT WGS84","traversability":assessment,
                    "hazard_policy":policy,"fine_terrain_checks":[check],"slope_weight":weight}
        return {**result,"dataset":"mola128","approximate":False,"traversability":assessment,
                "hazard_policy":policy,"terrain_checks":[check],"profile":profile,
                "route":{**result["route"],"properties":properties},
                "metrics":{**m,"max_grade_deg":m["max_segment_grade_deg"],"direct_distance_m":distance(a,b),
                           "cells":len(profile),"interpolated_cells":sum(p["interpolated"] for p in profile),
                           "snap_offsets_m":[distance(a,coords[0]),distance(b,coords[-1])],
                           "terrain_distance_m":sum(math.hypot(y["distance_m"]-x["distance_m"],y["elevation_m"]-x["elevation_m"])
                                                    for x,y in zip(profile,profile[1:]))}}


def refine_global_result(result,start,end,patches,grade,weight,catalogue=None):
    """Replace covered global path sections using the actual 128 ppd grid."""
    if result["status"]!="ok":return result
    geometry=result["route"]["geometry"]
    coordinates=geometry["coordinates"] if geometry["type"]=="LineString" else [geometry["coordinates"]]
    entries=[(list(c),float(p["elevation_m"]),bool(p["interpolated"]),"mola16")
             for c,p in zip(coordinates,result["profile"])]
    checks=[];expanded=result.get("expanded_cells",0)
    for patch in patches:
        inside=[patch.contains(e[0]) for e in entries]
        groups=[];i=0
        while i<len(entries):
            if not inside[i]:i+=1;continue
            first=i
            while i+1<len(entries) and inside[i+1]:i+=1
            groups.append((first,i));i+=1
        for first,last in reversed(groups):
            a=start if first==0 and patch.contains(start) else entries[first][0]
            b=end if last==len(entries)-1 and patch.contains(end) else entries[last][0]
            local=patch.route(a,b,grade,weight,budget_s=8,catalogue=catalogue)
            expanded+=local.get("expanded_cells",0)
            check={**patch.details(grade),"status":local["status"]}
            checks.append(check)
            if local["status"]!="ok":
                return {"status":local["status"],"reason":"fine_terrain_blocked","dataset":"mola128",
                        "expanded_cells":expanded,"terrain_checks":checks,"hazard_policy":result.get("hazard_policy"),
                        "message":"Детальніша MOLA 463 м не підтвердила цей перехід за обраним ухилом і контурами кратерів. "
                                  "Шлях через борт не малюється. Червоний шар показує схили, що перевищують поріг."}
            g=local["route"]["geometry"]
            line=g["coordinates"] if g["type"]=="LineString" else [g["coordinates"]]
            profile=local["metrics"]["elevation_profile"]
            replacement=[]
            for c,p in zip(line,profile):
                cell=patch.lonlat_to_pixel(*c)
                replacement.append((list(c),float(p["elevation_m"]),bool(patch.counts[cell]==0),"mola128"))
            entries[first:last+1]=replacement
    if not checks:return result
    coords=[e[0] for e in entries]
    heights=np.array([e[1] for e in entries])
    lengths=[distance(a,b) for a,b in zip(coords,coords[1:])]
    cumulative=np.r_[0.,np.cumsum(lengths)]
    changes=np.diff(heights)
    grades=[math.degrees(math.atan2(abs(h),d)) for h,d in zip(changes,lengths)]
    if any(g>grade+1e-8 and a[3]!=b[3] for g,a,b in zip(grades,entries,entries[1:])):
        return {"status":"no_route","reason":"resolution_transition_unverified","expanded_cells":expanded,
                "terrain_checks":checks,"message":"Стик глобальної та детальної сіток перевищує обраний градієнт; цей варіант відхилено."}
    # Refinement must not introduce a catalogue crossing in a stitching edge.
    if catalogue is not None:
        for a,b in zip(coords,coords[1:]):
            if catalogue.intersections(a,b):
                return {"status":"no_route","reason":"crater_stitch_intersection","expanded_cells":expanded,
                        "terrain_checks":checks,"message":"Перехід між сітками перетинає каталожний контур кратера; цей варіант відхилено."}
    properties={**result["route"]["properties"],"fine_terrain_checks":checks,
                "resolution_note":"MOLA 16 ppd globally, true MOLA 128 ppd in the listed patches; same MEGDR areoid, mixed spatial resolution."}
    assessment={**result["traversability"]}
    assessment["terrain_constraints_checked"]=[*assessment["terrain_constraints_checked"],"mola128_surface_slope_in_prepared_patches"]
    assessment["message"]="Каталожні кратери обійдено; у підготовлених областях шлях переплановано за MOLA 463 м з перевіркою схилів. Решта шляху — MOLA 3,7 км. Дрібні уступи, каміння і ґрунт залишаються неперевіреними."
    properties["traversability"]=assessment
    metrics={**result["metrics"],"distance_m":float(cumulative[-1]),
             "terrain_distance_m":sum(math.hypot(d,h) for d,h in zip(lengths,changes)),
             "ascent_m":float(changes[changes>0].sum()),"descent_m":float(-changes[changes<0].sum()),
             "min_elevation_m":float(heights.min()),"max_elevation_m":float(heights.max()),
             "max_grade_deg":max(grades,default=0),"cells":len(entries),
             "interpolated_cells":sum(e[2] for e in entries),
             "snap_offsets_m":[distance(start,coords[0]),distance(end,coords[-1])]}
    return {**result,"route":{"type":"Feature","geometry":{"type":"LineString" if len(coords)>1 else "Point",
             "coordinates":coords if len(coords)>1 else coords[0]},"properties":properties},
            "metrics":metrics,"traversability":assessment,"terrain_checks":checks,"expanded_cells":expanded,
            "profile":[{"distance_m":float(d),"elevation_m":e[1],"interpolated":e[2],"dataset":e[3]}
                       for d,e in zip(cumulative,entries)]}
