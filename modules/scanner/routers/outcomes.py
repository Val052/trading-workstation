"""Outcome tracking + strategy analytics endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.database import get_db
from modules.scanner.models import Outcome
from modules.scanner.services.outcome_tracker import update_outcomes
from modules.scanner.services.strategy_analytics import (
    compute_strategy_stats,
    compute_edge_report,
    compute_ticker_outcomes,
)

router = APIRouter(tags=["scanner"])


@router.post("/outcomes/update")
def trigger_outcome_update(db: Session = Depends(get_db)):
    """Trigger forward price tracking update for all pending/partial outcomes."""
    stats = update_outcomes(db)
    return stats


@router.get("/outcomes")
def list_outcomes(
    strategy_id: Optional[str] = None,
    status: Optional[str] = None,
    days_back: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """List outcomes, optionally filtered."""
    from datetime import date, timedelta

    query = db.query(Outcome)
    cutoff = date.today() - timedelta(days=days_back)
    query = query.filter(Outcome.entry_date >= cutoff)

    if strategy_id:
        query = query.filter(Outcome.strategy_id == strategy_id)
    if status:
        query = query.filter(Outcome.status == status)

    query = query.order_by(Outcome.entry_date.desc())
    rows = query.limit(500).all()

    return [_outcome_to_dict(o) for o in rows]


@router.get("/outcomes/{outcome_id}")
def get_outcome(outcome_id: int, db: Session = Depends(get_db)):
    """Get a single outcome by ID."""
    o = db.query(Outcome).filter(Outcome.id == outcome_id).first()
    if not o:
        return {"error": "Not found"}
    return _outcome_to_dict(o)


@router.get("/analytics")
def get_analytics(
    strategy_id: Optional[str] = None,
    days_back: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Strategy performance stats."""
    return compute_strategy_stats(db, strategy_id=strategy_id, days_back=days_back)


@router.get("/analytics/edge")
def get_edge_report(
    days_back: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """System-level edge report."""
    return compute_edge_report(db, days_back=days_back)


@router.get("/analytics/ticker/{ticker}")
def get_ticker_outcomes(ticker: str, db: Session = Depends(get_db)):
    """Ticker outcome history."""
    return compute_ticker_outcomes(db, ticker.upper())


def _outcome_to_dict(o: Outcome) -> dict:
    """Convert Outcome ORM object to response dict."""
    day5_return = None
    day10_return = None
    if o.entry_price and o.entry_price > 0:
        if o.price_day_5 is not None:
            day5_return = round((o.price_day_5 - o.entry_price) / o.entry_price * 100, 2)
        if o.price_day_10 is not None:
            day10_return = round((o.price_day_10 - o.entry_price) / o.entry_price * 100, 2)

    return {
        "id": o.id,
        "scan_result_id": o.scan_result_id,
        "ticker": o.ticker,
        "strategy_id": o.strategy_id,
        "entry_price": o.entry_price,
        "entry_date": o.entry_date.isoformat() if o.entry_date else None,
        "price_day_1": o.price_day_1,
        "price_day_2": o.price_day_2,
        "price_day_3": o.price_day_3,
        "price_day_5": o.price_day_5,
        "price_day_10": o.price_day_10,
        "price_day_20": o.price_day_20,
        "day5_return_pct": day5_return,
        "day10_return_pct": day10_return,
        "max_favorable_pct": o.max_favorable_pct,
        "max_adverse_pct": o.max_adverse_pct,
        "max_favorable_day": o.max_favorable_day,
        "max_adverse_day": o.max_adverse_day,
        "would_have_hit_target": o.would_have_hit_target,
        "would_have_hit_stop": o.would_have_hit_stop,
        "target_hit_day": o.target_hit_day,
        "stop_hit_day": o.stop_hit_day,
        "theoretical_r_multiple": o.theoretical_r_multiple,
        "regime_at_scan": o.regime_at_scan,
        "status": o.status,
        "days_tracked": o.days_tracked,
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
    }
