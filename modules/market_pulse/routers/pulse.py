"""Market Pulse API endpoints."""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.database import get_db
from modules.market_pulse.models import RegimeSnapshot, AssetTrend
from modules.market_pulse.services.composite import compute_market_pulse

router = APIRouter()


@router.get("/current")
def get_current(db: Session = Depends(get_db)):
    """Get latest regime snapshot. Includes stale flag if older than cache_hours."""
    latest = (
        db.query(RegimeSnapshot)
        .order_by(RegimeSnapshot.snapshot_date.desc(), RegimeSnapshot.id.desc())
        .first()
    )

    if latest is None:
        return {"data": None, "stale": True, "message": "No data yet. Hit refresh to run first analysis."}

    # Check staleness (4 hours default)
    age = datetime.utcnow() - latest.created_at
    stale = age > timedelta(hours=4)

    return {
        "data": _snapshot_to_dict(latest),
        "stale": stale,
        "age_hours": round(age.total_seconds() / 3600, 1),
    }


@router.post("/refresh")
def refresh_pulse(db: Session = Depends(get_db)):
    """Run full Market Pulse computation, store and return."""
    result = compute_market_pulse()

    # Store snapshot
    snapshot = RegimeSnapshot(
        snapshot_date=date.today(),
        regime=result["regime"],
        regime_score=result["regime_score"],
        regime_description=result["regime_description"],
        intermarket_score=result["intermarket"]["regime_score"],
        breadth_score=result["breadth"]["breadth_score"],
        volatility_score=result["volatility"]["vol_regime_score"],
        intermarket_data=result["intermarket"],
        breadth_data=result["breadth"],
        sector_data=result["sectors"],
        volatility_data=result["volatility"],
        signals=result["signals"],
    )
    db.add(snapshot)

    # Store asset trends
    for symbol, asset_data in result["intermarket"].get("assets", {}).items():
        trend = AssetTrend(
            snapshot_date=date.today(),
            symbol=symbol,
            asset_type=asset_data.get("asset_type", "unknown"),
            trend_score=asset_data.get("trend_score", 0),
            price=asset_data.get("price"),
            dma_50=asset_data.get("dma_50"),
            dma_200=asset_data.get("dma_200"),
            detail=asset_data,
        )
        db.add(trend)

    db.commit()

    return {
        "data": _snapshot_to_dict(snapshot),
        "stale": False,
        "age_hours": 0,
    }


@router.get("/history")
def get_history(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get regime history for charting."""
    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(RegimeSnapshot)
        .filter(RegimeSnapshot.snapshot_date >= cutoff)
        .order_by(RegimeSnapshot.snapshot_date.asc())
        .all()
    )
    return [
        {
            "date": r.snapshot_date.isoformat(),
            "regime": r.regime,
            "regime_score": r.regime_score,
            "intermarket_score": r.intermarket_score,
            "breadth_score": r.breadth_score,
            "volatility_score": r.volatility_score,
        }
        for r in rows
    ]


@router.get("/sectors")
def get_sectors(db: Session = Depends(get_db)):
    """Get current sector rankings from latest snapshot."""
    latest = (
        db.query(RegimeSnapshot)
        .order_by(RegimeSnapshot.snapshot_date.desc(), RegimeSnapshot.id.desc())
        .first()
    )
    if latest is None or latest.sector_data is None:
        return {"data": None, "message": "No sector data. Run refresh first."}
    return {"data": latest.sector_data}


@router.get("/assets")
def get_assets(
    asset_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Get asset trend scores, optionally filtered by type."""
    query = (
        db.query(AssetTrend)
        .filter(AssetTrend.snapshot_date == date.today())
    )
    if asset_type:
        query = query.filter(AssetTrend.asset_type == asset_type)

    rows = query.order_by(AssetTrend.trend_score.desc()).all()
    return [
        {
            "symbol": r.symbol,
            "asset_type": r.asset_type,
            "trend_score": r.trend_score,
            "price": r.price,
            "dma_50": r.dma_50,
            "dma_200": r.dma_200,
        }
        for r in rows
    ]


@router.get("/context")
def get_context(db: Session = Depends(get_db)):
    """Simplified scanner context dict."""
    latest = (
        db.query(RegimeSnapshot)
        .order_by(RegimeSnapshot.snapshot_date.desc(), RegimeSnapshot.id.desc())
        .first()
    )
    if latest is None:
        return {"regime": "UNKNOWN", "stale": True}

    sector_data = latest.sector_data or {}
    breadth_data = latest.breadth_data or {}
    vol_data = latest.volatility_data or {}

    return {
        "regime": latest.regime,
        "regime_score": latest.regime_score,
        "vix_zone": vol_data.get("vix_zone", "NORMAL"),
        "breadth_momentum": breadth_data.get("breadth_momentum", "STABLE"),
        "rotation_pattern": sector_data.get("rotation_pattern", "MIXED"),
        "leaders": sector_data.get("leaders", []),
        "laggards": sector_data.get("laggards", []),
        "stale": False,
    }


def _snapshot_to_dict(s: RegimeSnapshot) -> dict:
    return {
        "id": s.id,
        "snapshot_date": s.snapshot_date.isoformat(),
        "regime": s.regime,
        "regime_score": s.regime_score,
        "regime_description": s.regime_description,
        "intermarket_score": s.intermarket_score,
        "breadth_score": s.breadth_score,
        "volatility_score": s.volatility_score,
        "intermarket_data": s.intermarket_data,
        "breadth_data": s.breadth_data,
        "sector_data": s.sector_data,
        "volatility_data": s.volatility_data,
        "signals": s.signals,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
