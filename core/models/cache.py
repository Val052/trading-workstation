"""PriceCache model — shared daily price cache for all modules."""

from datetime import date, datetime

from sqlalchemy import Integer, String, Text, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class PriceCache(Base):
    """Daily price cache to avoid re-downloading from yfinance."""
    __tablename__ = "price_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False, index=True)
    cache_date: Mapped[date] = mapped_column(Date, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
