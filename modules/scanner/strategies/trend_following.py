"""
Donchian Channel Trend Following strategy.

Philosophically different from pullback/mean-reversion strategies:
- Buys breakouts to new highs (not dips)
- Accepts lower win rate (35-45%) for asymmetric payoffs
- Uses ATR-based trailing stops to let winners run
- Requires consolidation before breakout (not just any new high)

Based on Turtle Traders / Donchian methodology, adapted for equity swing trading.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from modules.scanner.strategies.base import BaseStrategy, ScanHit


class TrendFollowingStrategy(BaseStrategy):

    id = "trend_following"
    name = "Donchian Trend Following"
    description = (
        "Donchian channel breakout with ATR trailing stop. "
        "Captures trending stocks making new highs with controlled risk. "
        "Accepts lower win rate for asymmetric reward."
    )
    source = "Donchian/Turtle Traders methodology, adapted for equity swing trading"
    parameters = {
        "donchian_period": 50,
        "donchian_entry_period": 20,
        "atr_period": 14,
        "atr_stop_multiple": 2.5,
        "min_atr_pct": 0.01,
        "max_atr_pct": 0.06,
        "volume_confirm_ratio": 1.2,
        "min_rs_ratio": 1.0,
        "lookback_days": 60,
        "require_consolidation": True,
    }
    references = [
        "Curtis Faith - Way of the Turtle",
        "Michael Covel - Trend Following",
        "JC Parets - intermarket trend analysis",
    ]

    def scan(self, universe: list, market_data: dict) -> list:
        hits = []
        spy_df = market_data.get("SPY")
        if spy_df is None or len(spy_df) < 200:
            return hits

        for ticker in universe:
            if ticker == "SPY":
                continue
            df = market_data.get(ticker)
            if df is None or len(df) < 200:
                continue

            hit = self._evaluate(ticker, df, spy_df)
            if hit is not None:
                hits.append(hit)

        return hits

    def _evaluate(self, ticker: str, df: pd.DataFrame, spy_df: pd.DataFrame) -> Optional[ScanHit]:
        p = self.parameters
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        latest_close = float(close.iloc[-1])
        latest_vol = float(volume.iloc[-1])

        # Donchian channels
        upper_50 = high.rolling(p["donchian_period"]).max()
        lower_50 = low.rolling(p["donchian_period"]).min()
        entry_channel = high.rolling(p["donchian_entry_period"]).max()

        upper_50_val = float(upper_50.iloc[-1])
        lower_50_val = float(lower_50.iloc[-1])
        # Entry channel shifted 1 day (yesterday's 20d high)
        entry_channel_val = float(entry_channel.iloc[-2])

        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(p["atr_period"]).mean()
        current_atr = float(atr.iloc[-1])
        atr_pct = current_atr / latest_close if latest_close > 0 else 0

        # Moving averages for trend alignment
        dma_50 = close.rolling(50).mean()
        dma_200 = close.rolling(200).mean()
        dma_50_val = float(dma_50.iloc[-1])
        dma_200_val = float(dma_200.iloc[-1])

        # Volume average
        avg_vol_20 = float(volume.iloc[-20:].mean()) if len(volume) >= 20 else 1.0
        vol_ratio = latest_vol / avg_vol_20 if avg_vol_20 > 0 else 0

        # RS vs SPY
        spy_close = spy_df["Close"]
        lb = 20
        stock_ret = (float(close.iloc[-1]) / float(close.iloc[-lb - 1])) - 1 if len(close) > lb else 0
        spy_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-lb - 1])) - 1 if len(spy_close) > lb else 0
        if spy_ret > 0:
            rs_ratio = stock_ret / spy_ret
        elif spy_ret < 0:
            rs_ratio = stock_ret / abs(spy_ret)
        else:
            rs_ratio = 999.0 if stock_ret > 0 else 0.0

        # Consolidation: count days below entry channel in last 20
        consol_days = 0
        if len(close) >= 20 and len(entry_channel) >= 20:
            for i in range(-20, -1):
                if float(close.iloc[i]) < float(entry_channel.iloc[i]):
                    consol_days += 1

        # ── Evaluate filters ──
        failures = []
        near_miss_eligible = []

        # 1. Breakout: close > yesterday's 20d high
        is_breakout = latest_close > entry_channel_val
        if not is_breakout:
            return None  # Hard requirement — no breakout = skip entirely

        # 2. Not extended: within 3% of entry channel
        extension = (latest_close - entry_channel_val) / entry_channel_val if entry_channel_val > 0 else 0
        if extension > 0.03:
            failures.append("extended")

        # 3. Consolidation: at least 5 of last 20 days below channel
        if p["require_consolidation"] and consol_days < 5:
            near_miss_eligible.append("consolidation")
            failures.append("consolidation")

        # 4. Volume confirmation
        if vol_ratio < p["volume_confirm_ratio"]:
            near_miss_eligible.append("volume")
            failures.append("volume")

        # 5. ATR range
        if atr_pct < p["min_atr_pct"] or atr_pct > p["max_atr_pct"]:
            failures.append("atr_range")

        # 6. Relative strength
        if rs_ratio < p["min_rs_ratio"]:
            if rs_ratio >= 0.9:
                near_miss_eligible.append("rs_ratio")
            failures.append("rs_ratio")

        # 7. Trend alignment: golden cross
        golden_cross = dma_50_val > dma_200_val
        if not golden_cross:
            failures.append("trend_alignment")

        # Decision
        if len(failures) > 1:
            return None

        # Determine breakout type
        breakout_type = "NEW_50D_HIGH" if latest_close >= upper_50_val else "NEW_20D_HIGH"

        trailing_stop = latest_close - (p["atr_stop_multiple"] * current_atr)
        stop_distance_pct = (p["atr_stop_multiple"] * current_atr) / latest_close if latest_close > 0 else 0
        channel_width_pct = (upper_50_val - lower_50_val) / latest_close if latest_close > 0 else 0

        signal = {
            "entry_price": round(latest_close, 2),
            "donchian_high_20": round(entry_channel_val, 2),
            "donchian_high_50": round(upper_50_val, 2),
            "donchian_low_50": round(lower_50_val, 2),
            "atr": round(current_atr, 2),
            "atr_pct": round(atr_pct, 4),
            "trailing_stop": round(trailing_stop, 2),
            "stop_distance_pct": round(stop_distance_pct, 4),
            "volume_ratio": round(vol_ratio, 3),
            "rs_vs_spy_20d": round(rs_ratio, 3),
            "consolidation_days": consol_days,
            "channel_width_pct": round(channel_width_pct, 4),
            "breakout_type": breakout_type,
            "dma_50": round(dma_50_val, 2),
            "dma_200": round(dma_200_val, 2),
        }

        is_near_miss = len(failures) == 1 and failures[0] in near_miss_eligible
        if len(failures) == 1 and not is_near_miss:
            return None  # Failed a hard filter, not eligible for near-miss

        return ScanHit(
            ticker=ticker,
            price=round(latest_close, 2),
            signal_data=signal,
            near_miss=is_near_miss,
            failed_filter=failures[0] if is_near_miss else "",
        )

    def describe_signal(self, signal_data: dict) -> str:
        bt = signal_data.get("breakout_type", "NEW_20D_HIGH")
        label = "New 50D High" if bt == "NEW_50D_HIGH" else "New 20D High"
        stop_pct = signal_data.get("stop_distance_pct", 0) * 100
        vol = signal_data.get("volume_ratio", 0)
        rs = signal_data.get("rs_vs_spy_20d", 0)
        return (
            f"{label} | ATR stop {stop_pct:.1f}% below entry | "
            f"Volume {vol:.1f}x average | RS vs SPY {rs:.2f}"
        )
