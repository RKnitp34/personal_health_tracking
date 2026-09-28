"""One-time migration: copy all data from the local SQLite database to a
Postgres database (e.g. a free Neon instance), preserving row IDs so
foreign keys (exercise_sets -> workout_sessions) stay correct.

Read-only against the SQLite source -- it is never modified. Safe to run
more than once: it wipes and recreates the tables it writes to on the
TARGET only, never touches SOURCE.

Usage:
    export SOURCE_DB_URL="sqlite:////absolute/path/to/data/tracking.db"
    export TARGET_DB_URL="postgresql://user:password@host/dbname?sslmode=require"
    python scripts/migrate_to_postgres.py

Both env vars must be set explicitly -- this script never reads app/config.py's
DATABASE_URL, so it can't accidentally migrate the wrong database.
"""
import os
import sys

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import normalize_db_url  # noqa: E402
from app.models import Base, BodyMetric, ExerciseSet, Food, FoodLog, Profile, WorkoutSession  # noqa: E402

# Order matters: parents before children (exercise_sets references workout_sessions).
MODELS_IN_ORDER = [Profile, Food, BodyMetric, FoodLog, WorkoutSession, ExerciseSet]


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required env var: {name}")
        sys.exit(1)
    return value


def copy_table(source_session: Session, target_session: Session, model) -> tuple[int, int]:
    rows = source_session.execute(select(model)).scalars().all()
    if not rows:
        return 0, 0

    dicts = [{c.name: getattr(row, c.name) for c in model.__table__.columns} for row in rows]
    target_session.execute(model.__table__.insert(), dicts)
    target_session.commit()
    return len(rows), len(dicts)


def reset_postgres_sequence(target_session: Session, model) -> None:
    table_name = model.__table__.name
    target_session.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence(:table, 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
        ).bindparams(table=table_name)
    )
    target_session.commit()


def verify_counts(source_session: Session, target_session: Session, model) -> bool:
    source_count = source_session.execute(select(model)).scalars().all()
    target_count = target_session.execute(select(model)).scalars().all()
    ok = len(source_count) == len(target_count)
    status = "OK" if ok else "MISMATCH"
    print(f"  {model.__tablename__}: source={len(source_count)} target={len(target_count)} [{status}]")
    return ok


def main() -> None:
    source_url = normalize_db_url(get_required_env("SOURCE_DB_URL"))
    target_url = normalize_db_url(get_required_env("TARGET_DB_URL"))

    if not source_url.startswith("sqlite:"):
        print("Refusing to run: SOURCE_DB_URL doesn't look like a SQLite URL.")
        sys.exit(1)
    if target_url.startswith("sqlite:"):
        print("Refusing to run: TARGET_DB_URL looks like SQLite, not Postgres.")
        sys.exit(1)

    print(f"Source (read-only): {source_url}")
    print(f"Target: {target_url.split('@')[-1] if '@' in target_url else target_url}")

    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)

    print("\nCreating tables on target (if not already present)...")
    Base.metadata.create_all(target_engine)

    with Session(source_engine) as source_session, Session(target_engine) as target_session:
        print("\nCopying data...")
        for model in MODELS_IN_ORDER:
            copied, total = copy_table(source_session, target_session, model)
            print(f"  {model.__tablename__}: copied {copied} row(s)")

        if target_engine.dialect.name == "postgresql":
            print("\nResetting Postgres auto-increment sequences...")
            for model in MODELS_IN_ORDER:
                reset_postgres_sequence(target_session, model)

        print("\nVerifying row counts (source vs target)...")
        all_ok = True
        for model in MODELS_IN_ORDER:
            if not verify_counts(source_session, target_session, model):
                all_ok = False

    if not all_ok:
        print("\nMigration completed with MISMATCHES -- do not switch the app over yet.")
        sys.exit(1)

    print("\nAll table row counts match. Migration verified successfully.")


if __name__ == "__main__":
    main()
