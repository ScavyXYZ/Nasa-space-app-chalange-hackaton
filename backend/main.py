"""Run: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000."""
import json
from contextlib import asynccontextmanager
from threading import Lock
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from algorithms import plan_route
from algorithms.grid import MarsRasterGeometry
from algorithms.metrics import analyze_route
from algorithms.terrain import DATASETS, ROOT, TerrainError, TerrainGrid

Dataset = Literal["ctx", "hirise"]


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
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],
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
        return {"coordinate_system":"Mars planetocentric latitude, east-positive longitude; NOT WGS84",
                "terrain":terrains,
                "imagery":read_json("data/processed/imagery_config.json"),
                "geology":{"url":"/api/geology","legend":read_json("data/processed/geology_legend.json"),
                           "registration_uncertainty_m":[100,200],"source":"https://doi.org/10.3133/sim3464"},
                "science":{"url":"/api/points","geometry_type":"source_mapped_regions"},
                "notice":"Modelled terrain analysis, not a safety assessment."}

    @app.get("/api/elevation")
    def elevation(
        lon: Annotated[float, Query(ge=-180,le=180,allow_inf_nan=False)],
        lat: Annotated[float, Query(ge=-90,le=90,allow_inf_nan=False)],
        dataset: Dataset = "ctx",
    ):
        return grid(dataset).sample(lon,lat)

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
                            mode=payload.mode)
        return {"dataset": payload.dataset, **result}

    @app.get("/api/points")
    def points():
        return read_json("science/points_of_interest.geojson")

    @app.get("/api/geology")
    def geology():
        return read_json("data/processed/geology.geojson")

    @app.get("/api/overlays/{dataset}")
    def overlays(dataset: Dataset):
        grid(dataset)
        directory = "data/processed/gis" if dataset == "ctx" else "data/processed/hirise"
        return read_json(f"{directory}/overlay_config.json")

    # Explicit allowlist: never expose raw data or arbitrary workspace files.
    assets = {
        "ctx-optical.png":"data/processed/jezero_ctx_overlay.png",
        "ctx-elevation.png":"data/processed/gis/elevation_overlay.png",
        "ctx-slope.png":"data/processed/gis/slope_overlay.png",
        "hirise-elevation.png":"data/processed/hirise/elevation_overlay.png",
        "hirise-slope.png":"data/processed/hirise/slope_overlay.png",
    }

    @app.get("/api/assets/{name}")
    def asset(name: str):
        if name not in assets:
            raise TerrainError("asset_not_found","Unknown map asset",404)
        path = root / assets[name]
        if not path.is_file():
            raise TerrainError("asset_unavailable","Run scripts/build_gis_overlays.py",503)
        return FileResponse(path,media_type="image/png")

    @app.get("/", include_in_schema=False)
    def map_check():
        return FileResponse(root / "frontend/gis-check/index.html",media_type="text/html")

    return app


app = create_app()
