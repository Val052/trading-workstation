"""Scanner module — strategy-based stock scanner with risk calculator."""

from modules.base import BaseModule


class ScannerModule(BaseModule):
    id = "scanner"
    name = "Scanner"
    icon = "radar"
    description = "Strategy-based stock scanner with risk calculator"
    order = 1

    def register_routes(self, app):
        from modules.scanner.routers import scanner, candidates, strategies, settings
        app.include_router(scanner.router, prefix="/api/scanner", tags=["scanner"])
        app.include_router(candidates.router, prefix="/api/scanner", tags=["scanner"])
        app.include_router(strategies.router, prefix="/api/scanner", tags=["scanner"])
        app.include_router(settings.router, prefix="/api/scanner", tags=["scanner"])

    def get_models(self):
        from modules.scanner.models import (
            Strategy, ScanResult, Candidate, Outcome, AccountConfig,
        )
        return [Strategy, ScanResult, Candidate, Outcome, AccountConfig]


module_instance = ScannerModule()
