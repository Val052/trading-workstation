"""Base module interface — all modules implement this."""

from abc import ABC, abstractmethod

from fastapi import FastAPI


class BaseModule(ABC):
    """
    Abstract base for platform modules. Each module registers its routes,
    declares its models, and provides UI asset paths.
    """
    id: str              # "scanner", "portfolio", etc.
    name: str            # Human-readable name for sidebar
    icon: str            # CSS class or identifier for sidebar icon
    description: str
    order: int = 0       # Sidebar sort order (lower = higher)

    @abstractmethod
    def register_routes(self, app: FastAPI) -> None:
        """Register API routes. All routes must be under /api/{self.id}/"""

    @abstractmethod
    def get_models(self) -> list:
        """Return SQLAlchemy model classes for table creation."""

    def get_ui_assets(self) -> dict:
        """Return dict with panel_html, panel_js paths relative to core/ui/."""
        return {
            "panel_html": f"module_panels/{self.id}.html",
            "panel_js": f"module_panels/{self.id}.js",
        }
