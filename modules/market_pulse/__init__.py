"""Market Pulse module — macro regime analysis and intermarket intelligence."""

from modules.base import BaseModule


class MarketPulseModule(BaseModule):
    id = "market_pulse"
    name = "Market Pulse"
    icon = "pulse"
    description = "Macro regime analysis: intermarket ratios, breadth, sectors, volatility"
    order = 0  # First in sidebar — context before everything

    def register_routes(self, app):
        from modules.market_pulse.routers import pulse
        app.include_router(pulse.router, prefix="/api/market_pulse", tags=["market_pulse"])

    def get_models(self):
        from modules.market_pulse.models import RegimeSnapshot, AssetTrend
        return [RegimeSnapshot, AssetTrend]


module_instance = MarketPulseModule()
