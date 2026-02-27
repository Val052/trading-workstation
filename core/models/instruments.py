"""Instrument registry — canonical instrument resolution."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class Instrument(TimestampMixin, Base):
    """
    Canonical instrument record. Every module references instruments by ID.
    ID is the ticker for US equities, ISIN for international.
    """
    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    isin: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    instrument_type: Mapped[str] = mapped_column(
        String, default="equity",
    )  # equity, etf, index, bond, crypto, cash, real_estate
    currency: Mapped[str] = mapped_column(String, default="USD")
    sector: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )  # flexible: country, market_cap_bucket, etc.
