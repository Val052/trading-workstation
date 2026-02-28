"""Weekly timeframe enrichment — adds multi-TF alignment to all scan results."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def enrich_with_weekly(results: list, data: dict) -> list:
    """
    Add weekly_context to each result's signal_data.

    Resamples daily data to weekly (no extra download needed) and computes
    trend alignment score for multi-timeframe confirmation.
    """
    spy_df = data.get("SPY")

    for result in results:
        ticker = result.get("ticker", "")
        df = data.get(ticker)
        if df is None or len(df) < 200:
            result["signal_data"]["weekly_context"] = _empty_context()
            continue

        try:
            weekly = _resample_to_weekly(df)
            if len(weekly) < 40:
                result["signal_data"]["weekly_context"] = _empty_context()
                continue

            context = _compute_weekly_context(weekly, spy_df)
            result["signal_data"]["weekly_context"] = context
        except Exception as e:
            logger.debug(f"Weekly enrichment failed for {ticker}: {e}")
            result["signal_data"]["weekly_context"] = _empty_context()

    return results


def _resample_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV to weekly bars (Friday close)."""
    return daily_df.resample("W-FRI").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()


def _compute_weekly_context(weekly: pd.DataFrame, spy_df: pd.DataFrame = None) -> dict:
    """Compute weekly trend alignment metrics."""
    close = weekly["Close"]
    high = weekly["High"]
    low = weekly["Low"]

    latest = float(close.iloc[-1])

    # 10-week and 40-week MAs (≈ 50 DMA and 200 DMA)
    ma_10w = close.rolling(10).mean()
    ma_40w = close.rolling(40).mean()

    ma_10w_val = float(ma_10w.iloc[-1])
    ma_40w_val = float(ma_40w.iloc[-1])

    above_10w = latest > ma_10w_val
    above_40w = latest > ma_40w_val
    weekly_golden = ma_10w_val > ma_40w_val

    # MA stack classification
    if weekly_golden and above_10w:
        weekly_ma_stack = "BULLISH"
    elif not weekly_golden and not above_10w:
        weekly_ma_stack = "BEARISH"
    elif weekly_golden and not above_10w:
        weekly_ma_stack = "CROSS_DOWN"
    else:
        weekly_ma_stack = "CROSS_UP"

    # Weekly RS trend (vs SPY)
    weekly_rs_trend = "STABLE"
    if spy_df is not None and len(spy_df) >= 200:
        spy_weekly = _resample_to_weekly(spy_df)
        if len(spy_weekly) >= 15:
            spy_close = spy_weekly["Close"]
            # RS ratio = stock weekly close / SPY weekly close
            combined = pd.DataFrame({
                "stock": close,
                "spy": spy_close,
            }).dropna()

            if len(combined) >= 15:
                rs_ratio = combined["stock"] / combined["spy"]
                rs_now = float(rs_ratio.iloc[-1])
                rs_10ago = float(rs_ratio.iloc[-11]) if len(rs_ratio) >= 11 else rs_now

                if rs_10ago > 0:
                    rs_slope = (rs_now - rs_10ago) / rs_10ago
                    if rs_slope > 0.005:
                        weekly_rs_trend = "IMPROVING"
                    elif rs_slope < -0.005:
                        weekly_rs_trend = "DECLINING"

    # Weekly close position in range (0 = at low, 1 = at high)
    recent_high = float(high.iloc[-10:].max())
    recent_low = float(low.iloc[-10:].min())
    rng = recent_high - recent_low
    close_position = (latest - recent_low) / rng if rng > 0 else 0.5

    # Weekly trend score (-2 to +2)
    score = 0
    if above_10w:
        score += 1
    else:
        score -= 1
    if above_40w:
        score += 1
    else:
        score -= 1
    if weekly_golden:
        score += 1
    else:
        score -= 1

    # Map -3..+3 to -2..+2
    weekly_trend_score = max(-2, min(2, score))

    # Alignment score (0-4, normalized to 0-1)
    alignment_points = 0
    if above_10w:
        alignment_points += 1
    if above_40w:
        alignment_points += 1
    if weekly_golden:
        alignment_points += 1
    if weekly_rs_trend == "IMPROVING":
        alignment_points += 1

    alignment_score = round(alignment_points / 4.0, 2)

    if alignment_score >= 0.75:
        alignment_label = "STRONG"
    elif alignment_score >= 0.50:
        alignment_label = "MODERATE"
    elif alignment_score >= 0.25:
        alignment_label = "WEAK"
    else:
        alignment_label = "CONFLICTING"

    return {
        "weekly_trend_score": weekly_trend_score,
        "above_10w_ma": above_10w,
        "above_40w_ma": above_40w,
        "weekly_ma_stack": weekly_ma_stack,
        "weekly_rs_trend": weekly_rs_trend,
        "weekly_close_position": round(close_position, 2),
        "alignment_score": alignment_score,
        "alignment_label": alignment_label,
    }


def _empty_context() -> dict:
    return {
        "weekly_trend_score": 0,
        "above_10w_ma": False,
        "above_40w_ma": False,
        "weekly_ma_stack": "BEARISH",
        "weekly_rs_trend": "STABLE",
        "weekly_close_position": 0.5,
        "alignment_score": 0.0,
        "alignment_label": "CONFLICTING",
    }
