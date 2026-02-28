# Task: Build Outcome Tracker Service + Strategy Analytics

## Context

The Outcome model already exists in `modules/scanner/models.py` with fields for forward price tracking (price_day_1/3/5/10, max_favorable, max_adverse, would_have_hit_target, would_have_hit_stop). The ScanResult model has a relationship to Outcome. But nothing populates this data.

This task builds the service that turns scan results into a strategy feedback loop: every scan hit gets tracked forward in time, and the results aggregate into strategy-level performance statistics. Without this, the scanner is a signal generator with no way to know if the signals have edge.

This is the poker equivalent of hand history tracking — you can't improve your game if you don't measure your results by situation type.

## Architecture

This lives entirely within the existing Scanner module — no new module needed.

```
modules/scanner/
  services/
    outcome_tracker.py     # NEW — forward price tracking + excursion analysis
    strategy_analytics.py  # NEW — aggregated strategy performance stats
  routers/
    outcomes.py            # NEW — API endpoints for outcomes + analytics

core/ui/module_panels/
  scanner.html             # UPDATE — add outcomes tab/section to existing panel
  scanner.js               # UPDATE — add outcomes UI logic
```

## Model Enhancement

The existing Outcome model needs a few additional fields. **Extend** the existing model in `modules/scanner/models.py`:

```python
class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_result_id: Mapped[int] = mapped_column(Integer, ForeignKey("scan_results.id"))
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    
    # Entry reference (from scan)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)  # NEW
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)     # NEW
    strategy_id: Mapped[str] = mapped_column(String, nullable=False)   # NEW — denormalized for easy queries
    
    # Forward prices (close on trading day N after scan)
    price_day_1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # NEW
    price_day_3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # NEW
    
    # Excursion analysis (within first 10 trading days)
    max_favorable: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_adverse: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_favorable_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # NEW
    max_adverse_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # NEW
    max_favorable_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # NEW
    max_adverse_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)     # NEW
    
    # Theoretical trade outcome (using scan's signal_data for stop/target)
    would_have_hit_target: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    would_have_hit_stop: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    target_hit_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # NEW
    stop_hit_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)        # NEW
    theoretical_r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # NEW
    
    # Regime context at time of scan (from Market Pulse if available)
    regime_at_scan: Mapped[Optional[str]] = mapped_column(String, nullable=True)       # NEW
    regime_score_at_scan: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # NEW
    
    # Tracking state
    status: Mapped[str] = mapped_column(String, default="pending")  # NEW
    days_tracked: Mapped[int] = mapped_column(Integer, default=0)   # NEW
    
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    scan_result: Mapped["ScanResult"] = relationship(back_populates="outcomes")
```

**IMPORTANT:** Since the table may already have rows from the old schema, use Alembic-style ALTER TABLE or just drop+recreate if no data exists yet. Check first: if the `outcomes` table has 0 rows, it's safe to drop and recreate. If it has data, add new columns with ALTER TABLE (all new columns are nullable so this is safe).

## Service 1: `services/outcome_tracker.py`

### Core Functions

