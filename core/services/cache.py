"""Shared price cache service — load/save DataFrames to SQLite."""

from __future__ import annotations

import logging
from datetime import date
from io import StringIO

import pandas as pd

from core.database import SessionLocal
from core.models.cache import PriceCache

logger = logging.getLogger(__name__)


def load_from_cache(ticker: str, cache_date: date) -> pd.DataFrame | None:
    """Load cached OHLCV DataFrame for a ticker+date. Returns None if not cached."""
    db = SessionLocal()
    try:
        row = (
            db.query(PriceCache)
            .filter(PriceCache.ticker == ticker, PriceCache.cache_date == cache_date)
            .first()
        )
        if row is None:
            return None
        df = pd.read_json(StringIO(row.data_json), orient="split")
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None
    finally:
        db.close()


def save_to_cache(ticker: str, cache_date: date, df: pd.DataFrame) -> None:
    """Save OHLCV DataFrame to cache, replacing any existing entry."""
    db = SessionLocal()
    try:
        db.query(PriceCache).filter(
            PriceCache.ticker == ticker, PriceCache.cache_date == cache_date,
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
