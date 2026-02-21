"""SQLAlchemy models — full data model for all phases."""

import json
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    String, Text, Boolean, Integer, Float, Date, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(Text, default="")
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")

    scan_results: Mapped[list["ScanResult"]] = relationship(back_populates="strategy")


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"))
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    price_at_scan: Mapped[float] = mapped_column(Float, nullable=False)
    signal_data: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    strategy: Mapped["Strategy"] = relationship(back_populates="scan_results")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="scan_result")
    outcomes: Mapped[list["Outcome"]] = relationship(back_populates="scan_result")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_result_id: Mapped[int] = mapped_column(Integer, ForeignKey("scan_results.id"))
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target_1: Mapped[float] = mapped_column(Float, nullable=False)
    target_2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    reward_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    r_multiple: Mapped[float] = mapped_column(Float, nullable=False)
    position_size: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_structure: Mapped[str] = mapped_column(String, default="stock")
    options_analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="watching")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scan_result: Mapped["ScanResult"] = relationship(back_populates="candidates")


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_result_id: Mapped[int] = mapped_column(Integer, ForeignKey("scan_results.id"))
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    price_day_1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_favorable: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_adverse: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    would_have_hit_target: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    would_have_hit_stop: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scan_result: Mapped["ScanResult"] = relationship(back_populates="outcomes")


class AccountConfig(Base):
    __tablename__ = "account_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_size: Mapped[float] = mapped_column(Float, nullable=False)
    risk_per_trade: Mapped[float] = mapped_column(Float, nullable=False)
    max_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PriceCache(Base):
    """Daily price cache to avoid re-downloading from yfinance."""
    __tablename__ = "price_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    cache_date: Mapped[date] = mapped_column(Date, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)  # serialized DataFrame
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
