"""Run: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000."""
import json
import os
import io
import math
from functools import lru_cache
from urllib.request import urlopen
from urllib.error import URLError
from urllib.parse import urlparse
from time import monotonic
from contextlib import asynccontextmanager
from threading import Lock, BoundedSemaphore
from pathlib import Path
import hashlib
import tempfile
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from algorithms import plan_route
from algorithms.grid import MarsRasterGeometry
from algorithms.metrics import analyze_route
from algorithms.terrain import DATASETS, ROOT, TerrainError, TerrainGrid
from algorithms.science import nearby_regions
from algorithms.mesh import terrain_mesh
from algorithms.global_routing import GlobalTerrain
from algorithms.assessment import traversability_assessment
from algorithms.imagery_validation import valid_tile
from algorithms.fine_mola import FineMolaPatch
from algorithms.mola128 import Mola128Store,NativeMolaPlanner,terrain_slopes
from algorithms.rim_guard import CatalogueRimGuard
from algorithms.atlas import Geology, expedition

Dataset = Literal["ctx", "hirise", "regional"]


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    dataset: Dataset = "ctx"
    coordinates: list[tuple[float,float]] = Field(min_length=2, max_length=1000)
    sample_step_m: float | None = Field(default=None, gt=0)
    max_slope_deg: float = Field(default=15, ge=0, le=90)


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class GlobalRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start: Position
    end: Position
    max_grade_deg: float = Field(default=15, ge=0, le=90)
    slope_weight: float = Field(default=5, ge=0, le=100)
    stops: list[Position] = Field(default_factory=list, max_length=4)
    avoid_craters: bool = True


class ExpeditionRequest(GlobalRouteRequest):
    resolution: Literal["auto","mola","regional","hirise"] = "auto"


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    dataset: Dataset = "ctx"
    start: Position
    end: Position
    max_slope_deg: float = Field(default=15, ge=0, le=90)
    slope_weight: float = Field(default=1, ge=0, le=100)
    mode: Literal["astar", "hierarchical"] = "astar"
    nearby_radius_m: float = Field(default=200,ge=0,le=1000)


