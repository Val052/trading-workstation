"""Portfolio CRUD + enrichment + analytics endpoints."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db, SessionLocal
from core.models.instruments import Instrument
from core.services.instrument_registry import resolve_instrument
from core.services.event_log import log_event
from modules.portfolio.models import PortfolioHolding, PortfolioSnapshot
from modules.portfolio.services.enrichment import (
    enrich_holding,
    enrich_holdings_parallel,
    compute_portfolio_summary,
)

router = APIRouter(tags=["portfolio"])


# ── Pydantic models ──

class AddHoldingRequest(BaseModel):
    instrument_input: str        # ticker or ISIN
    shares: float
    cost_basis: float
    cost_basis_currency: str = "EUR"
    account_label: str = "default"
    asset_class: str = "equity"  # equity, etf, fixed_income, cash_equivalent, real_estate
    instrument_type: Optional[str] = None  # override for non-marketable
    name: Optional[str] = None   # manual name for non-marketable
    date_acquired: Optional[str] = None
    notes: str = ""


class UpdateHoldingRequest(BaseModel):
    shares: Optional[float] = None
    cost_basis: Optional[float] = None
    cost_basis_currency: Optional[str] = None
    account_label: Optional[str] = None
    asset_class: Optional[str] = None
    date_acquired: Optional[str] = None
    notes: Optional[str] = None


# ── Endpoints ──

@router.get("/holdings")
def list_holdings(
    enrich: bool = False,
    db: Session = Depends(get_db),
):
    """List all active holdings. Set enrich=true for live price data (slow)."""
    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.is_active == True)
        .order_by(PortfolioHolding.id)
        .all()
    )

    if not enrich:
        # Fast path: return holdings with instrument info only
        instrument_ids = [h.instrument_id for h in holdings]
        instruments = db.query(Instrument).filter(Instrument.id.in_(instrument_ids)).all()
        inst_map = {i.id: i for i in instruments}

        return [
            {
                "id": h.id,
                "instrument_id": h.instrument_id,
                "name": inst_map[h.instrument_id].name if h.instrument_id in inst_map else h.instrument_id,
                "ticker": inst_map[h.instrument_id].ticker if h.instrument_id in inst_map else h.instrument_id,
                "shares": h.shares,
                "cost_basis": h.cost_basis,
                "cost_basis_currency": h.cost_basis_currency,
                "date_acquired": h.date_acquired.isoformat() if h.date_acquired else None,
                "account_label": h.account_label,
                "asset_class": h.asset_class,
                "notes": h.notes,
                "sector": inst_map[h.instrument_id].sector if h.instrument_id in inst_map else None,
            }
            for h in holdings
        ]

    # Enriched path: fetch live data
    instrument_ids = [h.instrument_id for h in holdings]
    instruments = db.query(Instrument).filter(Instrument.id.in_(instrument_ids)).all()
    inst_map = {i.id: i for i in instruments}

    return enrich_holdings_parallel(holdings, inst_map)


@router.post("/holdings")
def add_holding(req: AddHoldingRequest, db: Session = Depends(get_db)):
    """Add a new holding. Resolves instrument_input to canonical instrument."""
    # Determine instrument type
    inst_type = req.instrument_type or req.asset_class
    if inst_type in ("cash_equivalent", "real_estate"):
        instrument = resolve_instrument(
            req.instrument_input,
            instrument_type=inst_type,
            name=req.name,
            currency=req.cost_basis_currency,
        )
    else:
        instrument = resolve_instrument(
            req.instrument_input,
            instrument_type=inst_type if inst_type in ("equity", "etf", "index") else "equity",
            name=req.name,
        )

    holding = PortfolioHolding(
        instrument_id=instrument.id,
        shares=req.shares,
        cost_basis=req.cost_basis,
        cost_basis_currency=req.cost_basis_currency,
        date_acquired=date.fromisoformat(req.date_acquired) if req.date_acquired else None,
        account_label=req.account_label,
        asset_class=req.asset_class,
        notes=req.notes,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)

    log_event(
        module="portfolio",
        event_type="holding_added",
        instrument_id=instrument.id,
        data={
            "shares": req.shares,
            "cost_basis": req.cost_basis,
            "account": req.account_label,
        },
    )

    return {
        "id": holding.id,
        "instrument_id": instrument.id,
        "name": instrument.name,
        "ticker": instrument.ticker,
    }


@router.put("/holdings/{holding_id}")
def update_holding(
    holding_id: int,
    req: UpdateHoldingRequest,
    db: Session = Depends(get_db),
):
    """Update an existing holding."""
    holding = db.query(PortfolioHolding).filter(PortfolioHolding.id == holding_id).first()
    if not holding:
        return {"error": "Holding not found"}

    if req.shares is not None:
        holding.shares = req.shares
    if req.cost_basis is not None:
        holding.cost_basis = req.cost_basis
    if req.cost_basis_currency is not None:
        holding.cost_basis_currency = req.cost_basis_currency
    if req.account_label is not None:
        holding.account_label = req.account_label
    if req.asset_class is not None:
        holding.asset_class = req.asset_class
    if req.date_acquired is not None:
        holding.date_acquired = date.fromisoformat(req.date_acquired)
    if req.notes is not None:
        holding.notes = req.notes

    db.commit()
    return {"id": holding.id, "status": "updated"}


@router.delete("/holdings/{holding_id}")
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    """Soft-delete a holding (set is_active=false)."""
    holding = db.query(PortfolioHolding).filter(PortfolioHolding.id == holding_id).first()
    if not holding:
        return {"error": "Holding not found"}

    holding.is_active = False
    db.commit()

    log_event(
        module="portfolio",
        event_type="holding_removed",
        instrument_id=holding.instrument_id,
        data={"shares": holding.shares},
    )

    return {"id": holding.id, "status": "deactivated"}


@router.get("/summary")
def portfolio_summary(db: Session = Depends(get_db)):
    """Portfolio-level analytics with full enrichment."""
    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.is_active == True)
        .all()
    )

    if not holdings:
        return {
            "total_value": 0,
            "total_cost": 0,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "holdings_count": 0,
            "allocation": {},
            "concentration": {},
            "breadth": {},
        }

    instrument_ids = [h.instrument_id for h in holdings]
    instruments = db.query(Instrument).filter(Instrument.id.in_(instrument_ids)).all()
    inst_map = {i.id: i for i in instruments}

    enriched = enrich_holdings_parallel(holdings, inst_map)
    return compute_portfolio_summary(enriched)


@router.post("/snapshot")
def take_snapshot(db: Session = Depends(get_db)):
    """Save current portfolio state as a point-in-time snapshot."""
    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.is_active == True)
        .all()
    )

    instrument_ids = [h.instrument_id for h in holdings]
    instruments = db.query(Instrument).filter(Instrument.id.in_(instrument_ids)).all()
    inst_map = {i.id: i for i in instruments}

    enriched = enrich_holdings_parallel(holdings, inst_map)
    summary = compute_portfolio_summary(enriched)

    snapshot = PortfolioSnapshot(
        snapshot_date=date.today(),
        total_value=summary["total_value"],
        total_cost=summary["total_cost"],
        total_pnl=summary["total_pnl"],
        allocation_data=summary["allocation"],
        metrics_data={
            "concentration": summary["concentration"],
            "breadth": summary["breadth"],
        },
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    log_event(
        module="portfolio",
        event_type="snapshot_taken",
        data={
            "total_value": summary["total_value"],
            "total_pnl": summary["total_pnl"],
        },
    )

    return {
        "id": snapshot.id,
        "snapshot_date": snapshot.snapshot_date.isoformat(),
        "total_value": snapshot.total_value,
        "total_pnl": snapshot.total_pnl,
    }


@router.get("/snapshots")
def list_snapshots(db: Session = Depends(get_db)):
    """List historical snapshots."""
    snapshots = (
        db.query(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.snapshot_date.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": s.id,
            "snapshot_date": s.snapshot_date.isoformat(),
            "total_value": s.total_value,
            "total_cost": s.total_cost,
            "total_pnl": s.total_pnl,
            "allocation_data": s.allocation_data,
            "metrics_data": s.metrics_data,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in snapshots
    ]


@router.get("/holdings/{holding_id}/detail")
def holding_detail(holding_id: int, db: Session = Depends(get_db)):
    """Full enriched detail for a single holding."""
    holding = db.query(PortfolioHolding).filter(PortfolioHolding.id == holding_id).first()
    if not holding:
        return {"error": "Holding not found"}

    instrument = db.query(Instrument).filter(Instrument.id == holding.instrument_id).first()
    return enrich_holding(holding, instrument)


@router.post("/refresh")
def refresh_prices(db: Session = Depends(get_db)):
    """Refresh all prices by re-fetching from yfinance."""
    start = time.time()

    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.is_active == True)
        .all()
    )

    instrument_ids = [h.instrument_id for h in holdings]
    instruments = db.query(Instrument).filter(Instrument.id.in_(instrument_ids)).all()
    inst_map = {i.id: i for i in instruments}

    enriched = enrich_holdings_parallel(holdings, inst_map)
    duration = round(time.time() - start, 1)

    log_event(
        module="portfolio",
        event_type="prices_refreshed",
        data={"holdings_count": len(holdings), "duration_seconds": duration},
    )

    return {
        "holdings": enriched,
        "refreshed_count": len(enriched),
        "duration_seconds": duration,
    }
