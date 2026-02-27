"""Portfolio module models — holdings and snapshots."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Integer, String, Text, Float, Boolean, Date, DateTime, JSON, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class PortfolioHolding(Base):
    """
    A single investment holding. Stores static position data — enrichment
    (current price, P/L, momentum) is computed on-the-fly by the enrichment service.
    """
    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        String, ForeignKey("instruments.id"), nullable=False,
    )
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis_currency: Mapped[str] = mapped_column(String, default="EUR")
    date_acquired: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    account_label: Mapped[str] = mapped_column(String, default="default")
    asset_class: Mapped[str] = mapped_column(String, default="equity")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )


class PortfolioSnapshot(Base):
    """Point-in-time portfolio state for historical tracking."""
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    allocation_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metrics_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
