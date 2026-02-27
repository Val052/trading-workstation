"""Database setup — SQLite via SQLAlchemy."""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models.base import Base

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "terminal.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Safe to call repeatedly."""
    # Import all model modules to register them with Base.metadata
    import core.models.instruments  # noqa: F401
    import core.models.events  # noqa: F401
    import core.models.cache  # noqa: F401
    Base.metadata.create_all(bind=engine)
