"""Account settings endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from modules.scanner.models import AccountConfig

router = APIRouter(prefix="/settings", tags=["settings"])


class AccountSettingsRequest(BaseModel):
    account_size: float
    risk_per_trade: float
    max_positions: int


@router.get("/account")
def get_account(db: Session = Depends(get_db)):
    """Get current account configuration."""
    account = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
    if not account:
        return {
            "account_size": 10000,
            "risk_per_trade": 0.005,
            "max_positions": 5,
        }
    return {
        "account_size": account.account_size,
        "risk_per_trade": account.risk_per_trade,
        "max_positions": account.max_positions,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


@router.post("/account")
def update_account(req: AccountSettingsRequest, db: Session = Depends(get_db)):
    """Update account configuration."""
    account = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
    if account:
        account.account_size = req.account_size
        account.risk_per_trade = req.risk_per_trade
        account.max_positions = req.max_positions
        account.updated_at = datetime.utcnow()
    else:
        account = AccountConfig(
            account_size=req.account_size,
            risk_per_trade=req.risk_per_trade,
            max_positions=req.max_positions,
        )
        db.add(account)
    db.commit()
    return {"status": "ok", "account_size": req.account_size}
