"""
EMA Pullback with Relative Strength strategy.

Core RDT setup:
- Stock above rising 50 and 200 DMA
- Pulling back to 8 or 21 EMA
- Relative strength vs SPY (stock gained more than SPY over lookback)
- Volume on pullback lighter than recent breakout volume
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from app.strategies.base import BaseStrategy, ScanHit


class EMAPullbackRS(BaseStrategy):

    id = "ema_pullback_rs"
    name = "EMA Pullback with Relative Strength"
    description = (
        "Finds stocks in uptrends (above rising 50/200 DMA) pulling back to the "
        "8 or 21 EMA with relative strength vs SPY and lighter pullback volume."
    )
    source = "r/RealDayTrading Wiki, Brian Shannon AVWAP"
    parameters = {
        "ema_fast": 8,
        "ema_slow": 21,
        "dma_mid": 50,
        "dma_long": 200,
        "rs_lookback": 10,
        "min_rs_ratio": 1.0,
        "proximity_pct": 0.02,   # within 2% of EMA to count as "at" it
        "volume_ratio": 0.8,     # pullback volume < 80% of 20-day avg
    }
    references = [
        "https://www.reddit.com/r/RealDayTrading/wiki/",
    ]

    def scan(self, universe: list, market_data: dict) -> list:
        """Run scan against universe. Expects market_data to include 'SPY' key."""
        hits = []
        spy_df = market_data.get("SPY")
        if spy_df is None or len(spy_df) < self.parameters["dma_long"]:
            return hits

        for ticker in universe:
            if ticker == "SPY":
                continue
            df = market_data.get(ticker)
            if df is None or len(df) < self.parameters["dma_long"]:
                continue

            hit = self._evaluate(ticker, df, spy_df)
            if hit is not None:
                hits.append(hit)

        return hits

    def _evaluate(self, ticker: str, df: pd.DataFrame, spy_df: pd.DataFrame) -> Optional[ScanHit]:
        """Check all criteria. Returns full hit, near-miss, or None."""
        p = self.parameters
        close = df["Close"]
        volume = df["Volume"]
        latest = float(close.iloc[-1])

        # ── Compute all indicators ──
        ema_fast = close.ewm(span=p["ema_fast"], adjust=False).mean()
        ema_slow = close.ewm(span=p["ema_slow"], adjust=False).mean()
        dma_mid = close.rolling(p["dma_mid"]).mean()
        dma_long = close.rolling(p["dma_long"]).mean()

        dma_mid_val = float(dma_mid.iloc[-1])
        dma_long_val = float(dma_long.iloc[-1])
        ema_fast_val = float(ema_fast.iloc[-1])
        ema_slow_val = float(ema_slow.iloc[-1])

        # ── Evaluate each filter ──
        failures = []

        # 1) Price above both DMAs
        above_dma = latest >= dma_mid_val and latest >= dma_long_val
        if not above_dma:
            failures.append("above_DMA")

        # 2) DMAs rising
        dma_rising = (
            float(dma_mid.iloc[-1]) > float(dma_mid.iloc[-6])
            and float(dma_long.iloc[-1]) > float(dma_long.iloc[-6])
        )
        if not dma_rising:
            failures.append("DMA_rising")

        # 3) Near EMA
        dist_fast = abs(latest - ema_fast_val) / latest
        dist_slow = abs(latest - ema_slow_val) / latest
        near_ema = dist_fast <= p["proximity_pct"] or dist_slow <= p["proximity_pct"]
        if not near_ema:
            failures.append("near_EMA")

        # 4) Relative strength
        lb = p["rs_lookback"]
        if len(close) < lb + 1 or len(spy_df) < lb + 1:
            return None  # not enough data — skip entirely

        stock_ret = (float(close.iloc[-1]) / float(close.iloc[-lb - 1])) - 1
        spy_close = spy_df["Close"]
        spy_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-lb - 1])) - 1

        if spy_ret == 0:
            rs_ratio = 999.0 if stock_ret > 0 else 0.0
        else:
            rs_ratio = stock_ret / spy_ret if spy_ret > 0 else stock_ret / abs(spy_ret)

        if rs_ratio < p["min_rs_ratio"]:
            failures.append("RS")

        # 5) Volume contraction
        avg_vol_20 = float(volume.iloc[-20:].mean())
        recent_vol = float(volume.iloc[-3:].mean())
        vol_ratio = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

        if vol_ratio > p["volume_ratio"]:
            failures.append("volume")

        # ── Decision: full hit, near miss, or skip ──
        if len(failures) > 1:
            return None  # too many failures, not interesting
        # len(failures) == 0 -> full hit, len(failures) == 1 -> near miss

        # ── Build signal data ──
        high = df["High"]
        low = df["Low"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_14 = float(tr.iloc[-14:].mean())
        swing_low = float(low.iloc[-10:].min())

        signal = {
            "rs_ratio": round(rs_ratio, 3),
            "stock_return_pct": round(stock_ret * 100, 2),
            "spy_return_pct": round(spy_ret * 100, 2),
            "ema_fast": round(ema_fast_val, 2),
            "ema_slow": round(ema_slow_val, 2),
            "dma_50": round(dma_mid_val, 2),
            "dma_200": round(dma_long_val, 2),
            "dist_to_ema8_pct": round(dist_fast * 100, 2),
            "dist_to_ema21_pct": round(dist_slow * 100, 2),
            "volume_ratio": round(vol_ratio, 3),
            "atr_14": round(atr_14, 2),
            "swing_low_10": round(swing_low, 2),
            "suggested_stop": round(swing_low - 0.10, 2),
        }

        is_near_miss = len(failures) == 1
        return ScanHit(
            ticker=ticker,
            price=round(latest, 2),
            signal_data=signal,
            near_miss=is_near_miss,
            failed_filter=failures[0] if is_near_miss else "",
        )

    def describe_signal(self, signal_data: dict) -> str:
        """Human-readable explanation."""
        return (
            f"RS ratio {signal_data.get('rs_ratio', '?')}x vs SPY "
            f"(stock {signal_data.get('stock_return_pct', '?')}% vs SPY {signal_data.get('spy_return_pct', '?')}%). "
            f"Near EMA8 ({signal_data.get('dist_to_ema8_pct', '?')}% away) / "
            f"EMA21 ({signal_data.get('dist_to_ema21_pct', '?')}% away). "
            f"Volume ratio {signal_data.get('volume_ratio', '?')} (lower = more contraction). "
            f"ATR(14): ${signal_data.get('atr_14', '?')}. "
            f"Suggested stop: ${signal_data.get('suggested_stop', '?')}"
        )
