from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import refresh_interval_seconds
from .database import initialize_database
from .refresh import refresh_in_background

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    app.state.refresh_interval_seconds = refresh_interval_seconds()
    app.state.refresh_queued = refresh_in_background()
    app.state.last_manual_refresh = None
    scheduler = asyncio.create_task(_daily_refresh(app))
    try:
        yield
    finally:
        scheduler.cancel()
        try:
            await scheduler
        except asyncio.CancelledError:
            pass


async def _daily_refresh(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(app.state.refresh_interval_seconds)
        app.state.refresh_queued = refresh_in_background()


app = FastAPI(
    title="Japan COE Monthly Workload Dashboard",
    description=(
        "Official monthly e-Stat COE workload counts by immigration jurisdiction. "
        "Aggregate counts are not individual waiting-time predictions."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Japan COE Monthly Workload Dashboard",
        "api": "/docs",
        "overview": "/api/overview",
    }
