# Task: Build Market Pulse Module

## Context

This is a new module for the Trading Workstation project (`Val052/trading-workstation`). The project uses a modular architecture with:

- **Platform layer** in `core/` (database, shared services, UI shell)
- **Module system** in `modules/` (each module registers routes, models, UI panels)
- **BaseModule** ABC in `modules/base.py` defining the interface
- Existing modules: Scanner (`modules/scanner/`), Portfolio (`modules/portfolio/`)
- Database: SQLite via SQLAlchemy (`core/database.py`)
- Market data: yfinance with daily caching (`core/services/` or `app/services/market_data.py`)
- Frontend: Vanilla HTML/JS/CSS served by FastAPI, module panels in `core/ui/module_panels/`
- Python 3.9 on macOS — use `Optional[X]` not `X | None` in Pydantic models and FastAPI params
- `from __future__ import annotations` is safe in non-Pydantic files

The Market Pulse module provides the macro context layer that sits above all other modules. Its job is to answer: "What kind of market are we in right now?" before any individual stock analysis happens. This is inspired by JC Parets' "weight of the evidence" intermarket approach — you never look at a stock in isolation, you look at what the entire financial ecosystem is telling you.

## Architecture Overview

The module computes three layers that feed into each other:

1. **Intermarket Regime** — asset class ratios revealing capital flows
2. **Equity Internals** — breadth, sector rankings, style analysis
3. **Volatility & Positioning** — VIX term structure, put/call ratios

These produce a single **Regime Classification** (Risk-On / Risk-Off / Rotation) plus detailed breakdowns, all accessible via API and UI panel.

## File Structure to Create

```
modules/market_pulse/
  __init__.py              # MarketPulseModule class (BaseModule subclass)
  models.py                # SQLAlchemy models for regime history + snapshots
  routers/
    __init__.py
    pulse.py               # Main API endpoints
  services/
    __init__.py
    regime.py              # Intermarket regime computation engine
    breadth.py             # Equity breadth calculations
    sectors.py             # Sector ranking and rotation analysis
    volatility.py          # VIX term structure + put/call
    composite.py           # Combines all layers into final regime + score

core/ui/module_panels/
  market_pulse.html        # UI panel template
  market_pulse.js          # UI panel logic
```

## Data Layer

### Tickers to Track

All data fetched via the existing `market_data.get_multiple()` or `market_data.get_price_data()` functions (yfinance with SQLite caching).

**Equities (indices & style):**
- SPY, QQQ, IWM (US large/tech/small)
- EFA, EEM, FXI (international developed, emerging, China)
- IWF, IWD (growth vs value)

**Sector ETFs (SPDR S&P):**
- XLK, XLF, XLV, XLE, XLI, XLC, XLY, XLP, XLU, XLRE, XLB

**Fixed Income:**
- TLT (20yr+ treasuries), IEF (7-10yr), SHY (1-3yr)
- HYG (high yield corporate), LQD (investment grade corporate)
- TIP (TIPS / inflation-protected)

**Commodities:**
- GLD (gold), SLV (silver), USO (crude oil)
- DBC (broad commodity index), CPER (copper)

**Currencies:**
- UUP (US dollar index), FXE (euro), FXY (yen)

**Crypto:**
- BTC-USD, ETH-USD

**Volatility:**
- ^VIX (VIX index)
- ^VIX3M (3-month VIX, for term structure)

**Note:** yfinance can fetch ^VIX and ^VIX3M as index data. If ^VIX3M fails, fall back to VIXM ETF as a proxy.

### Intermarket Ratio Pairs

Each ratio is computed as price_A / price_B using daily close data. The trend of the ratio tells you the direction of capital flow.

| Ratio | Numerator | Denominator | What It Reveals | Risk-On Direction |
|-------|-----------|-------------|-----------------|-------------------|
| Stocks vs Bonds | SPY | TLT | Equity risk appetite | Ratio rising |
| Credit Stress | HYG | IEF | Credit market confidence | Ratio rising |
| Growth vs Value | IWF | IWD | Style preference | Ratio rising |
| Copper vs Gold | CPER | GLD | Real economy optimism | Ratio rising |
| Intl vs US | EFA | SPY | Global growth appetite | Ratio rising |
| Consumer Risk | XLY | XLP | Discretionary vs defensive | Ratio rising |
| Inflation Expectations | TIP | IEF | Real rate dynamics | Ratio rising |
| Speculative vs Defensive | BTC-USD | GLD | Risk appetite (extreme) | Ratio rising |

## Service Layer — Detailed Specifications

