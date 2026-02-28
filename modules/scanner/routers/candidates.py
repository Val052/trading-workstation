"""Candidate (watchlist/bookmark) endpoints."""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.services.event_log import log_event
from modules.scanner.models import Candidate, ScanResult, AccountConfig
from modules.scanner.services.risk_calculator import calculate_risk, suggest_targets

router = APIRouter(prefix="/candidates", tags=["candidates"])


class BookmarkRequest(BaseModel):
    scan_result_id: int
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None
    trade_structure: str = "stock"


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

    # Options analysis if non-stock structure requested
    options_analysis = None
    if req.trade_structure != "stock":
        try:
            from modules.scanner.services.options_chain import fetch_chain
            from modules.scanner.services.options_structures import compare_structures, calculate_options_risk
            chains = fetch_chain(scan_result.ticker)
            comparison = compare_structures(
                ticker=scan_result.ticker,
                entry=scan_result.price_at_scan,
                stop=req.stop_loss,
                target=req.target_1,
                account_size=account_size,
                risk_per_trade=risk_pct,
                chains_data=chains,
            )
            for s in comparison["structures"]:
                if s["structure_type"] == req.trade_structure:
                    options_analysis = calculate_options_risk(s, account_size)
                    break
        except Exception as e:
            logger.warning(f"Options analysis failed for bookmark: {e}")

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
        trade_structure=req.trade_structure,
        options_analysis=options_analysis,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    # Log event
    log_event(
        module="scanner",
        event_type="candidate_bookmarked",
        instrument_id=scan_result.ticker,
        data={
            "strategy": scan_result.strategy_id,
            "entry": scan_result.price_at_scan,
            "stop": req.stop_loss,
            "target": req.target_1,
            "r_multiple": calc.r_multiple,
        },
    )

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
