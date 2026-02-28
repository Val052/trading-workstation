"""Options chain fetching, filtering, and caching via yfinance."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

import yfinance as yf

from modules.scanner.services.options_greeks import (
    bs_greeks,
    DEFAULT_RISK_FREE_RATE,
)

logger = logging.getLogger(__name__)

# Simple in-memory cache: {ticker: (timestamp, data)}
_chain_cache: dict = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def fetch_chain(
    ticker: str,
    min_dte: int = 14,
    max_dte: int = 90,
) -> dict:
    """
    Fetch all available options chains within the DTE window.

    Returns structured dict with underlying price, chains by expiry,
    each contract enriched with Greeks.
    """
    # Check cache
    cache_key = f"{ticker}:{min_dte}:{max_dte}"
    if cache_key in _chain_cache:
        ts, cached_data = _chain_cache[cache_key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return cached_data

    yf_ticker = yf.Ticker(ticker)

    # Get underlying price
    try:
        info = yf_ticker.info
        underlying = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        dividend_yield = info.get("dividendYield") or 0.0
    except Exception:
        underlying = None
        dividend_yield = 0.0

    if not underlying:
        logger.warning(f"Could not get underlying price for {ticker}")
        return {"ticker": ticker, "underlying_price": None, "dividend_yield": 0, "chains": {}, "error": "No price data"}

    # Get available expirations
    try:
        expirations = yf_ticker.options
    except Exception as e:
        logger.error(f"No options data for {ticker}: {e}")
        return {"ticker": ticker, "underlying_price": underlying, "dividend_yield": dividend_yield, "chains": {}, "error": "No options available"}

    if not expirations:
        return {"ticker": ticker, "underlying_price": underlying, "dividend_yield": dividend_yield, "chains": {}, "error": "No expirations available"}

    today = date.today()
    chains = {}

    for exp_str in expirations:
        exp_date = date.fromisoformat(exp_str)
        dte = (exp_date - today).days

        if dte < min_dte or dte > max_dte:
            continue

        try:
            chain = yf_ticker.option_chain(exp_str)
        except Exception as e:
            logger.warning(f"Failed to fetch chain {ticker} {exp_str}: {e}")
            continue

        T = dte / 365.0
        strike_min = underlying * 0.85
        strike_max = underlying * 1.15

        calls = _process_contracts(
            chain.calls, underlying, T, strike_min, strike_max, "call"
        )
        puts = _process_contracts(
            chain.puts, underlying, T, strike_min, strike_max, "put"
        )

        if calls or puts:
            chains[exp_str] = {"dte": dte, "calls": calls, "puts": puts}

    result = {
        "ticker": ticker,
        "underlying_price": underlying,
        "dividend_yield": dividend_yield,
        "chains": chains,
    }

    _chain_cache[cache_key] = (time.time(), result)
    return result


def _process_contracts(
    df,
    underlying: float,
    T: float,
    strike_min: float,
    strike_max: float,
    option_type: str,
) -> list:
    """Process a calls or puts DataFrame into filtered contract dicts with Greeks."""
    contracts = []

    if df is None or df.empty:
        return contracts

    for _, row in df.iterrows():
        strike = float(row.get("strike", 0))
        if strike < strike_min or strike > strike_max:
            continue

        bid = float(row.get("bid", 0))
        ask = float(row.get("ask", 0))

        # Skip zero bid (illiquid)
        if bid <= 0:
            continue

        mid = (bid + ask) / 2.0
        iv = float(row.get("impliedVolatility", 0))
        volume = int(row.get("volume", 0) or 0)
        oi = int(row.get("openInterest", 0) or 0)
        itm = bool(row.get("inTheMoney", False))

        # Compute Greeks using yfinance IV
        if iv > 0 and T > 0:
            greeks = bs_greeks(underlying, strike, T, DEFAULT_RISK_FREE_RATE, iv, option_type)
        else:
            greeks = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0}

        contracts.append({
            "strike": strike,
            "bid": round(bid, 2),
            "ask": round(ask, 2),
            "mid": round(mid, 2),
            "iv": round(iv, 4),
            "volume": volume,
            "open_interest": oi,
            "itm": itm,
            **greeks,
        })

    return contracts


def select_expiry(chains: dict, target_dte: int = 30) -> Optional[str]:
    """
    Pick the expiration closest to target_dte.
    Prefers monthly expirations (third Friday) over weeklies if within 5 days of target.
    """
    if not chains:
        return None

    best = None
    best_diff = float("inf")

    for exp_str, chain_data in chains.items():
        dte = chain_data["dte"]
        diff = abs(dte - target_dte)

        # Check if this is a monthly expiry (third Friday of month)
        exp_date = date.fromisoformat(exp_str)
        is_monthly = _is_third_friday(exp_date)

        # Prefer monthly if within 5 days of target and there's a weekly closer
        if diff < best_diff or (diff <= best_diff + 5 and is_monthly and not _is_third_friday_str(best, chains)):
            if diff < best_diff or is_monthly:
                best = exp_str
                best_diff = diff

    return best


def _is_third_friday(d: date) -> bool:
    """Check if date is the third Friday of its month."""
    if d.weekday() != 4:  # Not Friday
        return False
    # Third Friday is between 15th and 21st
    return 15 <= d.day <= 21


def _is_third_friday_str(exp_str: Optional[str], chains: dict) -> bool:
    if not exp_str:
        return False
    return _is_third_friday(date.fromisoformat(exp_str))


def select_strikes(
    chain_for_expiry: dict,
    underlying: float,
    strategy: str,
    stop: float,
    target: float,
) -> dict:
    """
    Smart strike selection based on strategy type.

    Returns dict with selected contracts for each leg.
    """
    calls = chain_for_expiry.get("calls", [])
    puts = chain_for_expiry.get("puts", [])

    result = {}

    if strategy == "long_call":
        # ATM or 1 strike ITM, delta 0.50-0.60
        long = _find_best_strike(calls, underlying, delta_range=(0.48, 0.65), prefer="atm")
        if long:
            result["long"] = long

    elif strategy == "bull_call_spread":
        # Long: ATM/1 ITM (delta ~0.55), Short: near target (delta ~0.30)
        long = _find_best_strike(calls, underlying, delta_range=(0.48, 0.65), prefer="atm")
        short = _find_best_strike(calls, target, delta_range=(0.20, 0.40), prefer="otm")
        if long and short and short["strike"] > long["strike"]:
            result["long"] = long
            result["short"] = short
        elif long:
            # Fallback: use 1-2 strikes OTM from long
            otm_calls = [c for c in calls if c["strike"] > long["strike"] and _is_liquid(c)]
            if otm_calls:
                result["long"] = long
                result["short"] = otm_calls[min(1, len(otm_calls) - 1)]

    elif strategy == "bull_put_spread":
        # Short: near entry/slightly below (delta ~-0.35), Long: near stop (delta ~-0.20)
        short = _find_best_strike(puts, underlying, delta_range=(-0.45, -0.25), prefer="atm")
        long = _find_best_strike(puts, stop, delta_range=(-0.30, -0.10), prefer="otm")
        if short and long and long["strike"] < short["strike"]:
            result["short"] = short
            result["long"] = long
        elif short:
            # Fallback: 1-2 strikes below short
            below_puts = [p for p in puts if p["strike"] < short["strike"] and _is_liquid(p)]
            below_puts.sort(key=lambda p: p["strike"], reverse=True)
            if below_puts:
                result["short"] = short
                result["long"] = below_puts[min(1, len(below_puts) - 1)]

    return result


def _find_best_strike(
    contracts: list,
    target_price: float,
    delta_range: tuple,
    prefer: str = "atm",
) -> Optional[dict]:
    """Find best strike matching delta range and liquidity criteria near target price."""
    candidates = []
    for c in contracts:
        if not _is_liquid(c):
            continue
        d = abs(c["delta"])
        if delta_range[0] <= c["delta"] <= delta_range[1] or delta_range[0] <= d <= delta_range[1]:
            candidates.append(c)

    if not candidates:
        # Relax liquidity filter
        for c in contracts:
            d = abs(c["delta"])
            if c["bid"] > 0 and (delta_range[0] <= c["delta"] <= delta_range[1] or delta_range[0] <= d <= delta_range[1]):
                candidates.append(c)

    if not candidates:
        return None

    # Sort by proximity to target price
    candidates.sort(key=lambda c: abs(c["strike"] - target_price))
    return candidates[0]


def _is_liquid(contract: dict) -> bool:
    """Check if contract passes liquidity filter."""
    if contract.get("open_interest", 0) < 100:
        return False
    if contract.get("bid", 0) <= 0:
        return False
    mid = contract.get("mid", 0)
    if mid > 0:
        spread_pct = (contract.get("ask", 0) - contract.get("bid", 0)) / mid
        if spread_pct > 0.10:
            return False
    return True
