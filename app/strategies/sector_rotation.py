"""
Sector Relative Strength Rotation strategy.

1. Rank the 11 SPDR sector ETFs by relative strength vs SPY
2. Identify top N strongest sectors
3. Surface top RS stocks within those sectors
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.strategies.base import BaseStrategy, ScanHit
from app.services.universe import SECTOR_ETFS

logger = logging.getLogger(__name__)

# Map sector ETFs to representative S&P 500 stocks
# Built from SPDR holdings — top components per sector
SECTOR_STOCKS = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ADBE", "AMD", "CSCO", "ORCL", "ACN",
             "IBM", "INTU", "NOW", "QCOM", "TXN", "AMAT", "ADI", "LRCX", "KLAC", "SNPS"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "BLK",
             "AXP", "C", "SCHW", "MMC", "CB", "PGR", "ICE", "CME", "AON", "MET"],
    "XLE": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "PXD", "WMB",
             "OKE", "HAL", "HES", "DVN", "FANG", "OXY", "BKR", "TRGP", "KMI", "CTRA"],
    "XLV": ["UNH", "LLY", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN",
             "BMY", "ISRG", "SYK", "GILD", "MDT", "ELV", "VRTX", "CI", "BSX", "REGN"],
    "XLY": ["AMZN", "TSLA", "MCD", "HD", "NKE", "LOW", "BKNG", "SBUX", "TJX", "CMG",
             "ORLY", "MAR", "AZO", "ROST", "DHI", "GM", "F", "LEN", "ABNB", "YUM"],
    "XLP": ["PG", "COST", "KO", "PEP", "WMT", "PM", "MDLZ", "MO", "CL", "TGT",
             "KMB", "STZ", "SYY", "GIS", "ADM", "HSY", "KDP", "MKC", "CHD", "K"],
    "XLI": ["GE", "CAT", "RTX", "HON", "UPS", "UNP", "DE", "BA", "LMT", "ADP",
             "MMM", "GD", "WM", "CSX", "ITW", "NSC", "NOC", "EMR", "FDX", "ETN"],
    "XLU": ["NEE", "SO", "DUK", "SRE", "D", "AEP", "CEG", "EXC", "XEL", "PCG",
             "ED", "WEC", "AWK", "DTE", "ES", "PPL", "EIX", "FE", "ETR", "CMS"],
    "XLRE": ["PLD", "AMT", "EQIX", "CCI", "PSA", "SPG", "O", "WELL", "DLR", "VICI",
              "AVB", "EQR", "IRM", "SBAC", "WY", "ARE", "MAA", "ESS", "UDR", "KIM"],
    "XLB": ["LIN", "SHW", "APD", "FCX", "ECL", "NEM", "NUE", "DOW", "DD", "VMC",
             "MLM", "PPG", "IFF", "CTVA", "ALB", "CE", "EMN", "CF", "PKG", "IP"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX", "DIS", "CMCSA", "T", "VZ", "CHTR", "EA",
             "TMUS", "ATVI", "WBD", "TTWO", "OMC", "PARA", "IPG", "FOXA", "LYV", "MTCH"],
}


def _compute_rs(df: pd.DataFrame, spy_df: pd.DataFrame, lookback: int) -> float:
    """Compute relative strength ratio: stock return / SPY return over lookback."""
    if len(df) < lookback + 1 or len(spy_df) < lookback + 1:
        return 0.0
    stock_ret = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[-lookback - 1])) - 1
    spy_ret = (float(spy_df["Close"].iloc[-1]) / float(spy_df["Close"].iloc[-lookback - 1])) - 1
    if spy_ret == 0:
        return 999.0 if stock_ret > 0 else 0.0
    return stock_ret / spy_ret if spy_ret > 0 else stock_ret / abs(spy_ret)


class SectorRotation(BaseStrategy):

    id = "sector_rotation"
    name = "Sector Relative Strength Rotation"
    description = (
        "Ranks sectors by relative strength, then surfaces the strongest "
        "individual stocks within the top sectors."
    )
    source = "Sector rotation analysis, SPDR ETFs"
    parameters = {
        "sector_lookback": 20,      # days for sector RS ranking
        "stock_lookback": 10,       # days for individual stock RS
        "top_n_sectors": 3,         # how many top sectors to scan
        "top_n_stocks": 5,          # top stocks per sector to return
        "min_stock_rs": 1.0,        # minimum RS for individual stock
        "min_dma_200": True,        # stock must be above 200 DMA
    }
    references = [
        "SPDR Select Sector ETFs",
    ]

    def scan(self, universe: list, market_data: dict) -> list:
        """
        Two-phase scan:
        1. Rank sector ETFs by RS vs SPY
        2. Within top sectors, rank stocks by RS and return top performers
        """
        hits = []
        spy_df = market_data.get("SPY")
        if spy_df is None or len(spy_df) < 50:
            return hits

        p = self.parameters

        # Phase 1: Rank sectors
        sector_rs = {}
        for etf in SECTOR_ETFS:
            etf_df = market_data.get(etf)
            if etf_df is None or len(etf_df) < p["sector_lookback"] + 1:
                continue
            rs = _compute_rs(etf_df, spy_df, p["sector_lookback"])
            sector_rs[etf] = rs

        if not sector_rs:
            return hits

        # Sort sectors by RS, take top N
        sorted_sectors = sorted(sector_rs.items(), key=lambda x: x[1], reverse=True)
        top_sectors = sorted_sectors[:p["top_n_sectors"]]

        logger.info(f"Top sectors: {[(s, round(r, 2)) for s, r in top_sectors]}")

        # Phase 2: Within each top sector, find strongest stocks
        for etf, sector_rs_val in top_sectors:
            sector_name = SECTOR_ETFS.get(etf, etf)
            sector_stocks = SECTOR_STOCKS.get(etf, [])

            stock_scores = []
            for ticker in sector_stocks:
                df = market_data.get(ticker)
                if df is None or len(df) < 200:
                    continue

                close = df["Close"]
                latest = float(close.iloc[-1])

                # Optional: must be above 200 DMA
                if p["min_dma_200"]:
                    dma_200 = float(close.rolling(200).mean().iloc[-1])
                    if latest < dma_200:
                        continue

                rs = _compute_rs(df, spy_df, p["stock_lookback"])
                if rs < p["min_stock_rs"]:
                    continue

                stock_scores.append((ticker, rs, df))

            # Sort by RS, take top N
            stock_scores.sort(key=lambda x: x[1], reverse=True)
            top_stocks = stock_scores[:p["top_n_stocks"]]

            for ticker, rs, df in top_stocks:
                close = df["Close"]
                latest = float(close.iloc[-1])
                high = df["High"]
                low = df["Low"]

                # ATR
                tr = pd.concat([
                    high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs(),
                ], axis=1).max(axis=1)
                atr_14 = float(tr.iloc[-14:].mean())

                swing_low = float(low.iloc[-10:].min())
                dma_50 = float(close.rolling(50).mean().iloc[-1])
                dma_200 = float(close.rolling(200).mean().iloc[-1])

                stock_ret = (float(close.iloc[-1]) / float(close.iloc[-p["stock_lookback"] - 1])) - 1
                spy_ret = (float(spy_df["Close"].iloc[-1]) / float(spy_df["Close"].iloc[-p["stock_lookback"] - 1])) - 1

                signal = {
                    "sector": sector_name,
                    "sector_etf": etf,
                    "sector_rs": round(sector_rs_val, 3),
                    "sector_rank": [s for s, _ in top_sectors].index(etf) + 1,
                    "rs_ratio": round(rs, 3),
                    "stock_return_pct": round(stock_ret * 100, 2),
                    "spy_return_pct": round(spy_ret * 100, 2),
                    "dma_50": round(dma_50, 2),
                    "dma_200": round(dma_200, 2),
                    "atr_14": round(atr_14, 2),
                    "swing_low_10": round(swing_low, 2),
                    "suggested_stop": round(swing_low - 0.10, 2),
                }

                hits.append(ScanHit(ticker=ticker, price=round(latest, 2), signal_data=signal))

        return hits

    def describe_signal(self, signal_data: dict) -> str:
        """Human-readable explanation."""
        return (
            f"#{signal_data.get('sector_rank', '?')} sector {signal_data.get('sector', '?')} "
            f"({signal_data.get('sector_etf', '?')} RS {signal_data.get('sector_rs', '?')}x). "
            f"Stock RS {signal_data.get('rs_ratio', '?')}x vs SPY "
            f"({signal_data.get('stock_return_pct', '?')}% vs {signal_data.get('spy_return_pct', '?')}%). "
            f"Stop: ${signal_data.get('suggested_stop', '?')}"
        )