```python
def create_outcomes_for_scan(db: Session, scan_results: list) -> int:
    """
    Create Outcome rows for new scan results that don't already have outcomes.
    Called automatically after each scan run.
    
    For each ScanResult:
    - Check if Outcome already exists (avoid duplicates)
    - Create Outcome with entry_price, entry_date, strategy_id from ScanResult
    - Copy regime context if available from scan results
    - Set status = "pending"
    
    Returns count of outcomes created.
    """


def update_outcomes(db: Session, max_age_days: int = 25) -> dict:
    """
    Main tracking function. Fetches forward prices for all non-complete outcomes.
    
    For each outcome where status != "complete":
    1. Calculate how many trading days have elapsed since entry_date
    2. Fetch price data from entry_date to now using market_data.get_price_data()
    3. Fill in price_day_N fields for each milestone that has passed
    4. Compute excursion metrics (max favorable/adverse within tracked window)
    5. Check theoretical stop/target hits using signal_data from parent ScanResult
    6. Update status:
       - "partial" if some but not all price_day fields are filled
       - "complete" if all fields through day_20 are filled (or 25 calendar days elapsed)
       - "error" if ticker data unavailable
    
    Parameters:
      max_age_days: stop tracking outcomes older than this (calendar days)
    
    Returns dict with:
      - updated: int (outcomes that got new data)
      - completed: int (outcomes that reached "complete" status)  
      - errors: int (outcomes where data fetch failed)
      - skipped: int (already complete)
    """


def _compute_excursions(
    entry_price: float, 
    price_data: pd.DataFrame,
    entry_idx: int,
    window: int = 10,
) -> dict:
    """
    Compute max favorable and max adverse excursion within N trading days of entry.
    
    MFE (Max Favorable Excursion) = highest intraday high - entry_price
    MAE (Max Adverse Excursion) = entry_price - lowest intraday low
    
    Returns dict with:
      max_favorable, max_favorable_pct, max_favorable_day,
      max_adverse, max_adverse_pct, max_adverse_day
    """


def _check_stop_target(
    entry_price: float,
    price_data: pd.DataFrame,
    entry_idx: int,
    signal_data: dict,
    window: int = 20,
) -> dict:
    """
    Check if theoretical stop loss or target would have been hit.
    
    Stop/target extraction from signal_data:
    - For EMA Pullback RS / AVWAP Bounce: look for "stop_loss" or compute from 
      entry - ATR * stop_multiple
    - For Trend Following: use "trailing_stop" from signal_data
    - For Sector Rotation: no predefined stop, use 2*ATR below entry as default
    
    Walk forward through price_data day by day:
    - If any day's low <= stop_loss: stop hit, record stop_hit_day
    - If any day's high >= target: target hit, record target_hit_day
    - If both, record whichever happened FIRST (check intraday: 
      if day's low hit stop AND high hit target, assume stop hit first 
      as conservative approach)
    
    Theoretical R-multiple:
    - If stop hit first: R = -1.0 (by definition)
    - If target hit first: R = (target - entry) / (entry - stop)
    - If neither: R = (price_day_10 - entry) / (entry - stop) [open trade R]
    
    Returns dict with:
      would_have_hit_target, would_have_hit_stop,
      target_hit_day, stop_hit_day, theoretical_r_multiple
    """
```

### Trading Day Calculation

```python
def _get_trading_day_prices(
    price_data: pd.DataFrame, 
    entry_date: date,
    milestones: list = [1, 2, 3, 5, 10, 20],
) -> dict:
    """
    Extract closing prices at specific trading day offsets from entry.
    
    Trading days = rows in the DataFrame (yfinance excludes weekends/holidays).
    Find the index of entry_date (or nearest prior date), then count forward.
    
    Returns dict: {1: price_or_None, 2: price_or_None, ...}
    Returns None for milestones that haven't occurred yet.
    """
```

### Integration with Scanner

After `run_scan()` in the scanner service, automatically create outcome rows:

```python
# In modules/scanner/services/scanner.py, at the end of run_scan():
from modules.scanner.services.outcome_tracker import create_outcomes_for_scan
outcomes_created = create_outcomes_for_scan(db, results)
logger.info(f"Created {outcomes_created} outcome tracking records")
```

## Service 2: `services/strategy_analytics.py`

This is the strategy report card. Aggregates outcome data into performance statistics.

