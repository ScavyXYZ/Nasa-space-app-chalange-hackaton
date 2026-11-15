"""Planet-wide native MOLA graph: floors allowed, steep rims are not.

Catalogue rims are guarded, but their floors are not solid-disc obstacles. Numerical terrain is
checked on EVERY native edge, not only in endpoint-specific prepared patches.
Tiles are memory-mapped; slope blocks have a bounded cache and a one-cell halo.
"""
from functools import lru_cache
import json
import math
from time import monotonic

import numpy as np

from .assessment import traversability_assessment
from .bidirectional import bidirectional_search
from .global_routing import RADIUS,STEPS,distance
from .terrain import ROOT,TerrainError
from .rim_guard import CatalogueRimGuard

PPD=128
ROWS,COLS=180*PPD,360*PPD
TILE_ROWS,TILE_COLS=44*PPD,90*PPD
BANDS=("88n","44n","00n","44s")
STEP_M=2*math.pi*RADIUS/(360*PPD)


def terrain_slopes(heights,latitudes,ppd=PPD):
    """Surface gradient plus one-sided grades: a thin ridge cannot cancel out."""
    dy=2*math.pi*RADIUS/(360*ppd)
    dx=dy*np.cos(np.radians(latitudes))
    gy,gx=np.gradient(heights.astype(np.float64))
    gradient=np.hypot(gy/dy,gx/dx[:,None])
    # A central derivative alone is zero on a one-bin summit/valley.
    # Retain the worst measured neighbouring transition as well.
    for dr,dc in STEPS:
        a=(slice(max(0,-dr),heights.shape[0]-max(0,dr)),
           slice(max(0,-dc),heights.shape[1]-max(0,dc)))
        b=(slice(max(0,dr),heights.shape[0]-max(0,-dr)),
           slice(max(0,dc),heights.shape[1]-max(0,-dc)))
        run=np.hypot(dy*dr,dx[a[0]]*dc)[:,None]
        transition=np.abs(heights[b]-heights[a])/run
        gradient[a]=np.maximum(gradient[a],transition)
    return np.degrees(np.arctan(gradient)).astype(np.float32)


