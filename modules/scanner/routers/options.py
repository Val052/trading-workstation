"""Options overlay endpoints — chain data, structure comparison, booking."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from modules.scanner.models import ScanResult, Candidate, AccountConfig
from modules.scanner.services.options_chain import fetch_chain
from modules.scanner.services.options_structures import (
    compare_structures,
    calculate_options_risk,
)
from modules.scanner.services.risk_calculator import calculate_risk

router = APIRouter(prefix="/options", tags=["options"])


class CompareRequest(BaseModel):
    ticker: str
    entry_price: float
    stop_loss: float
    target_1: float
    scan_result_id: Optional[int] = None


class OptionsBookmarkRequest(BaseModel):
    scan_result_id: int
    structure_type: str  # "stock", "long_call", "bull_call_spread", "bull_put_spread"
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None


@router.get("/chain/{ticker}")
def get_chain(
    ticker: str,
    min_dte: int = 14,
    max_dte: int = 90,
):
    """Fetch filtered options chain for a ticker."""
    return fetch_chain(ticker, min_dte=min_dte, max_dte=max_dte)


@router.post("/compare")
def compare(req: CompareRequest, db: Session = Depends(get_db)):
    """Generate side-by-side structure comparison."""
    # Get account config
    account = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
    if account:
        account_size = account.account_size
        risk_pct = account.risk_per_trade
    else:
        account_size = 10000
        risk_pct = 0.005

    # Fetch chain
    chains = fetch_chain(req.ticker)

    # Run comparison
    result = compare_structures(
        ticker=req.ticker,
        entry=req.entry_price,
        stop=req.stop_loss,
        target=req.target_1,
        account_size=account_size,
        risk_per_trade=risk_pct,
        chains_data=chains,
    )

    return result


@router.post("/bookmark")
def bookmark_with_structure(req: OptionsBookmarkRequest, db: Session = Depends(get_db)):
    """Bookmark a candidate with a specific options structure."""
    scan_result = db.query(ScanResult).filter(ScanResult.id == req.scan_result_id).first()
    if not scan_result:
        return {"error": "Scan result not found"}

    account = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
    if account:
        account_size = account.account_size
        risk_pct = account.risk_per_trade
    else:
        account_size = 10000
        risk_pct = 0.005

    entry = scan_result.price_at_scan
    options_analysis = None

    if req.structure_type == "stock":
        # Standard stock booking
        calc = calculate_risk(entry, req.stop_loss, req.target_1, account_size, risk_pct, req.target_2)
        position_size = calc.position_size
        risk_per_share = calc.risk_per_share
        reward_per_share = calc.reward_per_share
        r_multiple = calc.r_multiple
    else:
        # Options structure — run comparison for just this structure
        chains = fetch_chain(scan_result.ticker)
        comparison = compare_structures(
            ticker=scan_result.ticker,
            entry=entry,
            stop=req.stop_loss,
            target=req.target_1,
            account_size=account_size,
            risk_per_trade=risk_pct,
            chains_data=chains,
        )

        # Find the requested structure
        target_struct = None
        for s in comparison["structures"]:
            if s["structure_type"] == req.structure_type:
                target_struct = s
                break

        if not target_struct:
            return {"error": f"Structure {req.structure_type} not available for this ticker"}

        options_analysis = calculate_options_risk(target_struct, account_size)
        position_size = target_struct["contracts"]
        risk_per_share = target_struct["max_risk"] / max(target_struct["total_units"], 1)
        reward_per_share = (target_struct["max_reward"] or 0) / max(target_struct["total_units"], 1)
        r_multiple = target_struct["risk_reward_ratio"] or 0

    candidate = Candidate(
        scan_result_id=scan_result.id,
        ticker=scan_result.ticker,
        entry_price=entry,
        stop_loss=req.stop_loss,
        target_1=req.target_1,
        target_2=req.target_2,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        r_multiple=r_multiple,
        position_size=position_size,
        trade_structure=req.structure_type,
        options_analysis=options_analysis,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    return {
        "id": candidate.id,
        "trade_structure": req.structure_type,
        "options_analysis": options_analysis,
    }
