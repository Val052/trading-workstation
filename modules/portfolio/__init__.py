"""Portfolio module — investment holdings tracker with enrichment."""

from modules.base import BaseModule


class PortfolioModule(BaseModule):
    id = "portfolio"
    name = "Portfolio"
    icon = "briefcase"
    description = "Track investment holdings, allocation, and performance metrics"
    order = 2

    def register_routes(self, app):
        from modules.portfolio.routers import portfolio
        app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])

    def get_models(self):
        from modules.portfolio.models import PortfolioHolding, PortfolioSnapshot
        return [PortfolioHolding, PortfolioSnapshot]


module_instance = PortfolioModule()
