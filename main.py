"""Entry point for the personal tracking system.

Phase 1: initializes the database and reports table status.
Later phases will add real data-entry commands here.
"""
from sqlalchemy import inspect

from app.db import engine, init_db


def main() -> None:
    init_db()
    tables = inspect(engine).get_table_names()
    print(f"Database ready at: {engine.url}")
    print(f"Tables: {', '.join(sorted(tables))}")


if __name__ == "__main__":
    main()