### 1. `services/regime.py` — Intermarket Regime Engine

#### Trend Classification Function

For any price series (individual asset or ratio), compute trend state:

```python
def classify_trend(df: pd.DataFrame, column: str = "Close") -> dict:
    """
    Classify trend using moving average framework.
    
    Returns dict with:
      - trend_score: int from -2 to +2
        +2 = Strong Uptrend (price > rising 50 DMA > rising 200 DMA)
        +1 = Uptrend (price > 50 DMA, 50 DMA > 200 DMA)
         0 = Neutral (mixed signals)
        -1 = Downtrend (price < 50 DMA, 50 DMA < 200 DMA)
        -2 = Strong Downtrend (price < falling 50 DMA < falling 200 DMA)
      - price: current price
      - dma_50: current 50 DMA value
      - dma_200: current 200 DMA value
      - dma_50_slope: 5-day rate of change of 50 DMA (positive = rising)
      - dma_200_slope: 5-day rate of change of 200 DMA
      - above_50: bool
      - above_200: bool
    """
```

**Slope calculation:** `slope = (ma_current - ma_5_days_ago) / ma_5_days_ago`

A moving average is "rising" if slope > 0.0005 (0.05%), "falling" if slope < -0.0005, "flat" otherwise.

**Scoring logic:**
- Price > 50 DMA: +1 point
- 50 DMA > 200 DMA (golden cross): +1 point  
- 50 DMA rising: +0.5 point
- 200 DMA rising: +0.5 point
- Map total to -2..+2 scale (mirror for negatives)

#### Ratio Computation

```python
def compute_ratio(data: dict, ticker_a: str, ticker_b: str) -> Optional[pd.DataFrame]:
    """
    Compute price ratio A/B as a synthetic series.
    Returns DataFrame with 'Close' column = ratio values.
    Returns None if either ticker is missing.
    """
```

Align dates using inner join before dividing.

#### Regime Classification

```python
def compute_regime(data: dict) -> dict:
    """
    Compute full intermarket regime analysis.
    
    Returns dict with:
      - regime: "RISK_ON" | "RISK_OFF" | "ROTATION"
      - regime_score: float from -1.0 to +1.0 
        (>0.3 = Risk-On, <-0.3 = Risk-Off, else Rotation)
      - ratios: dict of ratio_name -> {trend_score, ...classify_trend output}
      - assets: dict of ticker -> {trend_score, ...classify_trend output}
      - timestamp: ISO datetime string
    """
```

**Regime score:** Average all ratio trend_scores, normalize to [-1.0, +1.0] range.

**Classification thresholds:**
- Score > 0.30 -> RISK_ON
- Score < -0.30 -> RISK_OFF  
- Otherwise -> ROTATION

### 2. `services/breadth.py` — Equity Breadth

Uses the S&P 500 universe data that the scanner already downloads.

```python
def compute_breadth(universe_data: dict) -> dict:
    """
    Compute market breadth metrics from S&P 500 universe data.
    
    Parameters:
      universe_data: dict of ticker -> OHLCV DataFrame (from market_data.get_multiple)
    
    Returns dict with:
      - pct_above_50dma: float (0-100)
      - pct_above_200dma: float (0-100)
      - pct_above_50dma_5d_ago: float (for momentum calculation)
      - pct_above_200dma_5d_ago: float
      - breadth_momentum: "EXPANDING" | "CONTRACTING" | "STABLE"
        (EXPANDING if pct_above_50dma increased >3% in 5 days)
        (CONTRACTING if decreased >3%)
      - new_highs_20d: int (stocks at 20-day high)
      - new_lows_20d: int (stocks at 20-day low)
      - new_highs_50d: int
      - new_lows_50d: int
      - hi_lo_ratio: float (new_highs_50d / max(new_lows_50d, 1))
      - breadth_score: float (-1.0 to +1.0)
        Composite: weighted average of pct_above_50dma (normalized), 
        pct_above_200dma (normalized), hi_lo_ratio (normalized)
      - thrust_signal: bool 
        True if pct_above_50dma went from <30 to >60 within 10 trading days
        (Zweig Breadth Thrust analog — very rare, very bullish)
      - total_stocks: int (stocks with valid data)
      - timestamp: ISO datetime string
    """
```

**Breadth score calculation:**
- pct_above_50dma contribution: (pct - 50) / 50 * 0.4 (range -0.4 to +0.4)
- pct_above_200dma contribution: (pct - 50) / 50 * 0.3 (range -0.3 to +0.3)
- hi_lo_ratio contribution: clamp(ratio - 1, -1, 1) * 0.3 (range -0.3 to +0.3)

