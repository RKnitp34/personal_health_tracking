"""Environment/configuration handling for the tracking app."""
from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def normalize_db_url(url: str) -> str:
    """Fix up a raw connection string pasted from a host provider.

    - Neon/Heroku-style strings often start with "postgres://"; SQLAlchemy
      1.4+ requires "postgresql://".
    - A bare "postgresql://" (no driver) lets SQLAlchemy pick a default
      DBAPI, which in newer SQLAlchemy versions can resolve to psycopg3
      even when only psycopg2 is installed. Pin the driver explicitly so
      behavior doesn't depend on which SQLAlchemy version is running.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


DEFAULT_DB_PATH = BASE_DIR / "data" / "tracking.db"
DATABASE_URL = normalize_db_url(os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}"))

# Only used to sign Flask's session cookie for flash messages; this is a
# single-user local tool, so a fixed dev default is fine.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
