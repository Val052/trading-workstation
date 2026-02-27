"""Event log — append-only record of all platform actions."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Event(Base):
    """
    Append-only event log. Every meaningful action across all modules is
    recorded here. Current state is derived from events where practical.
    """
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    module: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    instrument_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("instruments.id"), nullable=True,
    )
    actor: Mapped[str] = mapped_column(String, default="system")
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
