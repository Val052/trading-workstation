"""Event log service — append-only logging of platform actions."""

from __future__ import annotations

import logging
from typing import Optional

from core.database import SessionLocal
from core.models.events import Event

logger = logging.getLogger(__name__)


def log_event(
    module: str,
    event_type: str,
    instrument_id: Optional[str] = None,
    data: Optional[dict] = None,
    actor: str = "system",
    session_id: Optional[str] = None,
) -> Event:
    """
    Log an event to the append-only event table.
    Returns the created Event (or None on failure).
    """
    db = SessionLocal()
    try:
        event = Event(
            module=module,
            event_type=event_type,
            instrument_id=instrument_id,
            actor=actor,
            data=data,
            session_id=session_id,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        logger.debug(f"Event logged: {module}/{event_type} instrument={instrument_id}")
        return event
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log event {module}/{event_type}: {e}")
        return None
    finally:
        db.close()
