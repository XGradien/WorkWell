"""WorkWell API.

Run with:

    uvicorn workwell.app:app --host 127.0.0.1 --port 8000

or the console script ``workwell`` (see pyproject [project.scripts]).

REST endpoints (stable contract for the dashboard):

    GET  /api/health                        liveness + version + mode
    GET  /api/state                         full snapshot (channels, mode, uptime)
    POST /api/control/start                 start live collection
    POST /api/control/stop                  stop everything
    GET  /api/simulation/scenarios          list demo scenarios
    POST /api/simulation/start              {scenario: calm|focus|meeting|stress|dynamic}
    POST /api/simulation/stop
    GET  /api/wellness?minutes=30           score + components + weakest channel
    GET  /api/wellness/recommendations      actionable suggestions
    GET  /api/wellness/patterns?days=7      longer-range observations
    GET  /api/analytics/series?channel=greenery&minutes=60&bucket=30
    WS   /ws/live                           state snapshot every second
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .config import Config
from .manager import (
    Manager,
)
from .simulator import SCENARIOS, Simulator
from .store import CHANNEL_META, CHANNELS, Store, parse_ts
from .wellness import WellnessEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("workwell.api")


class SimulationStart(BaseModel):
    scenario: str = "calm"


# --- app factory -----------------------------------------------------------


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.load()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store_path = config.get("storage.path", "data/workwell.db")
        if not os.path.isabs(store_path):
            store_path = os.path.join(os.getcwd(), store_path)
        app.state.store = Store(store_path)
        app.state.manager = Manager(app.state.store, config)
        app.state.engine = WellnessEngine(app.state.store, config.get("wellness.weights"))
        prune_days = float(config.get("storage.prune_days", 30))
        if prune_days > 0:
            removed = app.state.store.prune(prune_days)
            if removed:
                logger.info("pruned %d old readings", removed)
        logger.info("WorkWell v%s ready (store=%s)", __version__, store_path)
        yield
        app.state.manager.stop_all()

    app = FastAPI(
        title="WorkWell API",
        description="Local, privacy-first workspace wellness monitoring.",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- core endpoints ------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "mode": app.state.manager.mode}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        snap = app.state.manager.state()
        snap["wellness"] = app.state.engine.score(int(config.get("wellness.window_minutes", 30)))
        return snap

    @app.post("/api/control/start")
    async def control_start() -> dict[str, Any]:
        result = app.state.manager.start_live()
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail=result.get("error", "could not start"))
        return result

    @app.post("/api/control/stop")
    async def control_stop() -> dict[str, Any]:
        return app.state.manager.stop_all()

    # --- simulation ------------------------------------------------------

    @app.get("/api/simulation/scenarios")
    async def simulation_scenarios() -> dict[str, Any]:
        return {"scenarios": Simulator.available_scenarios(), "default": config.get("simulation.default_scenario", "calm")}

    @app.post("/api/simulation/start")
    async def simulation_start(payload: SimulationStart) -> dict[str, Any]:
        if payload.scenario not in SCENARIOS:
            raise HTTPException(status_code=400, detail=f"unknown scenario '{payload.scenario}'; use one of {list(SCENARIOS)}")
        result = app.state.manager.start_simulation(payload.scenario)
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail=result.get("error", "could not start simulation"))
        return result

    @app.post("/api/simulation/stop")
    async def simulation_stop() -> dict[str, Any]:
        return app.state.manager.stop_all()

    # --- wellness -----------------------------------------------------------

    @app.get("/api/wellness")
    async def wellness(minutes: int = 30) -> dict[str, Any]:
        if not 1 <= minutes <= 7 * 1440:
            raise HTTPException(status_code=400, detail="minutes must be 1..10080")
        return app.state.engine.score(minutes)

    @app.get("/api/wellness/recommendations")
    async def wellness_recommendations(minutes: int = 60) -> dict[str, Any]:
        if not 1 <= minutes <= 7 * 1440:
            raise HTTPException(status_code=400, detail="minutes must be 1..10080")
        return app.state.engine.recommendations(minutes)

    @app.get("/api/wellness/patterns")
    async def wellness_patterns(days: int = 7) -> dict[str, Any]:
        if not 1 <= days <= 30:
            raise HTTPException(status_code=400, detail="days must be 1..30")
        return app.state.engine.patterns(days)

    # --- analytics -------------------------------------------------------------

    @app.get("/api/analytics/series")
    async def analytics_series(channel: str, minutes: int = 60, bucket: int = 30) -> dict[str, Any]:
        if channel not in CHANNELS:
            raise HTTPException(status_code=400, detail=f"unknown channel '{channel}'")
        if not 1 <= minutes <= 7 * 1440:
            raise HTTPException(status_code=400, detail="minutes must be 1..10080")
        if not 5 <= bucket <= 3600:
            raise HTTPException(status_code=400, detail="bucket must be 5..3600 seconds")

        rows = app.state.store.series(
            channel, minutes=minutes, scalar_only=(channel == "mood")
        )
        points: dict[int, dict[str, Any]] = {}
        for row in rows:
            epoch = parse_ts(row["ts"]).timestamp()
            key = int(epoch // bucket)
            p = points.setdefault(key, {"n": 0, "sum": 0.0, "min": float("inf"), "max": float("-inf")})
            p["n"] += 1
            p["sum"] += row["value"]
            p["min"] = min(p["min"], row["value"])
            p["max"] = max(p["max"], row["value"])

        out = []
        for key in sorted(points):
            p = points[key]
            out.append({
                "ts": datetime.fromtimestamp(key * bucket, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "avg": round(p["sum"] / p["n"], 2),
                "min": round(p["min"], 2),
                "max": round(p["max"], 2),
                "n": p["n"],
            })
        return {"channel": channel, "unit": CHANNEL_META[channel]["unit"], "minutes": minutes, "bucket_seconds": bucket, "points": out}

    # --- websocket ---------------------------------------------------------------

    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(app.state.manager.state())
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, RuntimeError):
            return

    # --- static dashboard (production build) ---------------------------------------
    # Serves the built frontend when it exists, so a single `workwell` command
    # runs the whole app: API + dashboard on one port, all local.
    web_dir = config.get("server.web_dist")
    if web_dir is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        web_dir = os.path.join(repo_root, "frontend", "dist")
    elif not os.path.isabs(web_dir):
        web_dir = os.path.join(os.getcwd(), web_dir)
    if os.path.isdir(web_dir):
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="dashboard")

    return app


app = create_app()


def main() -> None:
    """Console entry point: python -m workwell or the `workwell` command."""
    import uvicorn

    config = Config.load()
    uvicorn.run(
        "workwell.app:app",
        host=config.get("server.host", "127.0.0.1"),
        port=int(config.get("server.port", 8000)),
        log_level="info",
    )


if __name__ == "__main__":
    main()
