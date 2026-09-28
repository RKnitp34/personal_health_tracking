"""Deterministic workout calculations: volume, PRs, estimated 1RM,
progression. Plain Python/math only -- no LLM, nothing probabilistic.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SetRecord:
    date: date
    weight_kg: float | None
    reps: int
    session_id: int


def set_volume(rec: SetRecord) -> float:
    """weight x reps; bodyweight sets (no weight) count as 0 volume."""
    return (rec.weight_kg or 0) * rec.reps


def total_volume(records: list[SetRecord]) -> float:
    return sum(set_volume(r) for r in records)


def estimated_1rm(weight_kg: float, reps: int) -> float:
    """Epley formula: a simple, standard, deterministic 1RM estimate."""
    return round(weight_kg * (1 + reps / 30), 1)


def best_set(records: list[SetRecord]) -> SetRecord | None:
    """Best = heaviest weight lifted; ties broken by more reps."""
    weighted = [r for r in records if r.weight_kg is not None]
    if not weighted:
        return None
    return max(weighted, key=lambda r: (r.weight_kg, r.reps))


def previous_best(records: list[SetRecord], current: SetRecord) -> SetRecord | None:
    """Best set strictly before the date the current best was achieved."""
    earlier = [r for r in records if r.date < current.date]
    return best_set(earlier)


def best_reps_by_weight(records: list[SetRecord]) -> list[tuple[float, int]]:
    """Highest reps ever achieved at each distinct weight, heaviest first."""
    best: dict[float, int] = {}
    for r in records:
        if r.weight_kg is None:
            continue
        best[r.weight_kg] = max(best.get(r.weight_kg, 0), r.reps)
    return sorted(best.items(), key=lambda kv: -kv[0])


def best_estimated_1rm(records: list[SetRecord]) -> tuple[float, SetRecord] | None:
    """The set that produces the highest estimated 1RM, with that estimate."""
    weighted = [r for r in records if r.weight_kg is not None and r.reps > 0]
    if not weighted:
        return None
    best_rec = max(weighted, key=lambda r: estimated_1rm(r.weight_kg, r.reps))
    return estimated_1rm(best_rec.weight_kg, best_rec.reps), best_rec


def weekly_volume(records: list[SetRecord]) -> list[tuple[str, float]]:
    """Total volume per ISO week (e.g. '2026-W05'), chronological."""
    totals: dict[str, float] = defaultdict(float)
    for r in records:
        year, week, _ = r.date.isocalendar()
        totals[f"{year}-W{week:02d}"] += set_volume(r)
    return sorted(totals.items())


def progression_by_date(records: list[SetRecord]) -> list[tuple[date, float]]:
    """Best weight lifted per calendar date, chronological -- feeds the chart."""
    best_per_date: dict[date, float] = {}
    for r in records:
        if r.weight_kg is None:
            continue
        best_per_date[r.date] = max(best_per_date.get(r.date, 0), r.weight_kg)
    return sorted(best_per_date.items())


def bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    return round(weight_kg / (height_m**2), 1)


def bmi_category(bmi_value: float) -> str:
    """Standard WHO adult thresholds."""
    if bmi_value < 18.5:
        return "Underweight"
    if bmi_value < 25:
        return "Normal"
    if bmi_value < 30:
        return "Overweight"
    return "Obese"


@dataclass(frozen=True)
class NutritionTotals:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


def sum_nutrition(rows: list[tuple[float | None, float | None, float | None, float | None]]) -> NutritionTotals:
    """rows = list of (calories, protein_g, carbs_g, fat_g) from food_logs; None counts as 0."""
    return NutritionTotals(
        calories=sum(r[0] or 0 for r in rows),
        protein_g=sum(r[1] or 0 for r in rows),
        carbs_g=sum(r[2] or 0 for r in rows),
        fat_g=sum(r[3] or 0 for r in rows),
    )


def average_daily_nutrition(daily_totals: list[NutritionTotals], num_days: int) -> NutritionTotals:
    """Averages a list of per-day totals over num_days (days with no logs
    still count toward the denominator, giving a true weekly average)."""
    if num_days <= 0:
        return NutritionTotals(0, 0, 0, 0)
    return NutritionTotals(
        calories=round(sum(d.calories for d in daily_totals) / num_days, 1),
        protein_g=round(sum(d.protein_g for d in daily_totals) / num_days, 1),
        carbs_g=round(sum(d.carbs_g for d in daily_totals) / num_days, 1),
        fat_g=round(sum(d.fat_g for d in daily_totals) / num_days, 1),
    )


def calendar_heat_color(value: float, max_value: float) -> str:
    """A deterministic background color for a calendar cell: intensity
    scales with value relative to the month's max (no data = neutral)."""
    if value <= 0 or max_value <= 0:
        return "#eef0f3"
    intensity = min(value / max_value, 1.0)
    lightness = round(92 - intensity * 48)
    return f"hsl(214, 65%, {lightness}%)"


def render_progression_svg(points: list[tuple[date, float]], width: int = 420, height: int = 140) -> str:
    """A minimal inline line chart -- no JS charting library needed."""
    if len(points) < 2:
        return ""

    pad = 24
    weights = [w for _, w in points]
    lo, hi = min(weights), max(weights)
    if hi == lo:
        hi = lo + 1  # avoid a divide-by-zero flat line

    n = len(points)

    def coords(i: int, w: float) -> tuple[float, float]:
        x = pad + (i / (n - 1)) * (width - 2 * pad)
        y = height - pad - ((w - lo) / (hi - lo)) * (height - 2 * pad)
        return x, y

    poly_points = " ".join(f"{x:.1f},{y:.1f}" for i, (_, w) in enumerate(points) for x, y in [coords(i, w)])
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#2563eb" />'
        for i, (_, w) in enumerate(points)
        for x, y in [coords(i, w)]
    )
    first_date, last_date = points[0][0], points[-1][0]

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{poly_points}" fill="none" stroke="#2563eb" stroke-width="2" />'
        f"{dots}"
        f'<text x="{pad}" y="{height - 4}" font-size="11" fill="#6b7280">{first_date}</text>'
        f'<text x="{width - pad}" y="{height - 4}" font-size="11" fill="#6b7280" text-anchor="end">{last_date}</text>'
        f'<text x="{pad}" y="12" font-size="11" fill="#6b7280">{hi:g}kg</text>'
        f'<text x="{pad}" y="{height - pad + 12}" font-size="11" fill="#6b7280">{lo:g}kg</text>'
        f"</svg>"
    )
