"""Copies the local SQLite database to data/backups/ with a timestamp.

Safe to run anytime -- read-only against the live file, never modifies it.
Usage: python scripts/backup_db.py
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "tracking.db"
BACKUP_DIR = BASE_DIR / "data" / "backups"


def main() -> None:
    if not DB_PATH.exists():
        print(f"No database found at {DB_PATH} -- nothing to back up.")
        sys.exit(1)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"tracking_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)

    print(f"Backed up {DB_PATH} -> {backup_path}")
    print(f"Size: {backup_path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
