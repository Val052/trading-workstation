"""Base class for all scanning strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Tuple

import pandas as pd


@dataclass
class ScanHit:
    """A single ticker that triggered a strategy's scan."""
    ticker: str
    price: float
    signal_data: dict = field(default_factory=dict)
    near_miss: bool = False          # True if passed all but one filter
    failed_filter: str = ""          # which filter it failed (for near misses)


class BaseStrategy(ABC):
    """
    Abstract base for pluggable strategies.

    Subclasses must define class attributes (id, name, etc.) and implement
    scan() and describe_signal(). The scanner discovers strategies by
    importing all modules in app/strategies/ and collecting BaseStrategy subclasses.
    """

    id: str               # slug, e.g. "ema_pullback_rs"
    name: str             # human-readable name
    description: str      # what the strategy looks for
    source: str           # where you learned it
    parameters: dict      # configurable thresholds with defaults
    references: list = []

    @abstractmethod
    def scan(self, universe: list, market_data: dict) -> list:
        """
        Run the scan against a universe of tickers.
        market_data maps ticker -> OHLCV DataFrame.
        Returns list of ScanHit for tickers that match criteria.
        Include near-miss hits with near_miss=True.
        """
        ...

    @abstractmethod
    def describe_signal(self, signal_data: dict) -> str:
        """Human-readable explanation of why this ticker triggered."""
        ...

    def to_db_dict(self) -> dict:
        """Serialize strategy metadata for the strategies DB table."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "parameters": self.parameters,
        }
