"""Engine/session setup and database initialization."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL
from app.models import Base

if DATABASE_URL.startswith("sqlite:///"):
    db_path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

# pool_pre_ping: on hosted Postgres (e.g. Neon), the DB can suspend after
# idling and drop pooled connections; this validates a connection before
# use and transparently reconnects instead of raising.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't already exist. Safe to call repeatedly."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
