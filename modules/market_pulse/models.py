"""Market Pulse models — regime snapshots and asset trend tracking."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Text, Float, Date, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    regime: Mapped[str] = mapped_column(String, nullable=False)
    regime_score: Mapped[float] = mapped_column(Float, nullable=False)
    regime_description: Mapped[str] = mapped_column(Text, default="")
    intermarket_score: Mapped[float] = mapped_column(Float, nullable=False)
    breadth_score: Mapped[float] = mapped_column(Float, nullable=False)
    volatility_score: Mapped[float] = mapped_column(Float, nullable=False)
    intermarket_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    breadth_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    sector_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    volatility_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    signals: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssetTrend(Base):
    __tablename__ = "asset_trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    trend_score: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dma_50: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dma_200: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
