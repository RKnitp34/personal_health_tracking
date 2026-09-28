"""Database models for the personal tracking system.

Phase 1 covers body metrics, workouts, and food logs. Kept intentionally
flexible (free-text fields alongside structured ones) so later phases
(e.g. natural-language entry, other tracking domains) can build on top
without schema churn.
"""
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Profile(TimestampMixin, Base):
    """Single-row settings: things that rarely change (height, weight goal).
    Not a daily log, so it doesn't belong in body_metrics."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    height_cm: Mapped[float | None] = mapped_column(nullable=True)
    target_weight_kg: Mapped[float | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"Profile(height_cm={self.height_cm}, target_weight_kg={self.target_weight_kg})"


class BodyMetric(TimestampMixin, Base):
    """A single day's body measurements (weight, body fat, etc.)."""

    __tablename__ = "body_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    weight_kg: Mapped[float | None] = mapped_column(nullable=True)
    body_fat_pct: Mapped[float | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"BodyMetric(date={self.date}, weight_kg={self.weight_kg})"


class WorkoutSession(TimestampMixin, Base):
    """A single workout session (e.g. 'Upper body', 'Run')."""

    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    exercise_sets: Mapped[list["ExerciseSet"]] = relationship(
        back_populates="workout_session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"WorkoutSession(date={self.date}, name={self.name!r})"


class ExerciseSet(TimestampMixin, Base):
    """A single set within a workout session."""

    __tablename__ = "exercise_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id"), nullable=False, index=True
    )
    exercise_name: Mapped[str] = mapped_column(String(120), nullable=False)
    set_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    workout_session: Mapped["WorkoutSession"] = relationship(back_populates="exercise_sets")

    def __repr__(self) -> str:
        return f"ExerciseSet(exercise_name={self.exercise_name!r}, reps={self.reps})"


class Food(TimestampMixin, Base):
    """A personal food-database entry: macros per one unit of this food.

    `unit` is one of: piece, bowl, spoon, cup, katori, 100g, 100ml.
    'piece'/'bowl'/'spoon'/'cup'/'katori' scale by plain count when logging
    (e.g. "2 eggs" = 2x); '100g'/'100ml' scale proportionally
    (e.g. "250ml milk" = 2.5x).
    """

    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    calories: Mapped[float] = mapped_column(nullable=False)
    protein_g: Mapped[float | None] = mapped_column(nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"Food(name={self.name!r}, unit={self.unit!r})"


class FoodLog(TimestampMixin, Base):
    """A single food entry. `description` holds the raw entry text; the
    structured macro fields are optional and can be filled in later
    (manually now, automatically by a future parsing step)."""

    __tablename__ = "food_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    calories: Mapped[float | None] = mapped_column(nullable=True)
    protein_g: Mapped[float | None] = mapped_column(nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(nullable=True)
    fat_g: Mapped[float | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"FoodLog(date={self.date}, description={self.description!r})"
