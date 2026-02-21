"""Scanner endpoints — run scans, get results."""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScanResult
from app.services.scanner import run_scan

router = APIRouter(prefix="/api/scan", tags=["scanner"])


@router.post("/run")
def run_scanner(
    strategy_ids: Optional[List[str]] = None,
    db: Session = Depends(get_db),
):
    """Run all active strategies (or specified ones) against the universe."""
    scan_output = run_scan(db, strategy_ids=strategy_ids)
    results = scan_output["results"]
    near_misses = scan_output["near_misses"]
    return {
        "count": len(results),
        "results": results,
        "near_miss_count": len(near_misses),
        "near_misses": near_misses,
    }


@router.get("/results")
def get_results(
    scan_date: Optional[str] = None,
    strategy_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get scan results, optionally filtered by date and/or strategy."""
    query = db.query(ScanResult)

    if scan_date:
        query = query.filter(ScanResult.scan_date == date.fromisoformat(scan_date))
    if strategy_id:
        query = query.filter(ScanResult.strategy_id == strategy_id)

    query = query.order_by(ScanResult.scan_date.desc(), ScanResult.id.desc())
    rows = query.limit(200).all()

    return [
        {
            "id": r.id,
            "scan_date": r.scan_date.isoformat(),
            "strategy_id": r.strategy_id,
            "ticker": r.ticker,
            "price_at_scan": r.price_at_scan,
            "signal_data": r.signal_data,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/results/{result_id}")
def get_result_detail(result_id: int, db: Session = Depends(get_db)):
    """Get a single scan result by ID."""
    r = db.query(ScanResult).filter(ScanResult.id == result_id).first()
    if not r:
        return {"error": "Not found"}, 404
    return {
        "id": r.id,
        "scan_date": r.scan_date.isoformat(),
        "strategy_id": r.strategy_id,
        "ticker": r.ticker,
        "price_at_scan": r.price_at_scan,
        "signal_data": r.signal_data,
        "notes": r.notes,
    }
