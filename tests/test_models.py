"""Basic model/schema tests using an in-memory SQLite database."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, BodyMetric, ExerciseSet, FoodLog, WorkoutSession


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_body_metric_created_with_timestamps(session):
    metric = BodyMetric(date=date(2026, 1, 1), weight_kg=80.5)
    session.add(metric)
    session.commit()

    saved = session.query(BodyMetric).one()
    assert saved.weight_kg == 80.5
    assert saved.created_at is not None
    assert saved.updated_at is not None


def test_workout_session_with_exercise_sets(session):
    workout = WorkoutSession(date=date(2026, 1, 1), name="Upper body")
    workout.exercise_sets.append(
        ExerciseSet(exercise_name="Bench press", set_number=1, reps=8, weight_kg=60)
    )
    session.add(workout)
    session.commit()

    saved = session.query(WorkoutSession).one()
    assert saved.name == "Upper body"
    assert len(saved.exercise_sets) == 1
    assert saved.exercise_sets[0].exercise_name == "Bench press"
    assert saved.exercise_sets[0].workout_session.id == saved.id


def test_exercise_set_deleted_when_session_deleted(session):
    workout = WorkoutSession(date=date(2026, 1, 1), name="Legs")
    workout.exercise_sets.append(ExerciseSet(exercise_name="Squat", reps=5))
    session.add(workout)
    session.commit()

    session.delete(workout)
    session.commit()

    assert session.query(ExerciseSet).count() == 0


def test_food_log_allows_optional_macros(session):
    entry = FoodLog(date=date(2026, 1, 1), description="Chicken salad")
    session.add(entry)
    session.commit()

    saved = session.query(FoodLog).one()
    assert saved.description == "Chicken salad"
    assert saved.calories is None
