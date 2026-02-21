"""Database setup — SQLite via SQLAlchemy."""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "workstation.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Safe to call repeatedly."""
    from app.models import (  # noqa: F401 — import triggers table registration
        Strategy, ScanResult, Candidate, Outcome, AccountConfig, PriceCache,
    )
    Base.metadata.create_all(bind=engine)