### 3. `services/sectors.py` — Sector Ranking & Rotation

```python
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
    
    Returns dict with:
      - rankings: list of dicts sorted by composite_score descending:
        [{
          ticker: str,
          name: str,
          composite_score: float,  # weighted momentum score
          return_1w: float,  # 1-week % return
          return_1m: float,  # 1-month % return  
          return_3m: float,  # 3-month % return
          trend_score: int,  # -2 to +2 from classify_trend
          rs_vs_spy: float,  # relative strength ratio vs SPY
          rs_trend: str,     # "IMPROVING" | "DECLINING" | "STABLE"
        }]
      - leaders: list[str]   # top 3 sector tickers
      - laggards: list[str]  # bottom 3 sector tickers
      - rotation_pattern: str  # "EARLY_CYCLE" | "MID_CYCLE" | "LATE_CYCLE" | "DEFENSIVE" | "MIXED"
      - timestamp: ISO datetime string
    """
```

**Composite score:** `0.2 * norm(return_1w) + 0.3 * norm(return_1m) + 0.3 * norm(return_3m) + 0.2 * norm(trend_score)`

Where `norm()` normalizes to 0-1 range within the sector group.

**RS vs SPY:** For each sector ETF, compute `sector_return_3m / spy_return_3m`. Values >1 = outperforming. Track the 10-day slope of this ratio to determine RS_TREND (IMPROVING if slope positive, DECLINING if negative).

**Rotation pattern classification:**
- EARLY_CYCLE: XLF and XLI in top 4, XLU and XLP in bottom 4
- MID_CYCLE: XLK and XLC in top 4, balanced otherwise
- LATE_CYCLE: XLE and XLB in top 4, XLK and XLF declining
- DEFENSIVE: XLU, XLP, XLV in top 4
- MIXED: no clear pattern matches

### 4. `services/volatility.py` — VIX Term Structure & Positioning

```python
def compute_volatility_regime(data: dict) -> dict:
    """
    Analyze volatility regime and options positioning.
    
    Parameters:
      data: must include ^VIX and ^VIX3M (or VIXM) DataFrames
    
    Returns dict with:
      - vix_level: float (current VIX close)
      - vix_zone: "LOW" (<15) | "NORMAL" (15-20) | "ELEVATED" (20-25) | 
                  "HIGH" (25-30) | "EXTREME" (>30)
      - vix_percentile: float (current VIX percentile over last 252 trading days)
      - vix3m_level: float
      - term_structure: "CONTANGO" | "FLAT" | "BACKWARDATION"
        CONTANGO: VIX3M > VIX * 1.02 (normal, complacent)
        FLAT: ratio between 0.98 and 1.02
        BACKWARDATION: VIX > VIX3M * 1.02 (panic, often marks bottoms)
      - term_structure_ratio: float (VIX / VIX3M, <1 = contango, >1 = backwardation)
      - vix_ma_50: float (50-day MA of VIX)
      - vix_trend: "RISING" | "FALLING" | "STABLE" (VIX vs its 50 DMA)
      - vol_regime_score: float (-1.0 to +1.0)
        Positive = low vol / complacent (supports risk-on but warns of complacency)
        Negative = high vol / fear (contrarian bullish if extreme)
      - contrarian_signal: Optional[str]
        "EXTREME_FEAR" if VIX > 30 AND backwardation (bullish contrarian)
        "EXTREME_COMPLACENCY" if VIX < 12 AND VIX percentile < 5 (bearish contrarian)
        None otherwise
      - timestamp: ISO datetime string
    """
```

**Vol regime score calculation:**
- VIX zone contribution: LOW=+0.3, NORMAL=+0.1, ELEVATED=-0.1, HIGH=-0.3, EXTREME=-0.5
- Term structure: CONTANGO=+0.2, FLAT=0, BACKWARDATION=-0.3
- VIX trend: FALLING=+0.2, STABLE=0, RISING=-0.2
- Sum and clamp to [-1.0, +1.0]

### 5. `services/composite.py` — Master Synthesis

