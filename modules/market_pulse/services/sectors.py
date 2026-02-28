"""Sector ranking and rotation analysis."""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from modules.market_pulse.services.regime import classify_trend

logger = logging.getLogger(__name__)

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Healthcare",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLC": "Communications",
    "XLY": "Consumer Disc.",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
}


def compute_sector_rankings(data: dict) -> dict:
    """
    Rank sectors by momentum and classify rotation pattern.
    """
    spy_df = data.get("SPY")
    if spy_df is None or len(spy_df) < 63:
        return _empty_sectors()

    spy_close = spy_df["Close"]
    spy_ret_3m = _pct_return(spy_close, 63)

    rankings = []

    for ticker, name in SECTOR_ETFS.items():
        df = data.get(ticker)
        if df is None or len(df) < 63:
            continue

        close = df["Close"]

        ret_1w = _pct_return(close, 5)
        ret_1m = _pct_return(close, 21)
        ret_3m = _pct_return(close, 63)

        trend = classify_trend(df)

        # RS vs SPY: sector 3m return / SPY 3m return
        if spy_ret_3m != 0:
            rs_vs_spy = round(ret_3m / spy_ret_3m, 3) if spy_ret_3m != 0 else 1.0
        else:
            rs_vs_spy = 1.0

        # RS trend: 10-day slope of the RS ratio series
        rs_trend = _compute_rs_trend(close, spy_close)

        rankings.append({
            "ticker": ticker,
            "name": name,
            "return_1w": round(ret_1w, 2),
            "return_1m": round(ret_1m, 2),
            "return_3m": round(ret_3m, 2),
            "trend_score": trend["trend_score"],
            "rs_vs_spy": rs_vs_spy,
            "rs_trend": rs_trend,
        })

    if not rankings:
        return _empty_sectors()

    # Compute composite score using normalized ranks
    _add_composite_scores(rankings)

    # Sort by composite score descending
    rankings.sort(key=lambda x: x["composite_score"], reverse=True)

    leaders = [r["ticker"] for r in rankings[:3]]
    laggards = [r["ticker"] for r in rankings[-3:]]
    rotation_pattern = _classify_rotation(rankings)

    return {
        "rankings": rankings,
        "leaders": leaders,
        "laggards": laggards,
        "rotation_pattern": rotation_pattern,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _pct_return(series: pd.Series, days: int) -> float:
    """Compute percentage return over N days."""
    if len(series) < days + 1:
        return 0.0
    current = float(series.iloc[-1])
    past = float(series.iloc[-(days + 1)])
    if past == 0:
        return 0.0
    return (current - past) / past * 100


def _compute_rs_trend(sector_close: pd.Series, spy_close: pd.Series) -> str:
    """Compute RS trend direction over last 10 days."""
    combined = pd.DataFrame({"sector": sector_close, "spy": spy_close}).dropna()
    if len(combined) < 15:
        return "STABLE"

    rs_ratio = combined["sector"] / combined["spy"]
    rs_now = float(rs_ratio.iloc[-1])
    rs_10ago = float(rs_ratio.iloc[-11])

    if rs_10ago == 0:
        return "STABLE"

    slope = (rs_now - rs_10ago) / rs_10ago
    if slope > 0.005:
        return "IMPROVING"
    elif slope < -0.005:
        return "DECLINING"
    return "STABLE"


def _normalize(values: list) -> list:
    """Normalize list of values to 0-1 range."""
    if not values:
        return values
    mn = min(values)
    mx = max(values)
    rng = mx - mn
    if rng == 0:
        return [0.5] * len(values)
    return [(v - mn) / rng for v in values]


def _add_composite_scores(rankings: list) -> None:
    """Add composite_score to each ranking entry."""
    ret_1w = [r["return_1w"] for r in rankings]
    ret_1m = [r["return_1m"] for r in rankings]
    ret_3m = [r["return_3m"] for r in rankings]
    trends = [r["trend_score"] for r in rankings]

    n_1w = _normalize(ret_1w)
    n_1m = _normalize(ret_1m)
    n_3m = _normalize(ret_3m)
    n_tr = _normalize(trends)

    for i, r in enumerate(rankings):
        r["composite_score"] = round(
            0.2 * n_1w[i] + 0.3 * n_1m[i] + 0.3 * n_3m[i] + 0.2 * n_tr[i], 3
        )


def _classify_rotation(rankings: list) -> str:
    """Classify sector rotation pattern based on leader/laggard positions."""
    top4 = {r["ticker"] for r in rankings[:4]}
    bottom4 = {r["ticker"] for r in rankings[-4:]}

    # Early cycle: financials + industrials leading, utilities + staples lagging
    if {"XLF", "XLI"} & top4 and {"XLU", "XLP"} & bottom4:
        if len({"XLF", "XLI"} & top4) >= 1 and len({"XLU", "XLP"} & bottom4) >= 1:
            return "EARLY_CYCLE"

    # Mid cycle: tech + communications leading
    if {"XLK", "XLC"} & top4 and len({"XLK", "XLC"} & top4) >= 1:
        return "MID_CYCLE"

    # Defensive: utilities, staples, healthcare leading
    defensive_leaders = {"XLU", "XLP", "XLV"} & top4
    if len(defensive_leaders) >= 2:
        return "DEFENSIVE"

    # Late cycle: energy + materials leading
    if {"XLE", "XLB"} & top4 and len({"XLE", "XLB"} & top4) >= 1:
        if {"XLK", "XLF"} & bottom4:
            return "LATE_CYCLE"

    return "MIXED"


def _empty_sectors() -> dict:
    return {
        "rankings": [],
        "leaders": [],
        "laggards": [],
        "rotation_pattern": "MIXED",
        "timestamp": datetime.utcnow().isoformat(),
    }
