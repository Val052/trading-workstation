"""Scanner module models — strategies, scan results, candidates, outcomes, account config."""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    String, Text, Boolean, Integer, Float, Date, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String, primary_key=True)
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

    # Entry reference (from scan)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False)

    # Forward prices (close on trading day N after scan)
    price_day_1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_3: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_day_20: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Excursion analysis (within first 10 trading days)
    max_favorable: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_adverse: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_favorable_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_adverse_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_favorable_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_adverse_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Theoretical trade outcome
    would_have_hit_target: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    would_have_hit_stop: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    target_hit_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stop_hit_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    theoretical_r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Regime context at time of scan
    regime_at_scan: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    regime_score_at_scan: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Tracking state
    status: Mapped[str] = mapped_column(String, default="pending")
    days_tracked: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scan_result: Mapped["ScanResult"] = relationship(back_populates="outcomes")


class AccountConfig(Base):
    __tablename__ = "account_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_size: Mapped[float] = mapped_column(Float, nullable=False)
    risk_per_trade: Mapped[float] = mapped_column(Float, nullable=False)
    max_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
