"""Instrument registry — resolve tickers/ISINs to canonical instrument records."""

from __future__ import annotations

import logging
import re
from typing import Optional

import yfinance as yf

from core.database import SessionLocal
from core.models.instruments import Instrument

logger = logging.getLogger(__name__)

# ISIN pattern: 2-letter country code + 9 alphanumeric + 1 check digit
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def resolve_instrument(
    identifier: str,
    instrument_type: str = "equity",
    name: Optional[str] = None,
    currency: str = "USD",
) -> Instrument:
    """
    Resolve a ticker or ISIN to a canonical Instrument record.
    Creates the instrument if it doesn't exist.

    Resolution order:
    1. Check if already in registry (by ID, ticker, or ISIN)
    2. If ISIN, try to resolve via yfinance
    3. If ticker, resolve via yfinance for metadata
    4. If yfinance fails, create with whatever info we have
    """
    identifier = identifier.strip().upper()
    db = SessionLocal()
    try:
        # Check existing by ID
        existing = db.query(Instrument).filter(Instrument.id == identifier).first()
        if existing:
            return existing

        # Check by ticker
        existing = db.query(Instrument).filter(Instrument.ticker == identifier).first()
        if existing:
            return existing

        # Check by ISIN
        if ISIN_PATTERN.match(identifier):
            existing = db.query(Instrument).filter(Instrument.isin == identifier).first()
            if existing:
                return existing

        # Not found — create it
        is_isin = bool(ISIN_PATTERN.match(identifier))

        # For non-marketable types, skip yfinance lookup
        if instrument_type in ("cash", "real_estate", "cash_equivalent"):
            inst = Instrument(
                id=identifier,
                ticker=None if is_isin else identifier,
                isin=identifier if is_isin else None,
                name=name or identifier,
                instrument_type=instrument_type,
                currency=currency,
            )
            db.add(inst)
            db.commit()
            db.refresh(inst)
            return inst

        # Try yfinance for metadata
        yf_ticker = identifier
        resolved_name = name
        sector = None
        exchange = None

        try:
            tk = yf.Ticker(yf_ticker)
            info = tk.info
            if info:
                resolved_name = resolved_name or info.get("longName") or info.get("shortName")
                sector = info.get("sector")
                exchange = info.get("exchange")
                currency = info.get("currency", currency)
                # Determine type from yfinance
                quote_type = info.get("quoteType", "").lower()
                if quote_type == "etf":
                    instrument_type = "etf"
                elif quote_type == "index":
                    instrument_type = "index"
        except Exception as e:
            logger.debug(f"yfinance lookup failed for {identifier}: {e}")

        inst = Instrument(
            id=identifier,
            ticker=None if is_isin else identifier,
            isin=identifier if is_isin else None,
            name=resolved_name or identifier,
            instrument_type=instrument_type,
            currency=currency,
            sector=sector,
            exchange=exchange,
        )
        db.add(inst)
        db.commit()
        db.refresh(inst)
        return inst

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to resolve instrument {identifier}: {e}")
        # Return a transient instrument object so callers don't crash
        return Instrument(
            id=identifier,
            name=name or identifier,
            instrument_type=instrument_type,
            currency=currency,
        )
    finally:
        db.close()
