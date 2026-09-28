from datetime import date

from app.analytics import (
    NutritionTotals,
    SetRecord,
    average_daily_nutrition,
    best_estimated_1rm,
    best_reps_by_weight,
    best_set,
    bmi,
    bmi_category,
    estimated_1rm,
    previous_best,
    progression_by_date,
    render_progression_svg,
    sum_nutrition,
    total_volume,
    weekly_volume,
)

RECORDS = [
    SetRecord(date=date(2026, 1, 1), weight_kg=60, reps=10, session_id=1),
    SetRecord(date=date(2026, 1, 1), weight_kg=60, reps=8, session_id=1),
    SetRecord(date=date(2026, 1, 8), weight_kg=65, reps=8, session_id=2),
    SetRecord(date=date(2026, 1, 8), weight_kg=65, reps=6, session_id=2),
    SetRecord(date=date(2026, 1, 15), weight_kg=65, reps=10, session_id=3),
]


def test_estimated_1rm_epley():
    assert estimated_1rm(100, 10) == 133.3
    assert estimated_1rm(100, 0) == 100


def test_total_volume():
    assert total_volume(RECORDS) == 60 * 10 + 60 * 8 + 65 * 8 + 65 * 6 + 65 * 10


def test_best_set_picks_heaviest_then_most_reps():
    b = best_set(RECORDS)
    assert b.weight_kg == 65
    assert b.reps == 10
    assert b.date == date(2026, 1, 15)


def test_previous_best_excludes_current_and_later():
    current = best_set(RECORDS)
    prev = previous_best(RECORDS, current)
    assert prev.date == date(2026, 1, 8)
    assert prev.weight_kg == 65
    assert prev.reps == 8


def test_best_reps_by_weight():
    result = dict(best_reps_by_weight(RECORDS))
    assert result[60] == 10
    assert result[65] == 10


def test_best_estimated_1rm():
    est, rec = best_estimated_1rm(RECORDS)
    assert rec.weight_kg == 65
    assert rec.reps == 10
    assert est == estimated_1rm(65, 10)


def test_weekly_volume_grouping():
    weeks = weekly_volume(RECORDS)
    assert len(weeks) == 3
    labels = [w for w, _ in weeks]
    assert labels == sorted(labels)


def test_progression_by_date():
    prog = progression_by_date(RECORDS)
    assert prog == [
        (date(2026, 1, 1), 60),
        (date(2026, 1, 8), 65),
        (date(2026, 1, 15), 65),
    ]


def test_render_svg_returns_empty_for_single_point():
    assert render_progression_svg([(date(2026, 1, 1), 60)]) == ""


def test_render_svg_returns_markup_for_multiple_points():
    svg = render_progression_svg(progression_by_date(RECORDS))
    assert svg.startswith("<svg")
    assert "polyline" in svg


def test_no_weight_sets_excluded_from_best():
    bodyweight_only = [SetRecord(date=date(2026, 1, 1), weight_kg=None, reps=10, session_id=1)]
    assert best_set(bodyweight_only) is None
    assert best_estimated_1rm(bodyweight_only) is None


def test_bmi_calculation():
    assert bmi(70, 175) == 22.9


def test_bmi_category_thresholds():
    assert bmi_category(17) == "Underweight"
    assert bmi_category(22) == "Normal"
    assert bmi_category(27) == "Overweight"
    assert bmi_category(32) == "Obese"


def test_sum_nutrition_treats_none_as_zero():
    rows = [(400, 30, None, None), (200, None, 20, 5)]
    totals = sum_nutrition(rows)
    assert totals == NutritionTotals(calories=600, protein_g=30, carbs_g=20, fat_g=5)


def test_average_daily_nutrition_counts_days_with_no_logs():
    daily = [NutritionTotals(calories=1400, protein_g=100, carbs_g=100, fat_g=40)]
    avg = average_daily_nutrition(daily, num_days=7)
    assert avg.calories == round(1400 / 7, 1)
    assert avg.protein_g == round(100 / 7, 1)
