"""VIX term structure and volatility regime analysis."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def compute_volatility_regime(data: dict) -> dict:
    """
    Analyze volatility regime using VIX level, term structure, and trend.
    """
    # Try ^VIX first, then VIX as fallback
    vix_df = data.get("^VIX")
    if vix_df is None:
        vix_df = data.get("VIX")
    vix3m_df = data.get("^VIX3M")
    if vix3m_df is None:
        vix3m_df = data.get("VIXM")

    if vix_df is None or len(vix_df) < 50:
        return _empty_volatility()

    vix_close = vix_df["Close"]
    vix_level = round(float(vix_close.iloc[-1]), 2)

    # VIX zone
    vix_zone = _classify_vix_zone(vix_level)

    # VIX percentile over last 252 trading days
    lookback = min(252, len(vix_close))
    recent_vix = vix_close.iloc[-lookback:]
    vix_percentile = round(float((recent_vix < vix_level).sum() / len(recent_vix) * 100), 1)

    # 50-day MA of VIX
    vix_ma_50 = round(float(vix_close.rolling(50).mean().iloc[-1]), 2)

    # VIX trend vs its 50 DMA
    if vix_level > vix_ma_50 * 1.05:
        vix_trend = "RISING"
    elif vix_level < vix_ma_50 * 0.95:
        vix_trend = "FALLING"
    else:
        vix_trend = "STABLE"

    # Term structure
    vix3m_level = None
    term_structure = "FLAT"
    term_structure_ratio = 1.0

    if vix3m_df is not None and len(vix3m_df) > 0:
        vix3m_close = vix3m_df["Close"]
        vix3m_level = round(float(vix3m_close.iloc[-1]), 2)

        if vix3m_level > 0:
            term_structure_ratio = round(vix_level / vix3m_level, 3)

            if term_structure_ratio < 0.98:
                term_structure = "CONTANGO"
            elif term_structure_ratio > 1.02:
                term_structure = "BACKWARDATION"
            else:
                term_structure = "FLAT"

    # Vol regime score
    zone_scores = {"LOW": 0.3, "NORMAL": 0.1, "ELEVATED": -0.1, "HIGH": -0.3, "EXTREME": -0.5}
    ts_scores = {"CONTANGO": 0.2, "FLAT": 0.0, "BACKWARDATION": -0.3}
    trend_scores = {"FALLING": 0.2, "STABLE": 0.0, "RISING": -0.2}

    vol_score = zone_scores.get(vix_zone, 0) + ts_scores.get(term_structure, 0) + trend_scores.get(vix_trend, 0)
    vol_regime_score = round(max(-1.0, min(1.0, vol_score)), 3)

    # Contrarian signals
    contrarian_signal = None
    if vix_level > 30 and term_structure == "BACKWARDATION":
        contrarian_signal = "EXTREME_FEAR"
    elif vix_level < 12 and vix_percentile < 5:
        contrarian_signal = "EXTREME_COMPLACENCY"

    return {
        "vix_level": vix_level,
        "vix_zone": vix_zone,
        "vix_percentile": vix_percentile,
        "vix3m_level": vix3m_level,
        "term_structure": term_structure,
        "term_structure_ratio": term_structure_ratio,
        "vix_ma_50": vix_ma_50,
        "vix_trend": vix_trend,
        "vol_regime_score": vol_regime_score,
        "contrarian_signal": contrarian_signal,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _classify_vix_zone(level: float) -> str:
    if level < 15:
        return "LOW"
    elif level < 20:
        return "NORMAL"
    elif level < 25:
        return "ELEVATED"
    elif level < 30:
        return "HIGH"
    return "EXTREME"


def _empty_volatility() -> dict:
    return {
        "vix_level": None,
        "vix_zone": "NORMAL",
        "vix_percentile": 50.0,
        "vix3m_level": None,
        "term_structure": "FLAT",
        "term_structure_ratio": 1.0,
        "vix_ma_50": None,
        "vix_trend": "STABLE",
        "vol_regime_score": 0.0,
        "contrarian_signal": None,
        "timestamp": datetime.utcnow().isoformat(),
    }
