"""FastAPI application — Trading Workstation."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import init_db
from app.routers import scanner, candidates, strategies, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="Trading Workstation", version="0.1.0")

# Initialize database on startup
@app.on_event("startup")
def startup():
    init_db()
    logging.getLogger(__name__).info("Database initialized, tables created")

# Register API routers
app.include_router(scanner.router)
app.include_router(candidates.router)
app.include_router(strategies.router)
app.include_router(settings.router)

# Serve frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")