```python
def compute_strategy_stats(
    db: Session,
    strategy_id: Optional[str] = None,
    days_back: int = 90,
    min_outcomes: int = 5,
) -> dict:
    """
    Compute performance statistics for one or all strategies.
    
    Returns dict with:
      - strategies: list of strategy stat dicts:
        [{
          strategy_id, strategy_name,
          total_scans, tracked_outcomes, complete_outcomes,
          win_rate, loss_rate, open_rate,
          avg_r_multiple, median_r_multiple, best_r, worst_r,
          expectancy,  # THE key number: (win_rate * avg_win_r) + (loss_rate * avg_loss_r)
          avg_return_day_1/3/5/10/20,
          avg_mfe_pct, avg_mae_pct, mfe_mae_ratio, avg_mfe_day, avg_mae_day,
          win_rate_risk_on, win_rate_risk_off, win_rate_rotation,
          confidence,  # "HIGH" (30+), "MODERATE" (15-29), "LOW" (5-14), "INSUFFICIENT" (<5)
          period_start, period_end,
        }]
      - overall: dict  # same structure aggregated across all strategies
      - timestamp: str
    """


def compute_ticker_outcomes(db: Session, ticker: str) -> dict:
    """
    All outcomes for a specific ticker across strategies.
    Returns: ticker, outcomes list, avg_return_day_5, times_scanned
    """


def compute_edge_report(db: Session, days_back: int = 90) -> dict:
    """
    Executive summary: does the system have edge?
    Returns:
      system_expectancy, total trades, winners, losers, system_win_rate,
      best/worst strategy,
      regime_impact: {risk_on/off/rotation expectancy, recommendation},
      sample_size_adequate (30+),
      verdict: "POSITIVE_EDGE" | "NO_EDGE" | "INSUFFICIENT_DATA"
    """
```

## Router: `modules/scanner/routers/outcomes.py`

```
POST /api/scanner/outcomes/update    — Trigger forward price tracking update
GET  /api/scanner/outcomes           — List outcomes (filter by strategy, status, days_back)
GET  /api/scanner/outcomes/{id}      — Single outcome detail
GET  /api/scanner/analytics          — Strategy performance stats
GET  /api/scanner/analytics/edge     — System-level edge report
GET  /api/scanner/analytics/ticker/{ticker} — Ticker outcome history
```

Register in `modules/scanner/__init__.py` alongside existing routers.

## UI Updates

Add "Outcomes" tab to scanner panel (NOT a separate module):

**1. Strategy Report Cards** — one per strategy, showing win rate, expectancy, R-multiple, MFE/MAE ratio, confidence badge. Green if expectancy > 0, red if < 0, gray if insufficient.

**2. Edge Summary** — system verdict badge, system expectancy (big number), win/loss/open stacked bar, regime breakdown.

**3. Outcome Table** — sortable: Date | Ticker | Strategy | Entry | Day 5 Return | Day 10 Return | MFE% | MAE% | R-Multiple | Status. Color-coded returns.

**4. Scanner Results Enhancement** — when viewing scan hits, show prior outcome indicator for previously-scanned tickers ("Scanned 3x, avg day-5 return +2.1%").

**5. Update Outcomes Button** — next to Run Scan button, calls POST /outcomes/update.

## Edge Cases

- **Weekend scans:** entry_date = most recent trading day, not scan date
- **Delisted tickers:** set status="error", don't fail other outcomes
- **Incomplete data:** fill what's available, status="partial", next update fills more
- **Duplicate prevention:** check scan_result_id before creating
- **Stop/target extraction:** strategy-aware logic (EMA uses signal_data stop, TF uses trailing_stop, Sector Rotation defaults to 2*ATR)
- **No signal_data:** default 2*ATR stop, 3*ATR target, log warning
- **Market Pulse regime:** populate if RegimeSnapshot exists for scan date, else null

## Testing Checklist

- [ ] Scan creates Outcome rows automatically
- [ ] Forward prices fill correctly on update
- [ ] MFE uses highs, MAE uses lows
- [ ] Stop/target check works per strategy type
- [ ] R-multiple negative for losses, positive for wins
- [ ] Analytics compute win rate, expectancy correctly
- [ ] Edge report verdict based on sample size + expectancy
- [ ] No divide-by-zero on insufficient data
- [ ] Duplicates prevented
- [ ] UI outcomes tab renders
- [ ] Prior outcome indicators show on scan results
- [ ] Regime correlation stats populate when Market Pulse data exists