def create_app(root=ROOT):
    root = Path(root)
    loaded = {}
    load_lock = Lock()
    global_loaded = {}
    global_slots = BoundedSemaphore(2)
    local_slots = BoundedSemaphore(2)
    tile_slots = BoundedSemaphore(8)
    tile_cache_lock=Lock()
    cache_base=(Path(os.environ["LOCALAPPDATA"])/"Temp/opencode" if os.environ.get("LOCALAPPDATA")
                else Path(tempfile.gettempdir()))
    tile_cache=cache_base/"mars-explorer-tiles"
    # Bounded disk cache; no workspace or scientific-source files are removed.
    def cached_tile(key,size,layer):
        path=tile_cache/(hashlib.sha256(key.encode()).hexdigest()+".tile")
        try:
            data=path.read_bytes()
            if not valid_tile(data,size,layer):
                # Only this application's corrupt temporary cache entry.
                path.unlink(missing_ok=True)
                return None
            os.utime(path,None)
            return data
        except OSError:
            return None
    def store_tile(key,content):
        try:
            with tile_cache_lock:
                tile_cache.mkdir(parents=True,exist_ok=True)
                files=list(tile_cache.glob("*.tile"))
                size=sum(p.stat().st_size for p in files)
                if size+len(content)>192_000_000:
                    for path in sorted(files,key=lambda p:p.stat().st_mtime):
                        size-=path.stat().st_size;path.unlink()
                        if size+len(content)<160_000_000:
                            break
                target=tile_cache/(hashlib.sha256(key.encode()).hexdigest()+".tile")
                pending=target.with_suffix(".part")
                pending.write_bytes(content);pending.replace(target)
        except OSError:
            pass  # A read-only/full cache must never prevent viewing.

    def geology_index():
        with load_lock:
            if "geology" not in global_loaded:
                global_loaded["geology"] = Geology(root)
            return global_loaded["geology"]

    def global_grid():
        with load_lock:
            if "terrain" not in global_loaded:
                global_loaded["terrain"] = GlobalTerrain.load(root)
            return global_loaded["terrain"]

    def fine_patches():
        with load_lock:
            if "fine_mola" not in global_loaded:
                global_loaded["fine_mola"]=FineMolaPatch.load_all(root)
            return global_loaded["fine_mola"]

    def native_mola():
        with load_lock:
            if "native_mola" not in global_loaded:
                global_loaded["native_mola"]=Mola128Store(root)
            return global_loaded["native_mola"]

    def native_rims():
        catalogue=global_grid().hazards
        if catalogue is None:
            raise TerrainError("craters_unavailable","Каталог бортів недоступний; перевірка неповна.",503)
        with load_lock:
            if "native_rims" not in global_loaded:
                global_loaded["native_rims"]=CatalogueRimGuard(catalogue)
            return global_loaded["native_rims"]

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            for terrain in loaded.values():
                terrain.close()
            loaded.clear()

    app = FastAPI(title="MARS EXPLORER — GIS Terrain API", version="1.0.0",
                  description="Mars terrain sampling, route analysis and A* route planning.",
                   lifespan=lifespan)
    app.add_middleware(GZipMiddleware,minimum_size=1000,compresslevel=5)
    origins = ["http://localhost:5173","http://127.0.0.1:5173"]
    origins.extend(x.strip() for x in os.environ.get("CORS_ORIGINS","").split(",") if x.strip())
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["GET","POST"], allow_headers=["Content-Type"])

    def grid(dataset):
        with load_lock:
            if dataset not in loaded:
                loaded[dataset] = TerrainGrid.load(dataset, root)
            return loaded[dataset]

    @app.exception_handler(TerrainError)
    async def terrain_error(request: Request, exc: TerrainError):
        return JSONResponse(status_code=exc.status, content={"detail":{"code":exc.code,"message":str(exc)}})

    def read_json(relative):
        try:
            return json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise TerrainError("asset_unavailable",f"Prepared asset unavailable: {relative}",503) from exc

    def science_path(dataset):
        return ("data/processed/regional/points_of_interest.geojson" if dataset=="regional"
                else "science/points_of_interest.geojson")

    @app.get("/api/health")
    def health():
        status = {}
        for name in DATASETS:
            try:
                g = grid(name)
                status[name] = {"available":True,"shape":list(g.shape)}
            except TerrainError as exc:
                status[name] = {"available":False,"error":exc.code}
        ready = status["ctx"]["available"]
        return JSONResponse(status_code=200 if ready else 503,
                             content={"status":"ready" if ready else "data_missing","datasets":status})

    @app.get("/api/ready")
    def readiness():
        checks={}
        for name,action in [("mola",global_grid),("geology",geology_index),
                            ("atlas",lambda:read_json("data/processed/atlas/tiles.json")),
                            ("missions",lambda:read_json("data/processed/atlas/missions.json"))]:
            try:
                action();checks[name]=True
            except TerrainError:
                checks[name]=False
        for name,relative in {"frontend":"frontend/dist/index.html","viking":"data/processed/globe/mars_viking_colorized.jpg",
                              "topography":"data/processed/global/mola-topography.jpg",
                              "geology_texture":"data/processed/atlas/geology.png"}.items():
            checks[name]=(root/relative).is_file()
        ready=all(checks.values())
        return JSONResponse(status_code=200 if ready else 503,content={"ready":ready,"checks":checks})

    @app.get("/api/layers")
    def layers():
        terrains = {}
        for name in DATASETS:
            try:
                terrains[name] = {"available":True, "metadata":grid(name).metadata,
                                  "overlay_url":f"/api/overlays/{name}"}
            except TerrainError as exc:
                terrains[name] = {"available":False,"error":exc.code}
        imagery = read_json("data/processed/imagery_config.json")
        context_path = root/"data/processed/gis/context_config.json"
        if context_path.is_file():
            imagery["context"] = read_json("data/processed/gis/context_config.json")
        regional_ready=terrains.get("regional",{}).get("available",False)
        geology_directory="data/processed/regional" if regional_ready else "data/processed"
        catalog_query="?dataset=regional&display=true" if regional_ready else ""
        return {"coordinate_system":"Mars planetocentric latitude, east-positive longitude; NOT WGS84",
                "terrain":terrains,
                "imagery":imagery,
                "geology":{"url":"/api/geology"+catalog_query,"legend":read_json(f"{geology_directory}/geology_legend.json"),
                           "registration_uncertainty_m":[100,200],"source":"https://doi.org/10.3133/sim3464"},
                "science":{"url":"/api/points"+catalog_query,"geometry_type":"source_mapped_regions"},
                "notice":"Modelled terrain analysis, not a safety assessment."}

    @app.get("/api/elevation")
    def elevation(
        lon: Annotated[float, Query(ge=-180,le=180,allow_inf_nan=False)],
        lat: Annotated[float, Query(ge=-90,le=90,allow_inf_nan=False)],
        dataset: Dataset = "ctx",
    ):
        return grid(dataset).sample(lon,lat)

    @app.get("/api/terrain/mesh")
    def mesh(dataset: Dataset = "ctx",max_size: Annotated[int,Query(ge=20,le=260)]=220):
        return terrain_mesh(grid(dataset),max_size)

    @app.post("/api/route/profile")
    def profile(payload: ProfileRequest):
        return analyze_route(grid(payload.dataset), payload.coordinates,
                             sample_step_m=payload.sample_step_m, max_slope_deg=payload.max_slope_deg)

    @app.post("/api/route")
    def route(payload: RouteRequest):
        if not local_slots.acquire(blocking=False):
            raise TerrainError("server_busy","Зайняті локальні обчислення. Спробуйте за кілька секунд.",429)
        try:
            return local_route(payload)
        finally:
            local_slots.release()

    def local_route(payload):
        terrain = grid(payload.dataset)
        geometry = MarsRasterGeometry(terrain=terrain)
        result = plan_route(terrain.elevation, terrain.slope, terrain.valid, geometry,
                            (payload.start.lon, payload.start.lat), (payload.end.lon, payload.end.lat),
                            max_slope_deg=payload.max_slope_deg, slope_weight=payload.slope_weight,
                            mode=payload.mode,max_expansions=500000 if payload.dataset=="regional" else 200000,
                            time_budget_s=20 if payload.dataset=="regional" else 8)
        nearby = (nearby_regions(result["route"]["geometry"],read_json(science_path(payload.dataset)),
                                terrain,payload.nearby_radius_m) if result["status"]=="ok" else [])
        if payload.dataset=="regional" and nearby:
            display_catalog=read_json("data/processed/regional/points_of_interest_display.geojson")
            display_by_name={f["properties"]["name"]:f["geometry"] for f in display_catalog["features"]}
            nearby=[{**f,"geometry":display_by_name[f["properties"]["name"]],
                     "properties":{**f["properties"],"display_geometry_note":"15m topology-preserving display simplification; proximity calculated on exact source geometry."}} for f in nearby]
        return {"dataset": payload.dataset, **result,"nearby_science":nearby,
                "parameters":{"max_slope_deg":payload.max_slope_deg,"slope_weight":payload.slope_weight,
                              "nearby_radius_m":payload.nearby_radius_m},
                "warnings":["Research model, not a safety assessment.",
                            "Geology registration uncertainty is approximately 100–200 m.",
                            "Start/end are snapped to raster cell centres; distances exclude the subpixel offsets."]}

    @app.get("/api/points")
    def points(dataset: Dataset = "ctx",display: bool=False):
        if dataset=="regional" and display:
            return read_json("data/processed/regional/points_of_interest_display.geojson")
        return read_json(science_path(dataset))

    @app.get("/api/globe")
    def globe():
        return read_json("data/processed/globe/metadata.json")

    @app.get("/api/global")
    def global_metadata():
        return global_grid().metadata

    @app.get("/api/global/terrain")
    def global_display():
        with load_lock:
            cached = global_loaded.get("display")
        if cached is None:
            cached = global_grid().display()
            with load_lock:
                global_loaded["display"] = cached
        return cached

    @app.get("/api/global/elevation")
    def global_elevation(
        lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
        lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    ):
        return global_grid().sample((lon, lat))

    @app.post("/api/global/route")
    def global_route(payload: GlobalRouteRequest):
        if not global_slots.acquire(blocking=False):
            raise TerrainError("server_busy", "Обчислюються інші експедиції. Спробуйте за кілька секунд.", 429)
        try:
            points = [(p.lon,p.lat) for p in [payload.start,*payload.stops,payload.end]]
            terrain=global_grid()
            store=native_mola()
            planner=NativeMolaPlanner(store,terrain,terrain.hazards,rim_guard=native_rims())
            class PlanetTerrain:
                step=1/128
                metadata={"product":"NASA PDS MOLA MEGDR 128 ppd",
                    "equatorial_spacing_m":store.step_m,"vertical_datum":"MOLA GMM3 areoid, MEGDR v2",
                    "source_page":"https://pds-geosciences.wustl.edu/missions/mgs/megdr.html"}
                def index(self,point):return store.index(point)
                def route(self,a,b,max_grade_deg,slope_weight,time_budget_s):
                    return planner.route(a,b,max_grade_deg,slope_weight,budget_s=time_budget_s)
            result=expedition(PlanetTerrain(),points,payload.max_grade_deg,
                               payload.slope_weight,geology_index(),budget_s=90)
            if terrain.hazards is not None:
                hazards={}
                for point in points:
                    for h in terrain.hazards.nearby(point,radius_m=40000,limit=60):hazards[h["id"]]=h
                result.setdefault("hazards",list(hazards.values()))
            return result
        finally:
            global_slots.release()

    @app.post("/api/expedition")
    def plan_expedition(payload: ExpeditionRequest):
        points = [(p.lon,p.lat) for p in [payload.start,*payload.stops,payload.end]]
        local = None
        if payload.resolution != "mola":
            for dataset in (["hirise","regional"] if payload.resolution=="auto" else [payload.resolution]):
                try:
                    candidate=grid(dataset)
                    for point in points:
                        candidate.index(*point)
                    local=candidate
                    break
                except TerrainError:
                    if payload.resolution!="auto":
                        raise TerrainError("outside_coverage","Усі точки мають бути в межах обраної DEM.")
        if local is None:
            return global_route(payload)
        if not global_slots.acquire(blocking=False):
            raise TerrainError("server_busy", "Сервер зайнятий. Спробуйте за кілька секунд.", 429)
        try:
            geometry = MarsRasterGeometry(terrain=local)
            class LocalAdapter:
                counts = local.valid
                step = 0
                metadata = {"product":"USGS Jezero HiRISE DEM 1m" if local.dataset=="hirise" else "USGS Jezero CTX DEM 20m",
                            "equatorial_spacing_m":1 if local.dataset=="hirise" else 20,
                            "vertical_datum":f"Local {local.dataset} product; not blended with global MOLA",
                            "source_page":"https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic"}
                def index(self, point):
                    return local.index(*point)
                def route(self, start, end, max_grade_deg, slope_weight, time_budget_s):
                    result = plan_route(local.elevation,local.slope,local.valid,geometry,start,end,
                                        max_slope_deg=max_grade_deg,slope_weight=slope_weight,
                                        max_expansions=500000,time_budget_s=time_budget_s)
                    if result["status"] != "ok":
                        return result
                    metrics = result["metrics"]
                    profile = [{**p,"interpolated":False} for p in metrics["elevation_profile"]]
                    assessment=traversability_assessment(1 if local.dataset=="hirise" else 20,global_model=False)
                    return {**result,"dataset":local.dataset,"approximate":False,
                            "traversability":assessment,
                            "algorithm":f"Exact local A* on {local.dataset} grid",
                            "route":{**result["route"],"properties":{"coordinate_system":"Mars, NOT WGS84",
                                                                    "traversability":assessment}},
                            "metrics":{**metrics,"direct_distance_m":local.distance_m(start,end),
                                       "terrain_distance_m":sum(math.hypot(b["distance_m"]-a["distance_m"],b["elevation_m"]-a["elevation_m"])
                                                                for a,b in zip(profile,profile[1:])),
                                       "max_grade_deg":metrics["max_segment_grade_deg"],
                                       "cells":len(profile),"interpolated_cells":0,
                                       "snap_offsets_m":[local.distance_m(start,result["snapped_start"]),
                                                         local.distance_m(end,result["snapped_end"])]},
                            "profile":profile,
                            "warnings":["Local CTX terrain model, not a safety assessment.",
                                        "Endpoints snap to raster centres. Geology boundaries have source uncertainty."]}
            return expedition(LocalAdapter(),points,payload.max_grade_deg,payload.slope_weight,geology_index())
        finally:
            global_slots.release()

    @app.get("/api/atlas")
    def atlas_catalog():
        return {**read_json("data/processed/atlas/metadata.json"),
                "tiles": read_json("data/processed/atlas/tiles.json"),
                "legend": read_json("data/processed/atlas/geology_legend.json"),
                "missions": read_json("data/processed/atlas/missions.json")}

    @app.get("/api/atlas/geology")
    def atlas_geology():
        return read_json("data/processed/atlas/geology_display.geojson")

    @app.get("/api/atlas/inspect")
    def atlas_inspect(
        lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
        lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    ):
        measurements=[{"dataset":"mola",**global_grid().sample((lon,lat)),
                       "spacing_m":global_grid().metadata.get("equatorial_spacing_m"),"valid":True}]
        for dataset in ["regional","hirise"]:
            try:
                terrain=grid(dataset)
                sampled=terrain.sample(lon,lat)
                measurements.append({**sampled,"dataset":dataset,"spacing_m":1 if dataset=="hirise" else 20,
                                     "interpolated":False,"observations":None})
            except TerrainError:
                pass
        try:measurements.insert(1,native_mola().sample((lon,lat)))
        except TerrainError:pass
        selected=next((m for m in reversed(measurements) if m["valid"]),measurements[0])
        return {"elevation":selected,"measurements":measurements,
                "terrain_checks":[],
                "craters":global_grid().hazards.nearby((lon,lat),radius_m=25000,limit=40) if global_grid().hazards else [],
                "selection_note":"Finest valid available DEM at this point; source datums are not blended.",
                "geology": geology_index().point(lon,lat),
                "geology_scale": "1:20,000,000", "notice": "Source polygon query, not local hazard detection."}

    @lru_cache(maxsize=32)
    def slope_image(patch_id,grade):
        from PIL import Image
        patch=next((p for p in fine_patches() if p.metadata["id"]==patch_id),None)
        if patch is None:raise TerrainError("outside_coverage","No fine MOLA patch",404)
        import numpy as np
        rgba=np.zeros((*patch.shape,4),dtype=np.uint8)
        rgba[patch.slope>grade]=(255,65,65,150)
        stream=io.BytesIO();Image.fromarray(rgba).save(stream,format="PNG")
        return stream.getvalue()

    @app.get("/api/hazards/mola128/{patch_id}/slopes")
    def fine_slope_mask(patch_id: Literal["a","b"],
                        max_grade_deg: Annotated[float,Query(ge=0,le=90,allow_inf_nan=False)]=15):
        return Response(slope_image(patch_id,max_grade_deg),media_type="image/png",
                        headers={"Cache-Control":"public,max-age=86400"})

    @lru_cache(maxsize=32)
    def native_slope_image(west,south,east,north,grade):
        import numpy as np
        from PIL import Image
        r0,r1=round((90-north)*128),round((90-south)*128)
        c0,c1=round(west*128),round(east*128)
        heights,_=native_mola().window(r0-1,r1+1,c0-1,c1+1)
        lats=90-(np.arange(r0-1,r1+1)+.5)/128
        slope=terrain_slopes(heights,lats)[1:-1,1:-1]
        rgba=np.zeros((*slope.shape,4),dtype=np.uint8)
        rgba[native_rims().window(r0,r1,c0,c1)]=(255,171,64,170)
        rgba[slope>grade]=(255,65,65,165)
        rgba[~np.isfinite(slope)]=(160,160,160,140)
        stream=io.BytesIO();Image.fromarray(rgba).save(stream,format="PNG")
        return stream.getvalue()

    @app.get("/api/hazards/native-slopes")
    def native_slope_mask(
        west:Annotated[float,Query(ge=-180,le=180,allow_inf_nan=False)],
        south:Annotated[float,Query(ge=-88,le=88,allow_inf_nan=False)],
        east:Annotated[float,Query(ge=-180,le=180,allow_inf_nan=False)],
        north:Annotated[float,Query(ge=-88,le=88,allow_inf_nan=False)],
        max_grade_deg:Annotated[float,Query(ge=0,le=90,allow_inf_nan=False)]=15):
        if not 0<east-west<=8 or not 0<north-south<=8:
            raise TerrainError("invalid_extent","Шар схилів: до 8° × 8° за запит.")
        bounds=[round(v*128)/128 for v in (west,south,east,north)]
        if bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:
            raise TerrainError("invalid_extent","Область менша за клітинку DEM.")
        return Response(native_slope_image(*bounds,max_grade_deg),media_type="image/png",
            headers={"Cache-Control":"public,max-age=86400","X-Terrain-PPD":"128"})

    @app.get("/api/atlas/media/{name}")
    def mission_image(name: Literal["perseverance","jezero-delta","curiosity"]):
        return FileResponse(root/f"data/processed/atlas/media/{name}.jpg", media_type="image/jpeg")

    @app.get("/api/share/qr")
    def share_qr(url: Annotated[str, Query(min_length=8,max_length=2000)]):
        if urlparse(url).scheme not in ("http","https") or not urlparse(url).hostname:
            raise TerrainError("invalid_url","Expected an HTTP(S) URL")
        import qrcode
        stream=io.BytesIO()
        qrcode.make(url,box_size=5,border=4).save(stream,format="PNG")
        return Response(stream.getvalue(),media_type="image/png")

    @lru_cache(maxsize=256)
    def tile_bytes(layer, z, y, x):
        catalogs = read_json("data/processed/atlas/tiles.json")
        config = next((c for c in catalogs if c["id"] == layer), None)
        if not config or not 0 <= z < len(config["matrices"]) or not (0 <= y < 2**z and 0 <= x < 2**(z+1)):
            raise TerrainError("tile_not_found", "Unknown tile", 404)
        # Fixed official host and fixed catalog templates, never arbitrary URLs.
        url = config["template"]
        for key,value in {"Style":config["style"],"TileMatrixSet":config["matrix_set"],
                          "TileMatrix":config["matrices"][z],"TileRow":y,"TileCol":x}.items():
            url = url.replace("{"+key+"}",str(value))
        approved=("https://trek.nasa.gov/tiles/Mars/",
                  "https://astro.arcgis.com/arcgis/rest/services/OnMars/CTX/MapServer/tile/")
        if not url.startswith(approved):
            raise TerrainError("invalid_source", "Unapproved tile source", 503)
        local = root/f"data/processed/atlas/tiles/{layer}/{z}/{y}/{x}.tile"
        size=config.get("native_tile_size",256)
        if local.is_file():
            content=local.read_bytes()
            if valid_tile(content,size,layer):
                return content, config["format"]
        cache_key=url
        cached=cached_tile(cache_key,size,layer)
        if cached is not None:
            return cached,config["format"]
        if not tile_slots.acquire(timeout=15):
            raise TerrainError("tiles_busy", "Tile source busy; base imagery remains available", 503)
        try:
            with urlopen(url,timeout=12) as response:
                if not response.geturl().startswith(approved):
                    raise TerrainError("invalid_source", "Unexpected redirect", 503)
                content=response.read(1_000_001)
                if len(content)>1_000_000 or not response.headers.get("content-type","").startswith("image/"):
                    raise TerrainError("invalid_tile", "Invalid upstream image", 502)
                if not valid_tile(content,size,layer):
                    raise TerrainError("invalid_tile", "Truncated, repeated placeholder or invalid upstream tile; not cached", 502)
                store_tile(cache_key,content)
                return content, config["format"]
        except (URLError, TimeoutError, OSError) as exc:
            raise TerrainError("tile_unavailable", "NASA tile unavailable; local base imagery remains available", 503) from exc
        finally:
            tile_slots.release()

    @app.get("/api/atlas/tiles/{layer}/{z}/{y}/{x}")
    def atlas_tile(layer: Literal["hrsc","mola","themis-day","themis-night","viking-hd","ctx-global","ctx-jezero","hirise-jezero"],
                   z: int, y: int, x: int,fallback: bool=False):
        content,media,level=display_tile(layer,z,y,x,fallback)
        return Response(content,media_type=media,headers={"Cache-Control":"public, max-age=86400",
                        "X-Imagery-Source-LOD":str(level),"X-Imagery-Requested-LOD":str(z)})

    @lru_cache(maxsize=512)
    def display_tile(layer,z,y,x,fallback):
        try:
            content,media=tile_bytes(layer,z,y,x)
            return content,media,z
        except TerrainError as original:
            if not fallback or original.code not in ("invalid_tile","tile_unavailable","tiles_busy"):
                raise
            from PIL import Image
            for level in range(z-1,max(-1,z-4),-1):
                scale=2**(z-level)
                try:
                    content,_=tile_bytes(layer,level,y//scale,x//scale)
                    with Image.open(io.BytesIO(content)) as image:
                        width,height=image.width/scale,image.height/scale
                        sx,sy=(x%scale)*width,(y%scale)*height
                        crop=image.convert("RGBA").crop((sx,sy,sx+width,sy+height)).resize((256,256),Image.Resampling.BILINEAR)
                        stream=io.BytesIO();crop.save(stream,format="PNG")
                        return stream.getvalue(),"image/png",level
                except TerrainError:
                    continue
            raise original

    @app.get("/api/geology")
    def geology(dataset: Dataset = "ctx",display: bool=False):
        directory="data/processed/regional" if dataset=="regional" else "data/processed"
        filename="geology_display.geojson" if dataset=="regional" and display else "geology.geojson"
        return read_json(f"{directory}/{filename}")

    @app.get("/api/overlays/{dataset}")
    def overlays(dataset: Dataset):
        grid(dataset)
        directory = {"ctx":"data/processed/gis","hirise":"data/processed/hirise",
                     "regional":"data/processed/regional"}[dataset]
        return read_json(f"{directory}/overlay_config.json")

    # Explicit allowlist: never expose raw data or arbitrary workspace files.
    assets = {
        "ctx-optical.png":"data/processed/jezero_ctx_overlay.png",
        "mars-global.jpg":"data/processed/globe/mars_viking_colorized.jpg",
        "mola-topography.jpg":"data/processed/global/mola-topography.jpg",
        "global-geology.png":"data/processed/atlas/geology.png",
        "ctx-context.png":"data/processed/gis/context_overlay.png",
        "ctx-elevation.png":"data/processed/gis/elevation_overlay.png",
        "ctx-slope.png":"data/processed/gis/slope_overlay.png",
        "hirise-elevation.png":"data/processed/hirise/elevation_overlay.png",
        "hirise-slope.png":"data/processed/hirise/slope_overlay.png",
        "regional-elevation.png":"data/processed/regional/elevation_overlay.png",
        "regional-slope.png":"data/processed/regional/slope_overlay.png",
        "regional-nodata.png":"data/processed/regional/nodata_overlay.png",
    }

    @app.get("/api/assets/{name}")
    def asset(name: str):
        if name not in assets:
            raise TerrainError("asset_not_found","Unknown map asset",404)
        path = root / assets[name]
        if not path.is_file():
            raise TerrainError("asset_unavailable","Run scripts/build_gis_overlays.py",503)
        return FileResponse(path,media_type="image/jpeg" if path.suffix==".jpg" else "image/png")

    @app.get("/gis-check", include_in_schema=False)
    def map_check():
        return FileResponse(root / "frontend/gis-check/index.html",media_type="text/html")

    dist = root / "frontend/dist"
    if (dist/"assets").is_dir():
        app.mount("/assets",StaticFiles(directory=dist/"assets"),name="frontend-assets")

    @app.get("/",include_in_schema=False)
    def frontend():
        index = dist/"index.html"
        return FileResponse(index if index.is_file() else root/"frontend/gis-check/index.html",
                            media_type="text/html")

    return app


app = create_app()
