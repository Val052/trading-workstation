"""Intermarket regime engine — ratio analysis and trend classification."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Slope threshold: MA is "rising" if slope > 0.05%, "falling" if < -0.05%
SLOPE_THRESHOLD = 0.0005

# Ratio definitions: name -> (numerator_ticker, denominator_ticker, risk_on_direction)
RATIO_PAIRS = {
    "stocks_vs_bonds": ("SPY", "TLT"),
    "credit_stress": ("HYG", "IEF"),
    "growth_vs_value": ("IWF", "IWD"),
    "copper_vs_gold": ("CPER", "GLD"),
    "intl_vs_us": ("EFA", "SPY"),
    "consumer_risk": ("XLY", "XLP"),
    "inflation_expectations": ("TIP", "IEF"),
    "speculative_vs_defensive": ("BTC-USD", "GLD"),
}


def classify_trend(df: pd.DataFrame, column: str = "Close") -> dict:
    """
    Classify trend using moving average framework.

    Returns dict with trend_score (-2 to +2), price levels, MA values, slopes.
    """
    if df is None or len(df) < 200:
        return {
            "trend_score": 0,
            "price": None,
            "dma_50": None,
            "dma_200": None,
            "dma_50_slope": 0.0,
            "dma_200_slope": 0.0,
            "above_50": False,
            "above_200": False,
        }

    series = df[column].dropna()
    if len(series) < 200:
        return {
            "trend_score": 0,
            "price": float(series.iloc[-1]) if len(series) > 0 else None,
            "dma_50": None,
            "dma_200": None,
            "dma_50_slope": 0.0,
            "dma_200_slope": 0.0,
            "above_50": False,
            "above_200": False,
        }

    ma_50 = series.rolling(50).mean()
    ma_200 = series.rolling(200).mean()

    price = float(series.iloc[-1])
    dma_50 = float(ma_50.iloc[-1])
    dma_200 = float(ma_200.iloc[-1])

    # Slopes: 5-day rate of change of each MA
    dma_50_5ago = float(ma_50.iloc[-6]) if len(ma_50) >= 6 else dma_50
    dma_200_5ago = float(ma_200.iloc[-6]) if len(ma_200) >= 6 else dma_200

    dma_50_slope = (dma_50 - dma_50_5ago) / dma_50_5ago if dma_50_5ago != 0 else 0.0
    dma_200_slope = (dma_200 - dma_200_5ago) / dma_200_5ago if dma_200_5ago != 0 else 0.0

    above_50 = price > dma_50
    above_200 = price > dma_200
    golden_cross = dma_50 > dma_200
    ma_50_rising = dma_50_slope > SLOPE_THRESHOLD
    ma_200_rising = dma_200_slope > SLOPE_THRESHOLD
    ma_50_falling = dma_50_slope < -SLOPE_THRESHOLD
    ma_200_falling = dma_200_slope < -SLOPE_THRESHOLD

    # Score: accumulate points
    score = 0.0
    if above_50:
        score += 1.0
    else:
        score -= 1.0
    if golden_cross:
        score += 1.0
    else:
        score -= 1.0
    if ma_50_rising:
        score += 0.5
    elif ma_50_falling:
        score -= 0.5
    if ma_200_rising:
        score += 0.5
    elif ma_200_falling:
        score -= 0.5

    # Map to -2..+2 (max raw score is 3.0, min is -3.0)
    trend_score = max(-2, min(2, round(score * 2 / 3)))

    return {
        "trend_score": trend_score,
        "price": round(price, 2),
        "dma_50": round(dma_50, 2),
        "dma_200": round(dma_200, 2),
        "dma_50_slope": round(dma_50_slope, 6),
        "dma_200_slope": round(dma_200_slope, 6),
        "above_50": above_50,
        "above_200": above_200,
    }


def compute_ratio(data: dict, ticker_a: str, ticker_b: str) -> Optional[pd.DataFrame]:
    """
    Compute price ratio A/B as a synthetic series.
    Returns DataFrame with 'Close' column = ratio values, or None if missing data.
    """
    df_a = data.get(ticker_a)
    df_b = data.get(ticker_b)

    if df_a is None or df_b is None:
        return None

    close_a = df_a["Close"].dropna()
    close_b = df_b["Close"].dropna()

    # Align dates using inner join
    combined = pd.DataFrame({"a": close_a, "b": close_b}).dropna()
    if combined.empty or (combined["b"] == 0).any():
        return None

    ratio = combined["a"] / combined["b"]
    return pd.DataFrame({"Close": ratio}, index=combined.index)


def compute_regime(data: dict) -> dict:
    """
    Compute full intermarket regime analysis.

    Returns regime classification, ratio trends, and individual asset trends.
    """
    ratios_output = {}
    ratio_scores = []

    for name, (ticker_a, ticker_b) in RATIO_PAIRS.items():
        ratio_df = compute_ratio(data, ticker_a, ticker_b)
        if ratio_df is not None:
            trend = classify_trend(ratio_df)
            ratios_output[name] = {
                "pair": f"{ticker_a}/{ticker_b}",
                **trend,
            }
            ratio_scores.append(trend["trend_score"])
        else:
            logger.warning(f"Missing data for ratio {name}: {ticker_a}/{ticker_b}")
            ratios_output[name] = {
                "pair": f"{ticker_a}/{ticker_b}",
                "trend_score": 0,
                "price": None,
                "error": "missing_data",
            }

    # Regime score: average of ratio trend scores, normalized to [-1.0, +1.0]
    if ratio_scores:
        regime_score = sum(ratio_scores) / len(ratio_scores) / 2.0  # /2 normalizes from [-2,2] to [-1,1]
    else:
        regime_score = 0.0

    regime_score = max(-1.0, min(1.0, regime_score))

    # Classification
    if regime_score > 0.30:
        regime = "RISK_ON"
    elif regime_score < -0.30:
        regime = "RISK_OFF"
    else:
        regime = "ROTATION"

    # Individual asset trends
    assets_output = {}
    tracked_assets = {
        "equity": ["SPY", "QQQ", "IWM", "EFA", "EEM", "FXI"],
        "bond": ["TLT", "IEF", "SHY", "HYG", "LQD", "TIP"],
        "commodity": ["GLD", "SLV", "USO", "DBC", "CPER"],
        "currency": ["UUP", "FXE", "FXY"],
        "crypto": ["BTC-USD", "ETH-USD"],
    }

    for asset_type, tickers in tracked_assets.items():
        for ticker in tickers:
            if ticker in data:
                trend = classify_trend(data[ticker])
                assets_output[ticker] = {
                    "asset_type": asset_type,
                    **trend,
                }

    return {
        "regime": regime,
        "regime_score": round(regime_score, 3),
        "ratios": ratios_output,
        "assets": assets_output,
        "timestamp": datetime.utcnow().isoformat(),
    }
