"""Market data service — yfinance wrapper with daily SQLite caching."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from core.services.cache import load_from_cache, save_to_cache

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
        cached = load_from_cache(ticker, today)
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

        save_to_cache(ticker, today, df)
        return df

    except Exception as e:
        logger.error(f"Failed to fetch {ticker}: {e}")
        return None


def get_multiple(
    tickers: list[str],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, pd.DataFrame]:
    """Fetch data for multiple tickers. Uses cache first, then batch-downloads uncached tickers."""
    today = date.today()
    result = {}
    uncached = []

    # Phase 1: load everything we can from cache
    for t in tickers:
        cached = load_from_cache(t, today)
        if cached is not None and not cached.empty:
            result[t] = cached
        else:
            uncached.append(t)

    if not uncached:
        logger.info(f"All {len(tickers)} tickers loaded from cache")
        return result

    logger.info(f"Cache hit: {len(result)}, downloading {len(uncached)} tickers in batch...")

    # Phase 2: batch download uncached tickers via yfinance (one HTTP call)
    start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    try:
        batch_df = yf.download(
            uncached,
            start=start,
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
        )
    except Exception as e:
        logger.error(f"Batch download failed: {e}")
        return result

    if batch_df.empty:
        logger.warning("Batch download returned empty DataFrame")
        return result

    # Parse batch result — yfinance returns MultiIndex columns (ticker, field)
    expected = ["Open", "High", "Low", "Close", "Volume"]

    for t in uncached:
        try:
            if len(uncached) == 1:
                # Single ticker: columns are flat or single-level MultiIndex
                df = batch_df.copy()
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
            else:
                df = batch_df[t].copy()

            df = df[[c for c in expected if c in df.columns]].dropna(how="all")
            if df.empty:
                continue

            save_to_cache(t, today, df)
            result[t] = df
        except Exception:
            continue

    logger.info(f"Total tickers loaded: {len(result)}")
    return result


def get_latest_price(ticker: str) -> float | None:
    """Get the most recent close price for a ticker."""
    df = get_price_data(ticker)
    if df is not None and not df.empty:
        return float(df["Close"].iloc[-1])
    return None
