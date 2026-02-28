"""Outcome tracker — forward price tracking + excursion analysis for scan results."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from modules.scanner.models import Outcome, ScanResult
from core.services import market_data

logger = logging.getLogger(__name__)

# Trading day milestones to track
MILESTONES = [1, 2, 3, 5, 10, 20]
MILESTONE_FIELDS = {
    1: "price_day_1",
    2: "price_day_2",
    3: "price_day_3",
    5: "price_day_5",
    10: "price_day_10",
    20: "price_day_20",
}


def create_outcomes_for_scan(db: Session, scan_results: list) -> int:
    """
    Create Outcome rows for new scan results that don't already have outcomes.
    Called automatically after each scan run.

    scan_results: list of result dicts from run_scan() (full hits only, not near misses).
    Returns count of outcomes created.
    """
    created = 0

    # Get regime context if available
    regime_label = None
    regime_score = None
    try:
        from modules.market_pulse.models import RegimeSnapshot
        latest = db.query(RegimeSnapshot).order_by(
            RegimeSnapshot.snapshot_date.desc()
        ).first()
        if latest:
            regime_label = latest.regime
            regime_score = latest.composite_score
    except Exception:
        pass  # Market Pulse module may not exist

    for r in scan_results:
        scan_result_id = r.get("id")
        if not scan_result_id:
            continue

        # Check for duplicate
        existing = db.query(Outcome).filter(
            Outcome.scan_result_id == scan_result_id
        ).first()
        if existing:
            continue

        outcome = Outcome(
            scan_result_id=scan_result_id,
            ticker=r["ticker"],
            entry_price=r.get("price", r.get("price_at_scan", 0)),
            entry_date=date.fromisoformat(r["scan_date"]) if isinstance(r["scan_date"], str) else r["scan_date"],
            strategy_id=r["strategy_id"],
            regime_at_scan=regime_label,
            regime_score_at_scan=regime_score,
            status="pending",
            days_tracked=0,
        )
        db.add(outcome)
        created += 1

    if created:
        db.commit()

    return created


def update_outcomes(db: Session, max_age_days: int = 25) -> dict:
    """
    Main tracking function. Fetches forward prices for all non-complete outcomes.

    For each outcome where status != "complete":
    1. Calculate trading days elapsed since entry_date
    2. Fetch price data and fill milestone prices
    3. Compute excursion metrics (MFE/MAE)
    4. Check theoretical stop/target hits
    5. Update status (partial/complete/error)

    Returns dict with updated, completed, errors, skipped counts.
    """
    stats = {"updated": 0, "completed": 0, "errors": 0, "skipped": 0}

    cutoff = date.today() - timedelta(days=max_age_days)
    outcomes = db.query(Outcome).filter(
        Outcome.status.notin_(["complete", "error"]),
        Outcome.entry_date >= cutoff,
    ).all()

    if not outcomes:
        return stats

    # Batch-fetch price data for all tickers we need
    tickers = list(set(o.ticker for o in outcomes))
    data = market_data.get_multiple(tickers)

    for outcome in outcomes:
        price_df = data.get(outcome.ticker)
        if price_df is None or price_df.empty:
            outcome.status = "error"
            outcome.updated_at = datetime.utcnow()
            stats["errors"] += 1
            continue

        try:
            _fill_outcome(outcome, price_df, db)
            stats["updated"] += 1
            if outcome.status == "complete":
                stats["completed"] += 1
        except Exception as e:
            logger.error(f"Failed to update outcome {outcome.id} ({outcome.ticker}): {e}")
            outcome.status = "error"
            stats["errors"] += 1

        outcome.updated_at = datetime.utcnow()

    db.commit()
    return stats


def _fill_outcome(outcome: Outcome, price_df: pd.DataFrame, db: Session) -> None:
    """Fill milestone prices, excursions, and stop/target checks for one outcome."""
    # Find entry date index in price data
    entry_date = outcome.entry_date
    if isinstance(entry_date, datetime):
        entry_date = entry_date.date()

    # Price data index is DatetimeIndex — normalize to dates for comparison
    dates = price_df.index.date if hasattr(price_df.index, 'date') else price_df.index
    date_list = list(dates)

    # Find the entry index (exact match or nearest prior)
    entry_idx = None
    for i, d in enumerate(date_list):
        if d <= entry_date:
            entry_idx = i
        elif d > entry_date:
            break

    if entry_idx is None:
        outcome.status = "error"
        return

    # Fill milestone prices
    milestone_prices = _get_trading_day_prices(price_df, entry_idx, MILESTONES)
    for day, price in milestone_prices.items():
        field = MILESTONE_FIELDS.get(day)
        if field and price is not None:
            setattr(outcome, field, price)

    # Count how many trading days we have after entry
    days_available = len(price_df) - entry_idx - 1
    outcome.days_tracked = min(days_available, 20)

    # Compute excursions (within first 10 trading days)
    excursions = _compute_excursions(outcome.entry_price, price_df, entry_idx, window=10)
    for key, val in excursions.items():
        if hasattr(outcome, key):
            setattr(outcome, key, val)

    # Check stop/target
    signal_data = {}
    scan_result = db.query(ScanResult).filter(ScanResult.id == outcome.scan_result_id).first()
    if scan_result and scan_result.signal_data:
        signal_data = scan_result.signal_data

    stop_target = _check_stop_target(
        outcome.entry_price, price_df, entry_idx, signal_data, window=20
    )
    for key, val in stop_target.items():
        if hasattr(outcome, key):
            setattr(outcome, key, val)

    # Determine status
    filled_milestones = sum(1 for d in MILESTONES if getattr(outcome, MILESTONE_FIELDS[d]) is not None)
    calendar_days = (date.today() - entry_date).days

    if filled_milestones == len(MILESTONES) or calendar_days >= 25:
        outcome.status = "complete"
    elif filled_milestones > 0:
        outcome.status = "partial"
    else:
        outcome.status = "pending"


def _get_trading_day_prices(
    price_df: pd.DataFrame,
    entry_idx: int,
    milestones: list,
) -> dict:
    """
    Extract closing prices at specific trading day offsets from entry.
    Trading days = rows in the DataFrame (yfinance excludes weekends/holidays).
    Returns dict: {1: price_or_None, 2: price_or_None, ...}
    """
    result = {}
    for day in milestones:
        target_idx = entry_idx + day
        if target_idx < len(price_df):
            result[day] = float(price_df["Close"].iloc[target_idx])
        else:
            result[day] = None
    return result


def _compute_excursions(
    entry_price: float,
    price_df: pd.DataFrame,
    entry_idx: int,
    window: int = 10,
) -> dict:
    """
    Compute max favorable and max adverse excursion within N trading days of entry.

    MFE = highest intraday high - entry_price
    MAE = entry_price - lowest intraday low

    Returns dict with max_favorable, max_favorable_pct, max_favorable_day,
    max_adverse, max_adverse_pct, max_adverse_day.
    """
    result = {
        "max_favorable": None, "max_favorable_pct": None, "max_favorable_day": None,
        "max_adverse": None, "max_adverse_pct": None, "max_adverse_day": None,
    }

    if entry_price <= 0:
        return result

    end_idx = min(entry_idx + window + 1, len(price_df))
    # Start from day after entry
    start_idx = entry_idx + 1

    if start_idx >= end_idx:
        return result

    window_df = price_df.iloc[start_idx:end_idx]

    if "High" in window_df.columns and not window_df["High"].empty:
        max_high = window_df["High"].max()
        max_high_idx = window_df["High"].idxmax()
        mfe = float(max_high - entry_price)
        result["max_favorable"] = round(mfe, 4)
        result["max_favorable_pct"] = round((mfe / entry_price) * 100, 2)
        # Day number relative to entry
        max_high_pos = list(window_df.index).index(max_high_idx) + 1
        result["max_favorable_day"] = max_high_pos

    if "Low" in window_df.columns and not window_df["Low"].empty:
        min_low = window_df["Low"].min()
        min_low_idx = window_df["Low"].idxmin()
        mae = float(entry_price - min_low)
        result["max_adverse"] = round(mae, 4)
        result["max_adverse_pct"] = round((mae / entry_price) * 100, 2)
        min_low_pos = list(window_df.index).index(min_low_idx) + 1
        result["max_adverse_day"] = min_low_pos

    return result


def _check_stop_target(
    entry_price: float,
    price_df: pd.DataFrame,
    entry_idx: int,
    signal_data: dict,
    window: int = 20,
) -> dict:
    """
    Check if theoretical stop loss or target would have been hit.

    Stop/target extraction from signal_data:
    - Look for explicit stop_loss/suggested_stop and target fields
    - Fallback: use ATR-based defaults (2*ATR stop, 3*ATR target)

    Conservative approach: if both stop and target hit on same day, assume stop hit first.
    """
    result = {
        "would_have_hit_target": None,
        "would_have_hit_stop": None,
        "target_hit_day": None,
        "stop_hit_day": None,
        "theoretical_r_multiple": None,
    }

    # Extract stop and target from signal_data
    stop_loss = signal_data.get("stop_loss") or signal_data.get("suggested_stop")
    target = signal_data.get("target") or signal_data.get("target_1")

    # ATR-based defaults
    atr = signal_data.get("atr_14") or signal_data.get("atr")
    if atr:
        atr = float(atr)
        if not stop_loss:
            # Trailing stop for trend following, otherwise 2*ATR
            trailing = signal_data.get("trailing_stop")
            if trailing:
                stop_loss = float(trailing)
            else:
                stop_loss = entry_price - 2 * atr
        if not target:
            target = entry_price + 3 * atr
    else:
        # No ATR available — can't compute
        if not stop_loss or not target:
            return result

    stop_loss = float(stop_loss)
    target = float(target)
    risk = entry_price - stop_loss

    if risk <= 0:
        return result

    end_idx = min(entry_idx + window + 1, len(price_df))
    start_idx = entry_idx + 1

    if start_idx >= end_idx:
        return result

    # Walk forward day by day
    for day_num, i in enumerate(range(start_idx, end_idx), start=1):
        row = price_df.iloc[i]
        day_low = float(row.get("Low", row.get("Close", 0)))
        day_high = float(row.get("High", row.get("Close", 0)))

        hit_stop = day_low <= stop_loss
        hit_target = day_high >= target

        if hit_stop and hit_target:
            # Both hit — conservative: assume stop hit first
            result["would_have_hit_stop"] = True
            result["stop_hit_day"] = day_num
            result["theoretical_r_multiple"] = -1.0
            break
        elif hit_stop:
            result["would_have_hit_stop"] = True
            result["stop_hit_day"] = day_num
            result["theoretical_r_multiple"] = -1.0
            break
        elif hit_target:
            result["would_have_hit_target"] = True
            result["target_hit_day"] = day_num
            result["theoretical_r_multiple"] = round((target - entry_price) / risk, 2)
            break

    # If neither hit, compute open trade R using day 10 close (or latest available)
    if result["would_have_hit_target"] is None and result["would_have_hit_stop"] is None:
        result["would_have_hit_target"] = False
        result["would_have_hit_stop"] = False
        # Use day 10 or latest
        ref_idx = min(entry_idx + 10, len(price_df) - 1)
        if ref_idx > entry_idx:
            ref_price = float(price_df["Close"].iloc[ref_idx])
            result["theoretical_r_multiple"] = round((ref_price - entry_price) / risk, 2)

    return result
