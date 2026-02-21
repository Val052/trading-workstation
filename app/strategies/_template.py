"""
Template for new strategies — copy this file, rename, and implement.

Steps:
1. Copy to app/strategies/your_strategy_name.py
2. Rename the class
3. Set id, name, description, source, parameters
4. Implement scan() and describe_signal()
5. The scanner auto-discovers it — no registration needed
"""

import pandas as pd

from app.strategies.base import BaseStrategy, ScanHit


class TemplateStrategy(BaseStrategy):

    id = "_template"  # change this — used as DB key
    name = "Template Strategy"
    description = "Describe what this strategy looks for."
    source = "Where you learned it"
    parameters = {
        # Add configurable thresholds here
    }
    references = []

    def scan(self, universe: list[str], market_data: dict[str, pd.DataFrame]) -> list[ScanHit]:
        """Implement your scan logic here."""
        hits: list[ScanHit] = []
        # for ticker in universe:
        #     df = market_data.get(ticker)
        #     if df is None:
        #         continue
        #     # ... your logic ...
        #     hits.append(ScanHit(ticker=ticker, price=..., signal_data={...}))
        return hits

    def describe_signal(self, signal_data: dict) -> str:
        """Human-readable explanation of why this ticker triggered."""
        return "Template — not implemented"
