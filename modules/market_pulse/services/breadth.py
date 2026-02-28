"""Equity breadth calculations — S&P 500 internals."""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


def compute_breadth(universe_data: dict) -> dict:
    """
    Compute market breadth metrics from S&P 500 universe data.

    Parameters:
        universe_data: dict of ticker -> OHLCV DataFrame

    Returns dict with breadth metrics, score, and thrust signal.
    """
    if not universe_data:
        return _empty_breadth()

    above_50_now = 0
    above_200_now = 0
    above_50_5ago = 0
    above_200_5ago = 0
    new_highs_20 = 0
    new_lows_20 = 0
    new_highs_50 = 0
    new_lows_50 = 0
    total = 0

    # For thrust detection: track recent pct_above_50 history
    daily_above_50_counts = {}

    for ticker, df in universe_data.items():
        if df is None or len(df) < 200:
            continue

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        if len(close) < 200:
            continue

        total += 1

        ma_50 = close.rolling(50).mean()
        ma_200 = close.rolling(200).mean()

        current_close = float(close.iloc[-1])
        current_ma50 = float(ma_50.iloc[-1])
        current_ma200 = float(ma_200.iloc[-1])

        # Current above MA
        if current_close > current_ma50:
            above_50_now += 1
        if current_close > current_ma200:
            above_200_now += 1

        # 5 days ago above MA
        if len(close) >= 6 and len(ma_50) >= 6:
            close_5ago = float(close.iloc[-6])
            ma50_5ago = float(ma_50.iloc[-6])
            ma200_5ago = float(ma_200.iloc[-6])
            if close_5ago > ma50_5ago:
                above_50_5ago += 1
            if close_5ago > ma200_5ago:
                above_200_5ago += 1

        # New highs/lows (20-day and 50-day)
        if len(high) >= 20:
            high_20 = float(high.iloc[-20:].max())
            low_20 = float(low.iloc[-20:].min())
            if current_close >= high_20:
                new_highs_20 += 1
            if current_close <= low_20:
                new_lows_20 += 1

        if len(high) >= 50:
            high_50 = float(high.iloc[-50:].max())
            low_50 = float(low.iloc[-50:].min())
            if current_close >= high_50:
                new_highs_50 += 1
            if current_close <= low_50:
                new_lows_50 += 1

        # Build daily above-50 history for thrust detection (last 15 days)
        if len(close) >= 65:  # need 50-day MA + 15 lookback
            for offset in range(15):
                idx = -(offset + 1)
                day_date = str(close.index[idx].date())
                c = float(close.iloc[idx])
                m = float(ma_50.iloc[idx])
                if day_date not in daily_above_50_counts:
                    daily_above_50_counts[day_date] = {"above": 0, "total": 0}
                daily_above_50_counts[day_date]["total"] += 1
                if c > m:
                    daily_above_50_counts[day_date]["above"] += 1

    if total == 0:
        return _empty_breadth()

    pct_above_50 = round(above_50_now / total * 100, 1)
    pct_above_200 = round(above_200_now / total * 100, 1)
    pct_above_50_5ago = round(above_50_5ago / total * 100, 1)
    pct_above_200_5ago = round(above_200_5ago / total * 100, 1)

    # Breadth momentum
    delta_50 = pct_above_50 - pct_above_50_5ago
    if delta_50 > 3:
        breadth_momentum = "EXPANDING"
    elif delta_50 < -3:
        breadth_momentum = "CONTRACTING"
    else:
        breadth_momentum = "STABLE"

    # Hi/lo ratio
    hi_lo_ratio = round(new_highs_50 / max(new_lows_50, 1), 2)

    # Breadth score composite
    score_50 = (pct_above_50 - 50) / 50 * 0.4
    score_200 = (pct_above_200 - 50) / 50 * 0.3
    score_hilo = max(-1, min(1, hi_lo_ratio - 1)) * 0.3
    breadth_score = round(max(-1.0, min(1.0, score_50 + score_200 + score_hilo)), 3)

    # Zweig Breadth Thrust analog: pct_above_50 went from <30 to >60 in 10 days
    thrust_signal = _check_thrust(daily_above_50_counts)

    return {
        "pct_above_50dma": pct_above_50,
        "pct_above_200dma": pct_above_200,
        "pct_above_50dma_5d_ago": pct_above_50_5ago,
        "pct_above_200dma_5d_ago": pct_above_200_5ago,
        "breadth_momentum": breadth_momentum,
        "new_highs_20d": new_highs_20,
        "new_lows_20d": new_lows_20,
        "new_highs_50d": new_highs_50,
        "new_lows_50d": new_lows_50,
        "hi_lo_ratio": hi_lo_ratio,
        "breadth_score": breadth_score,
        "thrust_signal": thrust_signal,
        "total_stocks": total,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _check_thrust(daily_counts: dict) -> bool:
    """Check if pct_above_50dma went from <30 to >60 within 10 trading days."""
    if len(daily_counts) < 10:
        return False

    sorted_dates = sorted(daily_counts.keys())
    pcts = []
    for d in sorted_dates:
        entry = daily_counts[d]
        if entry["total"] > 0:
            pcts.append(entry["above"] / entry["total"] * 100)

    # Check if any 10-day window shows <30 -> >60
    for i in range(len(pcts)):
        if pcts[i] < 30:
            for j in range(i + 1, min(i + 11, len(pcts))):
                if pcts[j] > 60:
                    return True
    return False


def _empty_breadth() -> dict:
    return {
        "pct_above_50dma": 0,
        "pct_above_200dma": 0,
        "pct_above_50dma_5d_ago": 0,
        "pct_above_200dma_5d_ago": 0,
        "breadth_momentum": "STABLE",
        "new_highs_20d": 0,
        "new_lows_20d": 0,
        "new_highs_50d": 0,
        "new_lows_50d": 0,
        "hi_lo_ratio": 0,
        "breadth_score": 0.0,
        "thrust_signal": False,
        "total_stocks": 0,
        "timestamp": datetime.utcnow().isoformat(),
    }
