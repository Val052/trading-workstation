"""FastAPI app factory — Trading Terminal with module discovery."""

import importlib
import logging
import pkgutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.database import init_db, engine
from core.models.base import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent / "ui"


def discover_modules():
    """Auto-discover modules in the modules/ directory."""
    modules_path = Path(__file__).resolve().parent.parent / "modules"
    found = []

    for importer, modname, ispkg in pkgutil.iter_modules([str(modules_path)]):
        if not ispkg or modname.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"modules.{modname}")
            if hasattr(mod, "module_instance"):
                found.append(mod.module_instance)
                logger.info(f"Discovered module: {modname}")
        except Exception as e:
            logger.error(f"Failed to load module {modname}: {e}")

    return sorted(found, key=lambda m: m.order)


def create_app() -> FastAPI:
    app = FastAPI(title="Trading Terminal", version="2.0.0")
    modules = discover_modules()

    @app.on_event("startup")
    def startup():
        # Import all module models so they register with Base.metadata
        for mod in modules:
            mod.get_models()
        # Create all tables (platform + module)
        init_db()
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database initialized. {len(modules)} module(s) loaded.")

    # Register module routes
    for mod in modules:
        mod.register_routes(app)

    # API endpoint: list available modules (for frontend sidebar)
    @app.get("/api/modules")
    def list_modules():
        return [
            {
                "id": m.id,
                "name": m.name,
                "icon": m.icon,
                "order": m.order,
                "description": m.description,
            }
            for m in modules
        ]

    # Serve frontend
    app.mount("/static", StaticFiles(directory=UI_DIR / "static"), name="static")
    app.mount("/panels", StaticFiles(directory=UI_DIR / "module_panels"), name="panels")

    @app.get("/")
    def serve_shell():
        return FileResponse(UI_DIR / "shell.html")

    return app
