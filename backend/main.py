"""Run: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000."""
import json
import os
from contextlib import asynccontextmanager
from threading import Lock
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from algorithms import plan_route
from algorithms.grid import MarsRasterGeometry
from algorithms.metrics import analyze_route
from algorithms.terrain import DATASETS, ROOT, TerrainError, TerrainGrid
from algorithms.science import nearby_regions
from algorithms.mesh import terrain_mesh

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
