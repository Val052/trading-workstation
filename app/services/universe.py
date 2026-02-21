"""Universe service — manages ticker lists including dynamic S&P 500."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

import pandas as pd

from app.database import SessionLocal
from app.models import PriceCache  # reuse cache table for universe storage

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

# 11 SPDR Select Sector ETFs
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Communication Services",
}


def get_sp500_tickers(force_refresh: bool = False) -> list:
    """
    Fetch S&P 500 ticker list from Wikipedia.
    Caches to config/sp500_cache.json (daily refresh).
    """
    cache_path = CONFIG_DIR / "sp500_cache.json"

    if not force_refresh and cache_path.exists():
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            if cached.get("date") == date.today().isoformat():
                return cached["tickers"]
        except Exception:
            pass

    # Fetch from Wikipedia
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        from io import StringIO
        html = urlopen(req, timeout=15).read().decode("utf-8")
        tables = pd.read_html(StringIO(html))
        df = tables[0]

        # The ticker column is usually "Symbol"
        tickers = df["Symbol"].str.strip().str.replace(".", "-", regex=False).tolist()
        tickers = [t for t in tickers if isinstance(t, str) and len(t) > 0]

        # Cache it
        with open(cache_path, "w") as f:
            json.dump({"date": date.today().isoformat(), "tickers": tickers}, f)

        logger.info(f"Fetched {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers

    except Exception as e:
        logger.error(f"Failed to fetch S&P 500 list: {e}")
        # Fallback to cached if available
        if cache_path.exists():
            with open(cache_path) as f:
                return json.load(f).get("tickers", [])
        return []


def get_sector_etf_tickers() -> list:
    """Return the 11 SPDR sector ETF tickers."""
    return list(SECTOR_ETFS.keys())


def get_sector_for_etf(etf: str) -> str:
    """Get sector name for an ETF ticker."""
    return SECTOR_ETFS.get(etf, "Unknown")


def get_universe(universe_type: Optional[str] = None) -> list:
    """
    Get the ticker universe based on type.
    Types: 'sp500', 'custom', 'sector_etfs'
    """
    if universe_type is None:
        # Read from settings.yaml
        import yaml
        settings_path = CONFIG_DIR / "settings.yaml"
        with open(settings_path) as f:
            settings = yaml.safe_load(f)
        universe_type = settings.get("scanner", {}).get("universe", "custom")

    if universe_type == "sp500":
        return get_sp500_tickers()
    elif universe_type == "sector_etfs":
        return get_sector_etf_tickers()
    else:
        # Custom — read from universe.json
        universe_path = CONFIG_DIR / "universe.json"
        with open(universe_path) as f:
            return json.load(f)["tickers"]
