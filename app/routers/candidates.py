"""Candidate (watchlist/bookmark) endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Candidate, ScanResult, AccountConfig
from app.services.risk_calculator import calculate_risk, suggest_targets

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


class BookmarkRequest(BaseModel):
    scan_result_id: int
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None


class RiskCalcRequest(BaseModel):
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None


@router.get("")
def list_candidates(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List bookmarked candidates, optionally filtered by status."""
    query = db.query(Candidate)
    if status:
        query = query.filter(Candidate.status == status)
    query = query.order_by(Candidate.created_at.desc())
    rows = query.limit(100).all()

    return [
        {
            "id": c.id,
            "scan_result_id": c.scan_result_id,
            "ticker": c.ticker,
            "entry_price": c.entry_price,
            "stop_loss": c.stop_loss,
            "target_1": c.target_1,
            "target_2": c.target_2,
            "risk_per_share": c.risk_per_share,
            "reward_per_share": c.reward_per_share,
            "r_multiple": c.r_multiple,
            "position_size": c.position_size,
            "trade_structure": c.trade_structure,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.post("/bookmark")
def bookmark_candidate(req: BookmarkRequest, db: Session = Depends(get_db)):
    """Bookmark a scan result as a candidate with stop/target levels."""
    scan_result = db.query(ScanResult).filter(ScanResult.id == req.scan_result_id).first()
    if not scan_result:
        return {"error": "Scan result not found"}

    # Get account config for position sizing
    account = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
    if not account:
        account_size = 10000
        risk_pct = 0.005
    else:
        account_size = account.account_size
        risk_pct = account.risk_per_trade

    calc = calculate_risk(
        entry_price=scan_result.price_at_scan,
        stop_loss=req.stop_loss,
        target_1=req.target_1,
        account_size=account_size,
        risk_per_trade=risk_pct,
        target_2=req.target_2,
    )

    candidate = Candidate(
        scan_result_id=scan_result.id,
        ticker=scan_result.ticker,
        entry_price=scan_result.price_at_scan,
        stop_loss=req.stop_loss,
        target_1=req.target_1,
        target_2=req.target_2,
        risk_per_share=calc.risk_per_share,
        reward_per_share=calc.reward_per_share,
        r_multiple=calc.r_multiple,
        position_size=calc.position_size,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    return {"id": candidate.id, "risk_calc": calc.to_dict()}


@router.post("/calculate-risk")
def calc_risk(req: RiskCalcRequest, db: Session = Depends(get_db)):
    """Calculate risk/reward without bookmarking — for the detail panel."""
    account = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
    if not account:
        account_size = 10000
        risk_pct = 0.005
    else:
        account_size = account.account_size
        risk_pct = account.risk_per_trade

    calc = calculate_risk(
        entry_price=req.entry_price,
        stop_loss=req.stop_loss,
        target_1=req.target_1,
        account_size=account_size,
        risk_per_trade=risk_pct,
        target_2=req.target_2,
    )
    return calc.to_dict()


@router.patch("/{candidate_id}/status")
def update_status(candidate_id: int, status: str, db: Session = Depends(get_db)):
    """Update candidate status (watching, entered, exited, expired)."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        return {"error": "Not found"}
    c.status = status
    db.commit()
    return {"id": c.id, "status": c.status}
