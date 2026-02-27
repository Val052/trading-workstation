"""
AVWAP Support Bounce strategy (Brian Shannon).

Looks for price approaching anchored VWAP from significant pivots:
- Last earnings date (auto-detected via yfinance)
- 52-week high
Price near AVWAP + relative strength = potential support bounce.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from modules.scanner.strategies.base import BaseStrategy, ScanHit

logger = logging.getLogger(__name__)


def _compute_avwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """
    Compute Anchored VWAP from a given bar index.
    AVWAP = cumulative(typical_price * volume) / cumulative(volume)
    """
    sliced = df.iloc[anchor_idx:]
    typical = (sliced["High"] + sliced["Low"] + sliced["Close"]) / 3
    cum_tpv = (typical * sliced["Volume"]).cumsum()
    cum_vol = sliced["Volume"].cumsum()
    avwap = cum_tpv / cum_vol.replace(0, np.nan)
    return avwap


def _find_earnings_anchor(ticker: str, df: pd.DataFrame) -> Optional[int]:
    """
    Find the most recent earnings date and return its index in the DataFrame.
    Uses yfinance calendar or earnings_dates.
    """
    try:
        tk = yf.Ticker(ticker)
        # Try earnings_dates first (returns past + future dates)
        try:
            ed = tk.earnings_dates
            if ed is not None and len(ed) > 0:
                dates = ed.index.tz_localize(None) if ed.index.tz else ed.index
                # Find most recent past earnings date
                today = pd.Timestamp.now().normalize()
                past = [d for d in dates if d <= today]
                if past:
                    earn_date = max(past)
                    # Find closest index in df
                    mask = df.index >= earn_date
                    if mask.any():
                        return int(np.where(mask)[0][0])
        except Exception:
            pass

        # Fallback: try calendar
        try:
            cal = tk.calendar
            if cal is not None and not cal.empty:
                if "Earnings Date" in cal.index:
                    earn_date = pd.Timestamp(cal.loc["Earnings Date"].iloc[0])
                    if earn_date.tz:
                        earn_date = earn_date.tz_localize(None)
                    mask = df.index >= earn_date
                    if mask.any():
                        return int(np.where(mask)[0][0])
        except Exception:
            pass

    except Exception as e:
        logger.debug(f"No earnings date for {ticker}: {e}")

    return None


def _find_52w_high_anchor(df: pd.DataFrame) -> Optional[int]:
    """Find the index of the 52-week high in the DataFrame."""
    if len(df) < 50:
        return None
    # Look at last 252 trading days (approx 1 year)
    lookback = min(252, len(df))
    window = df.iloc[-lookback:]
    high_idx = window["High"].idxmax()
    return int(df.index.get_loc(high_idx))


class AVWAPBounce(BaseStrategy):

    id = "avwap_bounce"
    name = "AVWAP Support Bounce"
    description = (
        "Finds stocks approaching anchored VWAP from significant pivots "
        "(earnings, 52-week high) with relative strength — potential support bounce."
    )
    source = "Brian Shannon, Anchored VWAP"
    parameters = {
        "proximity_pct": 0.02,   # within 2% of AVWAP
        "rs_lookback": 10,
        "min_rs_ratio": 0.8,     # slightly more lenient than EMA pullback
        "min_bars_from_anchor": 10,  # anchor must be at least 10 bars ago
    }
    references = [
        "Brian Shannon — Anchored VWAP",
        "https://alphatrends.net/",
    ]

    def scan(self, universe: list, market_data: dict) -> list:
        """Run scan. Expects market_data to include 'SPY'."""
        hits = []
        spy_df = market_data.get("SPY")
        if spy_df is None or len(spy_df) < 50:
            return hits

        for ticker in universe:
            if ticker == "SPY":
                continue
            df = market_data.get(ticker)
            if df is None or len(df) < 100:
                continue

            hit = self._evaluate(ticker, df, spy_df)
            if hit is not None:
                hits.append(hit)

        return hits

    def _evaluate(self, ticker: str, df: pd.DataFrame, spy_df: pd.DataFrame) -> Optional[ScanHit]:
        """Check if ticker is bouncing off an anchored VWAP."""
        p = self.parameters
        close = df["Close"]
        latest = float(close.iloc[-1])

        # Find anchor points
        anchors = {}

        earn_idx = _find_earnings_anchor(ticker, df)
        if earn_idx is not None and (len(df) - earn_idx) >= p["min_bars_from_anchor"]:
            anchors["earnings"] = earn_idx

        high_idx = _find_52w_high_anchor(df)
        if high_idx is not None and (len(df) - high_idx) >= p["min_bars_from_anchor"]:
            anchors["52w_high"] = high_idx

        if not anchors:
            return None

        # Check each anchor AVWAP for proximity
        best_anchor = None
        best_avwap_val = None
        best_dist = 999.0

        for anchor_name, anchor_idx in anchors.items():
            avwap = _compute_avwap(df, anchor_idx)
            if avwap.empty or avwap.isna().all():
                continue
            avwap_val = float(avwap.iloc[-1])
            if np.isnan(avwap_val) or avwap_val <= 0:
                continue

            dist = abs(latest - avwap_val) / latest
            if dist <= p["proximity_pct"] and dist < best_dist:
                best_anchor = anchor_name
                best_avwap_val = avwap_val
                best_dist = dist

        if best_anchor is None:
            return None

        # Price should be at or slightly above AVWAP (support test, not breakdown)
        price_vs_avwap = "above" if latest >= best_avwap_val else "below"

        # Relative strength check
        lb = p["rs_lookback"]
        if len(close) < lb + 1 or len(spy_df) < lb + 1:
            return None

        stock_ret = (float(close.iloc[-1]) / float(close.iloc[-lb - 1])) - 1
        spy_ret = (float(spy_df["Close"].iloc[-1]) / float(spy_df["Close"].iloc[-lb - 1])) - 1

        if spy_ret == 0:
            rs_ratio = 999.0 if stock_ret > 0 else 0.0
        else:
            rs_ratio = stock_ret / spy_ret if spy_ret > 0 else stock_ret / abs(spy_ret)

        if rs_ratio < p["min_rs_ratio"]:
            return None

        # ATR for stop
        high = df["High"]
        low = df["Low"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_14 = float(tr.iloc[-14:].mean())

        # Swing low
        swing_low = float(low.iloc[-10:].min())

        # Anchor date
        anchor_date = str(df.index[anchors[best_anchor]].date())

        signal = {
            "anchor_type": best_anchor,
            "anchor_date": anchor_date,
            "avwap": round(best_avwap_val, 2),
            "dist_to_avwap_pct": round(best_dist * 100, 2),
            "price_vs_avwap": price_vs_avwap,
            "rs_ratio": round(rs_ratio, 3),
            "stock_return_pct": round(stock_ret * 100, 2),
            "spy_return_pct": round(spy_ret * 100, 2),
            "atr_14": round(atr_14, 2),
            "swing_low_10": round(swing_low, 2),
            "suggested_stop": round(best_avwap_val - atr_14, 2),
            "all_anchors": {k: str(df.index[v].date()) for k, v in anchors.items()},
        }

        return ScanHit(ticker=ticker, price=round(latest, 2), signal_data=signal)

    def describe_signal(self, signal_data: dict) -> str:
        """Human-readable explanation."""
        return (
            f"Near {signal_data.get('anchor_type', '?')} AVWAP "
            f"(${signal_data.get('avwap', '?')}, {signal_data.get('dist_to_avwap_pct', '?')}% away, "
            f"{signal_data.get('price_vs_avwap', '?')}). "
            f"Anchor: {signal_data.get('anchor_date', '?')}. "
            f"RS {signal_data.get('rs_ratio', '?')}x vs SPY. "
            f"Stop: ${signal_data.get('suggested_stop', '?')}"
        )
