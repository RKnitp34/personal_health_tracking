"""Data-access helpers: create/read/update/delete + duplicate detection.

Kept as plain functions over a passed-in Session rather than a class/DAO
layer -- there's no need for more structure than that at this scale.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analytics import NutritionTotals, SetRecord, average_daily_nutrition, best_set, sum_nutrition
from app.models import BodyMetric, ExerciseSet, Food, FoodLog, Profile, WorkoutSession
from app.parser import MealItem, ParsedBodyMetric, ParsedFoodLog, ParsedMealLog, ParsedWorkout

DUPLICATE_WINDOW_MINUTES = 5

EntryType = Literal["body", "workout", "food"]


@dataclass
class RecentEntry:
    """A normalized view of one row, for the combined recent-activity list."""

    type: EntryType
    id: int
    created_at: datetime
    date: object
    summary: str


# ---- create ---------------------------------------------------------------


def find_recent_duplicate_body_metric(session: Session, parsed: ParsedBodyMetric) -> BodyMetric | None:
    cutoff = datetime.now(UTC) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    stmt = select(BodyMetric).where(
        BodyMetric.date == parsed.date,
        BodyMetric.weight_kg == parsed.weight_kg,
        BodyMetric.body_fat_pct == parsed.body_fat_pct,
        BodyMetric.created_at >= cutoff,
    )
    return session.execute(stmt).scalars().first()


def create_body_metric(session: Session, parsed: ParsedBodyMetric) -> BodyMetric:
    metric = BodyMetric(date=parsed.date, weight_kg=parsed.weight_kg, body_fat_pct=parsed.body_fat_pct)
    session.add(metric)
    session.commit()
    return metric


def find_recent_duplicate_workout(session: Session, parsed: ParsedWorkout) -> WorkoutSession | None:
    cutoff = datetime.now(UTC) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    stmt = select(WorkoutSession).where(
        WorkoutSession.date == parsed.date,
        WorkoutSession.name == parsed.exercise_name,
        WorkoutSession.created_at >= cutoff,
    )
    candidates = session.execute(stmt).scalars().all()
    for candidate in candidates:
        existing_sets = [(s.weight_kg, s.reps) for s in candidate.exercise_sets]
        if existing_sets == parsed.sets:
            return candidate
    return None


def create_workout(session: Session, parsed: ParsedWorkout) -> WorkoutSession:
    workout = WorkoutSession(date=parsed.date, name=parsed.exercise_name)
    for i, (weight_kg, reps) in enumerate(parsed.sets, start=1):
        workout.exercise_sets.append(
            ExerciseSet(
                exercise_name=parsed.exercise_name,
                set_number=i,
                reps=reps,
                weight_kg=weight_kg,
            )
        )
    session.add(workout)
    session.commit()
    return workout


def find_recent_duplicate_food_log(session: Session, parsed: ParsedFoodLog) -> FoodLog | None:
    cutoff = datetime.now(UTC) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    stmt = select(FoodLog).where(
        FoodLog.date == parsed.date,
        FoodLog.description == parsed.description,
        FoodLog.created_at >= cutoff,
    )
    return session.execute(stmt).scalars().first()


def list_exercise_names(session: Session) -> list[str]:
    """Distinct exercise names, case-insensitive, most-recently-used casing."""
    stmt = select(ExerciseSet.exercise_name, ExerciseSet.created_at).order_by(ExerciseSet.created_at.desc())
    seen: dict[str, str] = {}
    for name, _ in session.execute(stmt):
        key = name.lower()
        if key not in seen:
            seen[key] = name
    return sorted(seen.values(), key=str.lower)


def get_exercise_sessions(session: Session, exercise_name: str, limit: int = 10) -> list[WorkoutSession]:
    """Recent workout sessions that included this exercise, most recent first."""
    stmt = (
        select(WorkoutSession)
        .join(ExerciseSet, ExerciseSet.workout_session_id == WorkoutSession.id)
        .where(ExerciseSet.exercise_name.ilike(exercise_name.strip()))
        .options(selectinload(WorkoutSession.exercise_sets))
        .order_by(WorkoutSession.date.desc())
        .distinct()
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def get_exercise_history(session: Session, exercise_name: str) -> list[SetRecord]:
    stmt = (
        select(ExerciseSet, WorkoutSession.date)
        .join(WorkoutSession, ExerciseSet.workout_session_id == WorkoutSession.id)
        .where(ExerciseSet.exercise_name.ilike(exercise_name.strip()))
        .order_by(WorkoutSession.date)
    )
    return [
        SetRecord(date=session_date, weight_kg=exercise_set.weight_kg, reps=exercise_set.reps, session_id=exercise_set.workout_session_id)
        for exercise_set, session_date in session.execute(stmt)
    ]


def create_food_log(session: Session, parsed: ParsedFoodLog) -> FoodLog:
    entry = FoodLog(
        date=parsed.date,
        description=parsed.description,
        calories=parsed.calories,
        protein_g=parsed.protein_g,
    )
    session.add(entry)
    session.commit()
    return entry


# ---- read -------------------------------------------------------------


def _workout_summary(workout: WorkoutSession) -> str:
    sets_str = ", ".join(
        f"{s.weight_kg:g}x{s.reps}" if s.weight_kg is not None else f"x{s.reps}"
        for s in workout.exercise_sets
    )
    return f"{workout.name}: {sets_str}" if sets_str else workout.name


def list_recent_entries(session: Session, limit: int = 15) -> list[RecentEntry]:
    entries: list[RecentEntry] = []

    for metric in session.execute(
        select(BodyMetric).order_by(BodyMetric.created_at.desc()).limit(limit)
    ).scalars():
        summary = f"Weight: {metric.weight_kg:g}kg"
        if metric.body_fat_pct is not None:
            summary += f", {metric.body_fat_pct:g}% fat"
        entries.append(RecentEntry("body", metric.id, metric.created_at, metric.date, summary))

    for workout in session.execute(
        select(WorkoutSession).order_by(WorkoutSession.created_at.desc()).limit(limit)
    ).scalars():
        entries.append(
            RecentEntry("workout", workout.id, workout.created_at, workout.date, _workout_summary(workout))
        )

    for food in session.execute(
        select(FoodLog).order_by(FoodLog.created_at.desc()).limit(limit)
    ).scalars():
        summary = f"[{food.meal_type}] {food.description}" if food.meal_type else food.description
        extras = []
        if food.calories is not None:
            extras.append(f"{food.calories:g} cal")
        if food.protein_g is not None:
            extras.append(f"{food.protein_g:g}g protein")
        if extras:
            summary += f" ({', '.join(extras)})"
        entries.append(RecentEntry("food", food.id, food.created_at, food.date, summary))

    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries[:limit]


def get_body_metric(session: Session, entry_id: int) -> BodyMetric | None:
    return session.get(BodyMetric, entry_id)


def get_workout(session: Session, entry_id: int) -> WorkoutSession | None:
    return session.get(WorkoutSession, entry_id)


def get_food_log(session: Session, entry_id: int) -> FoodLog | None:
    return session.get(FoodLog, entry_id)


# ---- update / delete ----------------------------------------------------


def update_body_metric(
    session: Session, metric: BodyMetric, *, date, weight_kg: float, body_fat_pct: float | None
) -> None:
    metric.date = date
    metric.weight_kg = weight_kg
    metric.body_fat_pct = body_fat_pct
    session.commit()


def delete_body_metric(session: Session, metric: BodyMetric) -> None:
    session.delete(metric)
    session.commit()


def update_workout_set(session: Session, exercise_set: ExerciseSet, *, weight_kg: float | None, reps: int) -> None:
    exercise_set.weight_kg = weight_kg
    exercise_set.reps = reps
    session.commit()


def delete_workout_set(session: Session, exercise_set: ExerciseSet) -> None:
    session.delete(exercise_set)
    session.commit()


def update_workout_session(session: Session, workout: WorkoutSession, *, date, name: str) -> None:
    workout.date = date
    workout.name = name
    session.commit()


def delete_workout(session: Session, workout: WorkoutSession) -> None:
    session.delete(workout)
    session.commit()


def update_food_log(
    session: Session,
    food: FoodLog,
    *,
    date,
    description: str,
    calories: float | None,
    protein_g: float | None,
) -> None:
    food.date = date
    food.description = description
    food.calories = calories
    food.protein_g = protein_g
    session.commit()


def delete_food_log(session: Session, food: FoodLog) -> None:
    session.delete(food)
    session.commit()


# ---- foods (personal database of known foods) ---------------------------

_COUNT_UNITS = {"piece", "bowl", "spoon", "cup", "katori"}
_SCALED_UNITS = {"g": "100g", "ml": "100ml"}


def list_foods(session: Session) -> list[Food]:
    return list(session.execute(select(Food).order_by(Food.name)).scalars())


def get_food(session: Session, food_id: int) -> Food | None:
    return session.get(Food, food_id)


def find_food_by_name(session: Session, name: str) -> Food | None:
    stmt = select(Food).where(Food.name.ilike(name.strip()))
    return session.execute(stmt).scalars().first()


def create_food(
    session: Session, *, name: str, unit: str, calories: float, protein_g: float | None, carbs_g: float | None
) -> Food:
    food = Food(name=name.strip(), unit=unit, calories=calories, protein_g=protein_g, carbs_g=carbs_g)
    session.add(food)
    session.commit()
    return food


def update_food(
    session: Session,
    food: Food,
    *,
    name: str,
    unit: str,
    calories: float,
    protein_g: float | None,
    carbs_g: float | None,
) -> None:
    food.name = name.strip()
    food.unit = unit
    food.calories = calories
    food.protein_g = protein_g
    food.carbs_g = carbs_g
    session.commit()


def delete_food(session: Session, food: Food) -> None:
    session.delete(food)
    session.commit()


@dataclass
class MealResolution:
    description: str
    calories: float
    protein_g: float
    carbs_g: float
    unmatched: list[str]


def resolve_meal_items(session: Session, items: list[MealItem]) -> MealResolution:
    """Look up each item in the foods table and sum up macros. Items whose
    food isn't found, or whose unit doesn't match how that food is defined,
    are skipped and reported in `unmatched` rather than failing the whole
    entry."""
    parts: list[str] = []
    total_calories = total_protein = total_carbs = 0.0
    unmatched: list[str] = []

    for item in items:
        food = find_food_by_name(session, item.food_name)
        multiplier: float | None = None

        if food is not None:
            if item.unit is None and food.unit in _COUNT_UNITS:
                multiplier = item.quantity
            elif item.unit in _COUNT_UNITS and food.unit == item.unit:
                multiplier = item.quantity
            elif item.unit in _SCALED_UNITS and food.unit == _SCALED_UNITS[item.unit]:
                multiplier = item.quantity / 100.0

        if multiplier is None:
            unmatched.append(f"{item.quantity:g}{item.unit or ''} {item.food_name}".strip())
            continue

        total_calories += food.calories * multiplier
        total_protein += (food.protein_g or 0) * multiplier
        total_carbs += (food.carbs_g or 0) * multiplier
        unit_label = f"{item.unit} " if item.unit else ""
        parts.append(f"{item.quantity:g} {unit_label}{food.name}".replace("  ", " ").strip())

    return MealResolution(
        description=", ".join(parts) if parts else "(nothing matched)",
        calories=total_calories,
        protein_g=total_protein,
        carbs_g=total_carbs,
        unmatched=unmatched,
    )


def find_recent_duplicate_meal_log(session: Session, parsed: ParsedMealLog, description: str) -> FoodLog | None:
    cutoff = datetime.now(UTC) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    stmt = select(FoodLog).where(
        FoodLog.date == parsed.date,
        FoodLog.meal_type == parsed.meal_type,
        FoodLog.description == description,
        FoodLog.created_at >= cutoff,
    )
    return session.execute(stmt).scalars().first()


# ---- dashboard-level workout summaries -----------------------------------


def get_recent_workout_sessions(session: Session, limit: int = 5) -> list[WorkoutSession]:
    stmt = (
        select(WorkoutSession)
        .options(selectinload(WorkoutSession.exercise_sets))
        .order_by(WorkoutSession.date.desc(), WorkoutSession.created_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def get_todays_workout_sessions(session: Session, on_date: date) -> list[WorkoutSession]:
    stmt = (
        select(WorkoutSession)
        .where(WorkoutSession.date == on_date)
        .options(selectinload(WorkoutSession.exercise_sets))
    )
    return list(session.execute(stmt).scalars())


def get_workout_volume_since(session: Session, since_date: date) -> float:
    stmt = (
        select(ExerciseSet.weight_kg, ExerciseSet.reps)
        .join(WorkoutSession, ExerciseSet.workout_session_id == WorkoutSession.id)
        .where(WorkoutSession.date >= since_date)
    )
    return sum((weight_kg or 0) * reps for weight_kg, reps in session.execute(stmt))


def get_recent_prs(session: Session, limit: int = 5) -> list[tuple[str, SetRecord]]:
    """Current best set for each exercise that has one, most recently set first."""
    prs: list[tuple[str, SetRecord]] = []
    for name in list_exercise_names(session):
        history = get_exercise_history(session, name)
        record = best_set(history)
        if record:
            prs.append((name, record))
    prs.sort(key=lambda pair: pair[1].date, reverse=True)
    return prs[:limit]


# ---- calendar (day-wise weight/nutrition summary) ------------------------


@dataclass
class DaySummary:
    weight_kg: float | None
    calories: float
    protein_g: float
    carbs_g: float


def get_month_summary(session: Session, year: int, month: int) -> dict[date, DaySummary]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    end -= timedelta(days=1)

    weights: dict[date, float] = {}
    weight_stmt = (
        select(BodyMetric.date, BodyMetric.weight_kg)
        .where(BodyMetric.date >= start, BodyMetric.date <= end)
        .order_by(BodyMetric.created_at)
    )
    for metric_date, weight_kg in session.execute(weight_stmt):
        weights[metric_date] = weight_kg  # last row per date (by created_at) wins

    nutrition_by_day: dict[date, list[tuple]] = {}
    nutrition_stmt = select(
        FoodLog.date, FoodLog.calories, FoodLog.protein_g, FoodLog.carbs_g, FoodLog.fat_g
    ).where(FoodLog.date >= start, FoodLog.date <= end)
    for log_date, calories, protein_g, carbs_g, fat_g in session.execute(nutrition_stmt):
        nutrition_by_day.setdefault(log_date, []).append((calories, protein_g, carbs_g, fat_g))

    all_dates = set(weights) | set(nutrition_by_day)
    summary: dict[date, DaySummary] = {}
    for d in all_dates:
        totals = sum_nutrition(nutrition_by_day.get(d, []))
        summary[d] = DaySummary(
            weight_kg=weights.get(d), calories=totals.calories, protein_g=totals.protein_g, carbs_g=totals.carbs_g
        )
    return summary


# ---- profile (single-row settings: height, target weight) ---------------


def get_profile(session: Session) -> Profile | None:
    return session.get(Profile, 1)


def upsert_profile(session: Session, *, height_cm: float | None, target_weight_kg: float | None) -> Profile:
    profile = session.get(Profile, 1)
    if profile is None:
        profile = Profile(id=1)
        session.add(profile)
    profile.height_cm = height_cm
    profile.target_weight_kg = target_weight_kg
    session.commit()
    return profile


# ---- body weight history -------------------------------------------------


def get_weight_history(session: Session, limit: int = 30) -> list[BodyMetric]:
    """Most recent `limit` weigh-ins, chronological (oldest first) -- ready
    to feed straight into a trend chart."""
    stmt = select(BodyMetric).order_by(BodyMetric.date.desc()).limit(limit)
    return list(reversed(session.execute(stmt).scalars().all()))


def get_latest_weight(session: Session) -> BodyMetric | None:
    stmt = select(BodyMetric).order_by(BodyMetric.date.desc()).limit(1)
    return session.execute(stmt).scalars().first()


def get_body_metrics_on_date(session: Session, on_date: date) -> list[BodyMetric]:
    stmt = select(BodyMetric).where(BodyMetric.date == on_date).order_by(BodyMetric.created_at)
    return list(session.execute(stmt).scalars())


def get_food_logs_on_date(session: Session, on_date: date) -> list[FoodLog]:
    stmt = select(FoodLog).where(FoodLog.date == on_date).order_by(FoodLog.created_at)
    return list(session.execute(stmt).scalars())


# ---- nutrition: history + daily/weekly totals ----------------------------


def get_meal_history(session: Session, limit: int = 20) -> list[FoodLog]:
    stmt = select(FoodLog).order_by(FoodLog.date.desc(), FoodLog.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


def get_daily_nutrition(session: Session, on_date: date) -> NutritionTotals:
    stmt = select(FoodLog.calories, FoodLog.protein_g, FoodLog.carbs_g, FoodLog.fat_g).where(
        FoodLog.date == on_date
    )
    return sum_nutrition(list(session.execute(stmt)))


def get_weekly_nutrition_average(session: Session, end_date: date, days: int = 7) -> NutritionTotals:
    start_date = end_date - timedelta(days=days - 1)
    stmt = select(
        FoodLog.date, FoodLog.calories, FoodLog.protein_g, FoodLog.carbs_g, FoodLog.fat_g
    ).where(FoodLog.date >= start_date, FoodLog.date <= end_date)

    by_day: dict[date, list[tuple]] = {}
    for log_date, calories, protein_g, carbs_g, fat_g in session.execute(stmt):
        by_day.setdefault(log_date, []).append((calories, protein_g, carbs_g, fat_g))

    daily_totals = [sum_nutrition(rows) for rows in by_day.values()]
    return average_daily_nutrition(daily_totals, days)


def create_meal_log(session: Session, parsed: ParsedMealLog, resolution: MealResolution) -> FoodLog:
    entry = FoodLog(
        date=parsed.date,
        meal_type=parsed.meal_type,
        description=resolution.description,
        calories=resolution.calories,
        protein_g=resolution.protein_g,
        carbs_g=resolution.carbs_g,
    )
    session.add(entry)
    session.commit()
    return entry
