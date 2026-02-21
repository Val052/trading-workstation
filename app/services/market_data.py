"""Market data service — yfinance wrapper with daily SQLite caching."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PriceCache

logger = logging.getLogger(__name__)

# How many calendar days of history to fetch (covers ~200 trading days)
DEFAULT_LOOKBACK_DAYS = 400


def get_price_data(
    ticker: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    force_refresh: bool = False,
) -> pd.DataFrame | None:
    """
    Fetch OHLCV data for a ticker. Checks SQLite cache first (keyed by today's date),
    falls back to yfinance download. Returns DataFrame with columns:
    Open, High, Low, Close, Volume — DatetimeIndex.
    Returns None if download fails.
    """
    today = date.today()

    if not force_refresh:
        cached = _load_from_cache(ticker, today)
        if cached is not None:
            return cached

    # Download from yfinance
    try:
        start = datetime.now() - timedelta(days=lookback_days)
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return None

        # yfinance single-ticker returns MultiIndex columns — flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Keep only standard OHLCV columns
        expected = ["Open", "High", "Low", "Close", "Volume"]
        df = df[[c for c in expected if c in df.columns]]

        _save_to_cache(ticker, today, df)
        return df

    except Exception as e:
        logger.error(f"Failed to fetch {ticker}: {e}")
        return None


def get_multiple(
    tickers: list[str],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, pd.DataFrame]:
    """Fetch data for multiple tickers. Skips failures silently."""
    result = {}
    for t in tickers:
        df = get_price_data(t, lookback_days)
        if df is not None and not df.empty:
            result[t] = df
    return result


def get_latest_price(ticker: str) -> float | None:
    """Get the most recent close price for a ticker."""
    df = get_price_data(ticker)
    if df is not None and not df.empty:
        return float(df["Close"].iloc[-1])
    return None


# ── Cache helpers ──────────────────────────────────────────────────────

def _load_from_cache(ticker: str, cache_date: date) -> pd.DataFrame | None:
    db = SessionLocal()
    try:
        row = (
            db.query(PriceCache)
            .filter(PriceCache.ticker == ticker, PriceCache.cache_date == cache_date)
            .first()
        )
        if row is None:
            return None
        from io import StringIO
        df = pd.read_json(StringIO(row.data_json), orient="split")
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None
    finally:
        db.close()


def _save_to_cache(ticker: str, cache_date: date, df: pd.DataFrame) -> None:
    db = SessionLocal()
    try:
        # Remove old cache for this ticker+date
        db.query(PriceCache).filter(
            PriceCache.ticker == ticker, PriceCache.cache_date == cache_date
        ).delete()

        row = PriceCache(
            ticker=ticker,
            cache_date=cache_date,
            data_json=df.to_json(orient="split", date_format="iso"),
        )
        db.add(row)
        db.commit()
    except Exception as e:
        logger.error(f"Cache save failed for {ticker}: {e}")
        db.rollback()
    finally:
        db.close()
