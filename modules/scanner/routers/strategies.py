"""Strategy management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from modules.scanner.models import Strategy
from modules.scanner.services.scanner import discover_strategies, sync_strategies_to_db

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("")
def list_strategies(db: Session = Depends(get_db)):
    """List all strategies with their active status."""
    # Ensure DB is synced with discovered strategies
    discovered = discover_strategies()
    sync_strategies_to_db(db, discovered)

    rows = db.query(Strategy).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "source": s.source,
            "parameters": s.parameters,
            "is_active": s.is_active,
            "notes": s.notes,
        }
        for s in rows
    ]


@router.patch("/{strategy_id}/toggle")
def toggle_strategy(strategy_id: str, db: Session = Depends(get_db)):
    """Toggle a strategy's active status."""
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not s:
        return {"error": "Not found"}
    s.is_active = not s.is_active
    db.commit()
    return {"id": s.id, "is_active": s.is_active}


@router.patch("/{strategy_id}/parameters")
def update_parameters(strategy_id: str, parameters: dict, db: Session = Depends(get_db)):
    """Update a strategy's parameters."""
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not s:
        return {"error": "Not found"}
    s.parameters = parameters
    db.commit()
    return {"id": s.id, "parameters": s.parameters}
