"""Portfolio enrichment — compute live metrics for holdings and portfolio."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from core.services import market_data
from core.database import SessionLocal
from core.models.instruments import Instrument

logger = logging.getLogger(__name__)

# Cache the EUR/USD rate for the session to avoid repeated fetches
_fx_cache: dict[str, float] = {}


def _get_fx_rate(pair: str = "EURUSD=X") -> float:
    """Fetch EUR/USD rate. Returns rate or 1.0 on failure."""
    if pair in _fx_cache:
        return _fx_cache[pair]
    try:
        import yfinance as yf
        tk = yf.Ticker(pair)
        info = tk.info
        rate = info.get("regularMarketPrice") or info.get("previousClose") or 1.0
        _fx_cache[pair] = float(rate)
        return float(rate)
    except Exception as e:
        logger.warning(f"Failed to fetch FX rate {pair}: {e}")
        _fx_cache[pair] = 1.0
        return 1.0


def _get_instrument(instrument_id: str) -> Optional[Instrument]:
    """Load instrument record from DB."""
    db = SessionLocal()
    try:
        return db.query(Instrument).filter(Instrument.id == instrument_id).first()
    finally:
        db.close()


def enrich_holding(holding, instrument: Optional[Instrument] = None) -> dict:
    """
    Enrich a single holding with live market data.
    Returns dict with all computed metrics.
    """
    if instrument is None:
        instrument = _get_instrument(holding.instrument_id)

    result = {
        "id": holding.id,
        "instrument_id": holding.instrument_id,
        "name": instrument.name if instrument else holding.instrument_id,
        "ticker": instrument.ticker if instrument else holding.instrument_id,
        "instrument_type": instrument.instrument_type if instrument else holding.asset_class,
        "shares": holding.shares,
        "cost_basis": holding.cost_basis,
        "cost_basis_currency": holding.cost_basis_currency,
        "date_acquired": holding.date_acquired.isoformat() if holding.date_acquired else None,
        "account_label": holding.account_label,
        "asset_class": holding.asset_class,
        "notes": holding.notes,
        "sector": instrument.sector if instrument else None,
        "currency": instrument.currency if instrument else holding.cost_basis_currency,
    }

    # Non-marketable assets: cash, real_estate — no price enrichment
    if holding.asset_class in ("cash_equivalent", "real_estate"):
        result.update({
            "current_price": holding.cost_basis,
            "market_value": holding.shares * holding.cost_basis,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "vs_50dma_pct": None,
            "vs_200dma_pct": None,
            "dma50_slope": None,
            "dma200_slope": None,
            "rs_vs_spy": None,
            "range_52w_pct": None,
            "atr_14": None,
            "daily_change_pct": None,
            "trend": "N/A",
        })
        return result

    # Fetch price data
    ticker = instrument.ticker if instrument and instrument.ticker else holding.instrument_id
    df = market_data.get_price_data(ticker)

    if df is None or df.empty or len(df) < 10:
        result.update({
            "current_price": None,
            "market_value": None,
            "unrealized_pnl": None,
            "unrealized_pnl_pct": None,
            "vs_50dma_pct": None,
            "vs_200dma_pct": None,
            "dma50_slope": None,
            "dma200_slope": None,
            "rs_vs_spy": None,
            "range_52w_pct": None,
            "atr_14": None,
            "daily_change_pct": None,
            "trend": "No data",
        })
        return result

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    current_price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else current_price

    # Market value and P/L
    market_value = holding.shares * current_price
    total_cost = holding.shares * holding.cost_basis

    # Handle currency conversion for P/L
    inst_currency = instrument.currency if instrument else "USD"
    if holding.cost_basis_currency == "EUR" and inst_currency == "USD":
        # Convert USD market value to EUR for P/L comparison
        eur_usd = _get_fx_rate("EURUSD=X")
        market_value_eur = market_value / eur_usd if eur_usd > 0 else market_value
        unrealized_pnl = market_value_eur - total_cost
    elif holding.cost_basis_currency == "USD" and inst_currency == "USD":
        unrealized_pnl = market_value - total_cost
        market_value_eur = None
    else:
        unrealized_pnl = market_value - total_cost
        market_value_eur = None

    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

    # Moving averages
    dma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    dma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    vs_50dma_pct = ((current_price - dma_50) / dma_50 * 100) if dma_50 else None
    vs_200dma_pct = ((current_price - dma_200) / dma_200 * 100) if dma_200 else None

    # DMA slopes (5-day change in DMA value)
    dma50_slope = None
    if len(close) >= 55:
        dma50_series = close.rolling(50).mean()
        dma50_slope = "rising" if float(dma50_series.iloc[-1]) > float(dma50_series.iloc[-6]) else "falling"

    dma200_slope = None
    if len(close) >= 205:
        dma200_series = close.rolling(200).mean()
        dma200_slope = "rising" if float(dma200_series.iloc[-1]) > float(dma200_series.iloc[-6]) else "falling"

    # Relative strength vs SPY (10-day)
    rs_vs_spy = None
    spy_df = market_data.get_price_data("SPY")
    if spy_df is not None and len(spy_df) >= 11 and len(close) >= 11:
        stock_ret = (float(close.iloc[-1]) / float(close.iloc[-11])) - 1
        spy_ret = (float(spy_df["Close"].iloc[-1]) / float(spy_df["Close"].iloc[-11])) - 1
        if spy_ret != 0:
            rs_vs_spy = round(stock_ret / abs(spy_ret), 3)

    # 52-week range position
    range_52w_pct = None
    lookback = min(252, len(df))
    if lookback >= 50:
        high_52w = float(high.iloc[-lookback:].max())
        low_52w = float(low.iloc[-lookback:].min())
        if high_52w != low_52w:
            range_52w_pct = round((current_price - low_52w) / (high_52w - low_52w) * 100, 1)

    # ATR(14)
    atr_14 = None
    if len(df) >= 15:
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_14 = round(float(tr.iloc[-14:].mean()), 2)

    # Daily change
    daily_change_pct = round((current_price - prev_close) / prev_close * 100, 2)

    # Trend summary
    trend = "neutral"
    if dma_50 and dma_200:
        if current_price > dma_50 and current_price > dma_200 and dma50_slope == "rising":
            trend = "bullish"
        elif current_price < dma_50 and current_price < dma_200:
            trend = "bearish"

    result.update({
        "current_price": round(current_price, 2),
        "market_value": round(market_value, 2),
        "market_value_eur": round(market_value_eur, 2) if market_value_eur else None,
        "unrealized_pnl": round(unrealized_pnl, 2),
        "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
        "vs_50dma_pct": round(vs_50dma_pct, 2) if vs_50dma_pct else None,
        "vs_200dma_pct": round(vs_200dma_pct, 2) if vs_200dma_pct else None,
        "dma50_slope": dma50_slope,
        "dma200_slope": dma200_slope,
        "rs_vs_spy": rs_vs_spy,
        "range_52w_pct": range_52w_pct,
        "atr_14": atr_14,
        "daily_change_pct": daily_change_pct,
        "trend": trend,
    })

    return result


def enrich_holdings_parallel(holdings, instruments_map: dict) -> list[dict]:
    """Enrich multiple holdings in parallel using ThreadPoolExecutor."""
    enriched = []

    # Pre-fetch all price data in batch
    tickers = set()
    for h in holdings:
        inst = instruments_map.get(h.instrument_id)
        if inst and inst.ticker and h.asset_class not in ("cash_equivalent", "real_estate"):
            tickers.add(inst.ticker)
    tickers.add("SPY")  # Always need SPY for RS

    logger.info(f"Pre-fetching price data for {len(tickers)} tickers...")
    market_data.get_multiple(list(tickers))

    # Now enrich each holding (data is cached, so this is fast)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for h in holdings:
            inst = instruments_map.get(h.instrument_id)
            futures[executor.submit(enrich_holding, h, inst)] = h

        for future in as_completed(futures):
            try:
                enriched.append(future.result())
            except Exception as e:
                h = futures[future]
                logger.error(f"Enrichment failed for {h.instrument_id}: {e}")
                enriched.append({
                    "id": h.id,
                    "instrument_id": h.instrument_id,
                    "error": str(e),
                })

    return enriched


def compute_portfolio_summary(enriched_holdings: list[dict]) -> dict:
    """Compute portfolio-level analytics from enriched holdings."""
    total_value = 0.0
    total_cost = 0.0
    total_pnl = 0.0

    by_asset_class = {}
    by_sector = {}
    by_account = {}
    by_currency = {}
    weights = []
    above_50dma = 0
    above_200dma = 0
    marketable_count = 0

    for h in enriched_holdings:
        mv = h.get("market_value") or 0
        cost = (h.get("shares") or 0) * (h.get("cost_basis") or 0)
        pnl = h.get("unrealized_pnl") or 0

        total_value += mv
        total_cost += cost
        total_pnl += pnl

        # Allocation buckets
        ac = h.get("asset_class", "other")
        by_asset_class[ac] = by_asset_class.get(ac, 0) + mv

        sector = h.get("sector") or "Unknown"
        if h.get("asset_class") in ("equity", "etf"):
            by_sector[sector] = by_sector.get(sector, 0) + mv

        account = h.get("account_label", "default")
        by_account[account] = by_account.get(account, 0) + mv

        currency = h.get("currency", "USD")
        by_currency[currency] = by_currency.get(currency, 0) + mv

        weights.append(mv)

        # Breadth
        if h.get("vs_50dma_pct") is not None:
            marketable_count += 1
            if h["vs_50dma_pct"] > 0:
                above_50dma += 1
            if h.get("vs_200dma_pct") is not None and h["vs_200dma_pct"] > 0:
                above_200dma += 1

    # Concentration metrics
    max_weight_pct = 0
    top5_weight_pct = 0
    herfindahl = 0
    if total_value > 0:
        weight_pcts = sorted([(w / total_value * 100) for w in weights], reverse=True)
        max_weight_pct = weight_pcts[0] if weight_pcts else 0
        top5_weight_pct = sum(weight_pcts[:5])
        herfindahl = sum((w / 100) ** 2 for w in weight_pcts)

        # Convert allocation dicts to percentages
        for k in by_asset_class:
            by_asset_class[k] = round(by_asset_class[k] / total_value * 100, 1)
        for k in by_sector:
            by_sector[k] = round(by_sector[k] / total_value * 100, 1)
        for k in by_account:
            by_account[k] = round(by_account[k] / total_value * 100, 1)
        for k in by_currency:
            by_currency[k] = round(by_currency[k] / total_value * 100, 1)

    pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    return {
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(pnl_pct, 2),
        "holdings_count": len(enriched_holdings),
        "allocation": {
            "by_asset_class": by_asset_class,
            "by_sector": by_sector,
            "by_account": by_account,
            "by_currency": by_currency,
        },
        "concentration": {
            "max_weight_pct": round(max_weight_pct, 1),
            "top5_weight_pct": round(top5_weight_pct, 1),
            "herfindahl": round(herfindahl, 4),
        },
        "breadth": {
            "above_50dma": above_50dma,
            "above_200dma": above_200dma,
            "marketable_count": marketable_count,
            "pct_above_50dma": round(above_50dma / marketable_count * 100, 1) if marketable_count > 0 else 0,
            "pct_above_200dma": round(above_200dma / marketable_count * 100, 1) if marketable_count > 0 else 0,
        },
    }