class Mola128Store:
    rows,cols,ppd=ROWS,COLS,PPD
    step_m=STEP_M
    block_size=256

    def __init__(self,root=ROOT):
        self.folder=root/"data/processed/mola128_global"

    @lru_cache(maxsize=32)
    def _tile(self,band,west,kind):
        product=f"meg{kind}{band}{west:03}hb"
        path=self.folder/(product+".img")
        try:
            meta=json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            dtype=">i2" if kind=="t" else "u1"
            size=TILE_ROWS*TILE_COLS*(2 if kind=="t" else 1)
            if path.stat().st_size!=size or meta["bytes"]!=size or meta["dtype"]!=dtype:
                raise ValueError("Invalid MOLA tile layout")
            return np.memmap(path,dtype=dtype,mode="r",shape=(TILE_ROWS,TILE_COLS))
        except (OSError,ValueError,KeyError) as exc:
            raise TerrainError("terrain_data_unavailable",
                "Числова MOLA 463 м для цієї ділянки ще не готова. "
                "Маршрут через неперевірений рельєф не підставляється.",503) from exc

    def window(self,r0,r1,c0,c1):
        heights=np.full((r1-r0,c1-c0),np.nan,dtype=np.float32)
        counts=np.zeros(heights.shape,dtype=np.uint8)
        # Absolute row 256 is 88°N. The polar caps are genuinely uncovered.
        for band_index,band in enumerate(BANDS):
            top=2*PPD+band_index*TILE_ROWS
            ra,rb=max(r0,top),min(r1,top+TILE_ROWS)
            if rb<=ra:continue
            first=c0
            while first<c1:
                col=first%COLS;west=col//TILE_COLS*90
                last=min(c1,first+TILE_COLS-col%TILE_COLS)
                target=(slice(ra-r0,rb-r0),slice(first-c0,last-c0))
                source=(slice(ra-top,rb-top),slice(col%TILE_COLS,col%TILE_COLS+last-first))
                heights[target]=self._tile(band,west,"t")[source]
                counts[target]=self._tile(band,west,"c")[source]
                first=last
        if np.any(np.isfinite(heights)&((heights< -9000)|(heights>22000))):
            raise TerrainError("terrain_data_invalid","Некоректні числові висоти MOLA.",503)
        return heights,counts

    @lru_cache(maxsize=128)
    def block(self,br,bc):
        size=self.block_size;r0,c0=br*size,bc*size
        h,counts=self.window(r0-1,r0+size+1,c0-1,c0+size+1)
        lats=90-(np.arange(r0-1,r0+size+1)+.5)/PPD
        slope=terrain_slopes(h,lats)
        return h[1:-1,1:-1],slope[1:-1,1:-1],counts[1:-1,1:-1]

    def values(self,cell):
        r,c=cell
        h,s,n=self.block(r//self.block_size,c//self.block_size)
        local=(r%self.block_size,c%self.block_size)
        return float(h[local]),float(s[local]),int(n[local])

    def coordinate(self,cell):
        r,c=cell
        return ((c+.5)/PPD+180)%360-180,90-(r+.5)/PPD

    def index(self,point):
        lon,lat=point
        if not math.isfinite(lon) or not math.isfinite(lat) or abs(lon)>180 or abs(lat)>90:
            raise TerrainError("invalid_coordinate","Очікуються координати Марса.")
        return min(ROWS-1,int((90-lat)*PPD)),int((lon%360)*PPD)%COLS

    def covered(self,cell):
        return 2*PPD<=cell[0]<ROWS-2*PPD

    def sample(self,point):
        cell=self.index(point)
        if not self.covered(cell):
            raise TerrainError("outside_coverage","MOLA 128 ppd не покриває полярні шапки вище 88°.",422)
        height,slope,count=self.values(cell)
        return {"dataset":"mola128","spacing_m":STEP_M,"valid":math.isfinite(slope),
                "elevation_m":height,"slope_deg":slope,"observations":count,
                "interpolated":count==0,"cell_center":self.coordinate(cell)}


class NativeMolaPlanner:
    """Coarse guidance is a search bound only; output consists solely of fine cells."""
    def __init__(self,store,guide,catalogue=None,*,rim_guard=None):
        self.store,self.guide,self.catalogue=store,guide,catalogue
        self.rims=rim_guard or (CatalogueRimGuard(catalogue,store.ppd) if catalogue is not None else None)

    def route(self,start,end,grade=15,weight=5,budget_s=60):
        if not math.isfinite(grade) or not 0<=grade<=90 or not math.isfinite(weight) or not 0<=weight<=100:
            raise TerrainError("invalid_parameters","Некоректні обмеження ухилу.")
        if self.rims is None:
            raise TerrainError("craters_unavailable","Каталог бортів недоступний; неперевірений маршрут не будується.",503)
        result=self._route(start,end,grade,weight,budget_s)
        result["terrain_validation"]={"spacing_m":STEP_M,"max_grade_deg":grade,
            "entire_route":result["status"]=="ok","catalogue_circles_blocked":False,
            "polar_coverage_latitude":[-88,88],"catalogue_rim_guard":True,"model":"mola128-rim-guard-v1"}
        result["hazard_policy"]=self.rims.policy()
        return result

    def _route(self,start,end,grade,weight,budget_s):
        began=monotonic();deadline=began+budget_s
        store=self.store;a,b=store.index(start),store.index(end)
        for endpoint,cell in [("start",a),("end",b)]:
            if not store.covered(cell):
                return {"status":"outside_grid","reason":"fine_dem_polar_gap","expanded_cells":0,
                        "message":"Числова MOLA 463 м тут не має покриття; грубий маршрут замість неї не будується."}
            height,slope,_=store.values(cell)
            if not math.isfinite(slope) or slope>grade:
                return {"status":"blocked_endpoint","reason":"native_surface_slope","endpoint":endpoint,
                        "expanded_cells":0,"dataset":"mola128",
                        "message":f"Точка лежить на схилі {slope:.1f}° у числовій DEM; поріг — {grade}°. "
                                  "Саме перебування всередині кратера не є забороною."}
            point=start if endpoint=="start" else end
            if self.rims.blocked(cell) or self.rims.crossings(point,store.coordinate(cell)):
                return {"status":"blocked_endpoint","reason":"unresolved_catalogue_rim","endpoint":endpoint,
                    "expanded_cells":0,"dataset":"mola128",
                    "message":"Точка або її прив’язка до DEM потрапляє на нерозрізнений каталожний борт. "
                              "Потрібна детальніша числова DEM; однакові висоти не доводять наявність проїзду."}
        component=self.rims.component(start)
        if component!=self.rims.component(end):
            return {"status":"no_route","reason":"crater_exit_needs_finer_dem","expanded_cells":0,"dataset":"mola128",
                "message":"Точки лежать по різні боки каталожного борту. MOLA 463 м не підтверджує проїзд через нього. "
                          "Рух по дну дозволений, але для входу/виїзду потрібна детальніша числова DEM."}
        # The coarse grid guides search only. Guarded rims cannot disappear
        # because their MOLA endpoint heights happen to be identical.
        avoid_guide=not component and getattr(self.guide,"hazards",None) is not None
        guidance=self.guide.route(start,end,grade,weight,
            time_budget_s=min(40 if avoid_guide else 12,max(.01,deadline-monotonic())),
            avoid_craters=avoid_guide)
        # A coarse endpoint can snap into a crater even when the selected point
        # and native cell are outside. Coarse guidance may not veto that point.
        if avoid_guide and guidance["status"]=="blocked_endpoint":
            guidance=self.guide.route(start,end,grade,weight,
                time_budget_s=min(12,max(.01,deadline-monotonic())),avoid_craters=False)
        if guidance["status"]!="ok":
            return {**guidance,"message":"Не знайдено коридор у межах бюджету пошуку. Неперевірений відрізок не малюється."}
        geometry=guidance["route"]["geometry"]
        points=geometry["coordinates"] if geometry["type"]=="LineString" else [geometry["coordinates"]]
        guide_cells=[self.guide.index(p) for p in points]
        ratio=round(self.guide.step*PPD)
        if ratio<1 or abs(ratio-self.guide.step*PPD)>1e-8:
            raise ValueError("Guidance/native grids must align")
        expanded=guidance.get("expanded_cells",0)
        lengths={}
        def length(x,y):
            dr=y[0]-x[0];dc=abs(y[1]-x[1]);dc=min(dc,COLS-dc)
            key=(min(x[0],y[0]),abs(dr),dc)
            if key not in lengths:lengths[key]=distance(store.coordinate(x),store.coordinate(y))
            return lengths[key]
        def opened(cell):
            if not store.covered(cell) or self.rims.blocked(cell):return False
            _,slope,_=store.values(cell)
            return math.isfinite(slope) and slope<=grade
        def cost(x,y):
            hx,sx,nx=store.values(x);hy,sy,ny=store.values(y)
            run=length(x,y);rise=abs(hy-hx)
            transition=math.degrees(math.atan2(rise,run))
            if transition>grade or max(sx,sy)>grade:return None
            if x[0]!=y[0] and x[1]!=y[1]:
                if not opened((x[0],y[1])) or not opened((y[0],x[1])):return None
            local=max(transition,sx,sy)
            return math.hypot(run,rise)*(1+weight*(local/45)**2+.25*((nx==0)+(ny==0))/2)
        metric=lambda x,y:distance(store.coordinate(x),store.coordinate(y))
        # Long searches use measured, open intermediate cells near the coarse
        # guide. This bounds search work, not terrain checks: segments share
        # exactly the same native endpoint and every returned edge is tested.
        # No straight-line joins, mixed-resolution links, or skipped samples.
        waypoints=[a];travelled=0.
        for i,p in enumerate(points[1:-1],1):
            travelled+=distance(points[i-1],p)
            if travelled<100_000:continue
            cell=store.index(p);candidate=None
            for radius in (0,1,2,4,8,16):
                choices=[]
                for dr in range(-radius,radius+1):
                    for dc in range(-radius,radius+1):
                        if radius and max(abs(dr),abs(dc))!=radius:continue
                        nearby=(cell[0]+dr,(cell[1]+dc)%COLS)
                        if opened(nearby) and self.rims.component(store.coordinate(nearby))==component:
                            choices.append(nearby)
                if choices:
                    candidate=min(choices,key=lambda x:metric(x,cell));break
            if candidate is not None and candidate!=waypoints[-1] and metric(candidate,b)>25_000:
                waypoints.append(candidate);travelled=0.
        if waypoints[-1]!=b:waypoints.append(b)
        path=[a] if len(waypoints)==1 else []
        limited=False;attempted=[];corridors={}
        for source,target in zip(waypoints,waypoints[1:]):
            segment=[]
            for width in (2,6,16):
                if monotonic()>=deadline:limited=True;break
                if width not in corridors:
                    corridors[width]=self.guide._corridor(
                        guide_cells+[self.guide.index(start),self.guide.index(end)],width)
                allowed=corridors[width]
                def neighbours(cell):
                    r,c=cell
                    for dr,dc in STEPS:
                        other=(r+dr,(c+dc)%COLS)
                        if store.covered(other) and allowed[other[0]//ratio,other[1]//ratio] and opened(other):
                            yield other
                segment,count,limited=bidirectional_search(source,target,neighbours,cost,metric,
                    deadline=deadline,max_expansions=1_000_000)
                expanded+=count
                if width not in attempted:attempted.append(width)
                if segment or limited:break
            if not segment:
                path=[];break
            path.extend(segment[1:] if path else segment)
        if not path:
            return {"status":"search_limit" if limited else "no_route","reason":"native_terrain_search",
                    "dataset":"mola128","expanded_cells":expanded,
                    "message":"За числовою MOLA 463 м не знайдено допустимого шляху в перевірених коридорах. "
                              "Круті борти не замінюються прямими лініями; це не доказ відсутності всіх можливих об’їздів."}
        widths=[w*self.guide.step*math.pi/180*RADIUS for w in attempted]
        result=self.result(path,start,end,grade,weight,expanded,began,widths)
        if result["status"]=="ok":
            result["route"]["properties"]["native_search_segments"]=max(1,len(waypoints)-1)
        return result

    def result(self,path,start,end,grade,weight,expanded,began,widths):
        store=self.store
        coords=[store.coordinate(cell) for cell in path]
        values=[store.values(cell) for cell in path]
        heights=np.array([v[0] for v in values])
        lengths=[distance(x,y) for x,y in zip(coords,coords[1:])]
        changes=np.diff(heights);cumulative=np.r_[0.,np.cumsum(lengths)]
        max_transition=max((math.degrees(math.atan2(abs(dh),run)) for dh,run in zip(changes,lengths)),default=0.)
        max_surface=max(v[1] for v in values)
        if max_surface>grade or max_transition>grade:
            raise RuntimeError("Native terrain route validation failed")
        if any(self.rims.crossings(x,y) for x,y in zip(coords,coords[1:])):
            return {"status":"no_route","reason":"rim_validation_failed","dataset":"mola128",
                "expanded_cells":expanded,
                "message":"Фінальна перевірка виявила перетин нерозрізненого борту; цей шлях відхилено."}
        assessment=traversability_assessment(STEP_M,global_model=False)
        assessment["terrain_constraints_checked"]=["native_surface_slope","one_sided_neighbour_grades",
            "every_native_transition","diagonal_corner_clearance","unresolved_catalogue_rim_guard"]
        assessment["missing_evidence"]=["subgrid_crater_rims_and_cliffs","boulders","soil_traction"]
        assessment["message"]="Увесь шлях розрахований на числовій MOLA 463 м: перевірені схили та кожен перехід. "
        assessment["message"]+="Дно кратера дозволене; нерозрізнені каталожні борти обійдені, а не оголошені пологими. "
        assessment["message"]+="Уступи дрібніші за DEM, каміння та зчеплення ґрунту не перевірені."
        policy=self.rims.policy()
        properties={"coordinate_system":"Mars planetocentric, NOT WGS84","resolution_deg":1/PPD,
            "source":"https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
            "vertical_datum":"MOLA GMM3 areoid, MEGDR v2","traversability":assessment,"hazard_policy":policy,
            "slope_weight":weight,"max_grade_deg":grade,"native_terrain_entire_route":True,"approximate":True,
            "corridor_widths_m":widths}
        return {"status":"ok","dataset":"mola128","approximate":True,
            "algorithm":"Balanced bidirectional native 128 ppd search in widening coarse-guided corridors",
            "expanded_cells":expanded,"elapsed_ms":round((monotonic()-began)*1000),
            "traversability":assessment,"hazard_policy":policy,
            "route":{"type":"Feature","geometry":{"type":"LineString" if len(coords)>1 else "Point",
                "coordinates":coords if len(coords)>1 else coords[0]},"properties":properties},
            "metrics":{"distance_m":float(cumulative[-1]),"direct_distance_m":distance(start,end),
                "terrain_distance_m":sum(math.hypot(run,dh) for run,dh in zip(lengths,changes)),
                "min_elevation_m":float(heights.min()),"max_elevation_m":float(heights.max()),
                "ascent_m":float(changes[changes>0].sum()),"descent_m":float(-changes[changes<0].sum()),
                "max_grade_deg":max_transition,"max_surface_slope_deg":max_surface,"cells":len(path),
                "interpolated_cells":sum(v[2]==0 for v in values),
                "snap_offsets_m":[distance(start,coords[0]),distance(end,coords[-1])]},
            "profile":[{"distance_m":float(d),"elevation_m":v[0],"slope_deg":v[1],
                "interpolated":v[2]==0,"dataset":"mola128"} for d,v in zip(cumulative,values)],
            "warnings":["All route cells use native 128 ppd MOLA, including official interpolation.",
                        "Known catalogue rim bands are guarded; crossing requires finer numerical terrain.",
                        "463 m spacing is not rover-scale accuracy. Physical traversability is unverified.",
                        "Corridor guidance is approximate; failure is not a proof that no other path exists.",
                        "Endpoint-to-cell offsets are excluded from route length."]}