```python
def compute_market_pulse(
    universe_data: Optional[dict] = None,
    force_refresh: bool = False,
) -> dict:
    """
    Run the full Market Pulse analysis.
    Fetches all required data, computes all layers, synthesizes regime.
    
    Optionally accepts pre-fetched universe_data for breadth 
    (so scanner doesn't have to download twice).
    
    Returns dict with:
      - regime: "RISK_ON" | "RISK_OFF" | "ROTATION"
      - regime_score: float (-1.0 to +1.0)
      - regime_description: str  # Human-readable 1-2 sentence summary
      - intermarket: dict  # Full output from regime.compute_regime()
      - breadth: dict      # Full output from breadth.compute_breadth()
      - sectors: dict      # Full output from sectors.compute_sector_rankings()
      - volatility: dict   # Full output from volatility.compute_volatility_regime()
      - signals: list[str] # Notable signals/warnings
      - scanner_context: dict  # Simplified context for scanner integration
      - timestamp: ISO datetime string
    """
```

**Master regime score** (overrides the intermarket-only score):
- `0.45 * intermarket_regime_score + 0.30 * breadth_score + 0.25 * vol_regime_score`
- Same thresholds: >0.30 = RISK_ON, <-0.30 = RISK_OFF, else ROTATION

## Models

### `modules/market_pulse/models.py`

```python
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Text, Float, Date, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    regime: Mapped[str] = mapped_column(String, nullable=False)
    regime_score: Mapped[float] = mapped_column(Float, nullable=False)
    regime_description: Mapped[str] = mapped_column(Text, default="")
    intermarket_score: Mapped[float] = mapped_column(Float, nullable=False)
    breadth_score: Mapped[float] = mapped_column(Float, nullable=False)
    volatility_score: Mapped[float] = mapped_column(Float, nullable=False)
    intermarket_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    breadth_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    sector_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    volatility_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    signals: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssetTrend(Base):
    __tablename__ = "asset_trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    trend_score: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dma_50: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dma_200: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

## API Endpoints

```
GET /api/market_pulse/current       # Latest snapshot (stale flag if old)
POST /api/market_pulse/refresh      # Run full computation, store + return
GET /api/market_pulse/history?days=30  # Regime history for charting
GET /api/market_pulse/sectors       # Current sector rankings
GET /api/market_pulse/assets?type=  # Asset trend scores by type
GET /api/market_pulse/context       # Simplified scanner context dict
```

## UI Panel

Sections (styled consistently with existing panels):

1. **Regime Header** — badge (RISK ON/OFF/ROTATION), score gauge, description, refresh button
2. **Intermarket Grid** — 8 ratio pairs with trend/score/direction, color-coded
3. **Breadth Dashboard** — % above MAs as gauges, momentum, hi/lo, thrust alert
4. **Sector Heatmap** — 11 sectors ranked, color gradient, rotation pattern label
5. **Volatility Panel** — VIX level/zone, term structure bar, percentile, contrarian alert
6. **Signals** — notable alerts sorted by importance

CSS grid layout: regime header full-width, intermarket+vol side-by-side, breadth+sectors side-by-side, signals at bottom.

## Scanner Integration

After scan results are computed, attach regime context from latest RegimeSnapshot. Display as header bar above scan results in the scanner UI.

## Configuration (add to settings.yaml)

```yaml
market_pulse:
  cache_hours: 4
  risk_on_threshold: 0.30
  risk_off_threshold: -0.30
  weights:
    intermarket: 0.45
    breadth: 0.30
    volatility: 0.25
  ratios:
    stocks_vs_bonds: ["SPY", "TLT"]
    credit_stress: ["HYG", "IEF"]
    growth_vs_value: ["IWF", "IWD"]
    copper_vs_gold: ["CPER", "GLD"]
    intl_vs_us: ["EFA", "SPY"]
    consumer_risk: ["XLY", "XLP"]
    inflation_expectations: ["TIP", "IEF"]
    speculative_vs_defensive: ["BTC-USD", "GLD"]
  tracked_assets:
    equity: ["QQQ", "IWM", "EEM", "FXI"]
    bond: ["SHY", "LQD"]
    commodity: ["SLV", "USO", "DBC"]
    currency: ["UUP", "FXE", "FXY"]
    crypto: ["ETH-USD"]
    volatility: ["^VIX", "^VIX3M"]
```

## Build Order

1. Models -> 2. Services (regime, breadth, sectors, volatility, composite) -> 3. Router -> 4. Module registration -> 5. UI panel -> 6. Scanner integration -> 7. Test

## Edge Cases

- Missing tickers: log warning, compute without. Never fail entire analysis.
- Weekend/holiday: use most recent trading day data.
- First run: return empty/null, not 500 errors.
- Stale data: include `stale` flag in GET responses.
- BTC-USD: handle hyphen in ticker names.

**DO NOT modify existing strategy files or scanner logic beyond adding the regime_context hook.**