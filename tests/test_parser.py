from datetime import date, timedelta

import pytest

from app.parser import MealItem, ParseError, ParsedBodyMetric, ParsedFoodLog, ParsedWorkout, parse_quick_entry


def test_parse_weight_simple():
    result = parse_quick_entry("weight 72.4")
    assert isinstance(result, ParsedBodyMetric)
    assert result.weight_kg == 72.4
    assert result.body_fat_pct is None
    assert result.date == date.today()


def test_parse_weight_with_bodyfat():
    result = parse_quick_entry("weight 72.4 18%")
    assert result.weight_kg == 72.4
    assert result.body_fat_pct == 18.0


def test_parse_weight_short_form():
    result = parse_quick_entry("w 80")
    assert result.weight_kg == 80.0


def test_parse_weight_yesterday():
    result = parse_quick_entry("weight 72.4 yesterday")
    assert result.date == date.today() - timedelta(days=1)


def test_parse_weight_out_of_range():
    with pytest.raises(ParseError):
        parse_quick_entry("weight 5")


def test_parse_workout_with_weights():
    result = parse_quick_entry("bench 60x10 60x8 55x10")
    assert isinstance(result, ParsedWorkout)
    assert result.exercise_name == "bench"
    assert result.sets == [(60.0, 10), (60.0, 8), (55.0, 10)]


def test_parse_workout_bodyweight():
    result = parse_quick_entry("pullups x10 x8 x6")
    assert result.exercise_name == "pullups"
    assert result.sets == [(None, 10), (None, 8), (None, 6)]


def test_parse_workout_multiword_exercise():
    result = parse_quick_entry("overhead press 40x8 40x8")
    assert result.exercise_name == "overhead press"
    assert result.sets == [(40.0, 8), (40.0, 8)]


def test_parse_food_basic():
    result = parse_quick_entry("food chicken salad")
    assert isinstance(result, ParsedFoodLog)
    assert result.description == "chicken salad"
    assert result.calories is None


def test_parse_food_with_macros():
    result = parse_quick_entry("food chicken salad cal 450 protein 35g")
    assert result.description == "chicken salad"
    assert result.calories == 450.0
    assert result.protein_g == 35.0


def test_parse_food_alias_ate():
    result = parse_quick_entry("ate 2 eggs and toast on 2026-01-15")
    assert result.description == "2 eggs and toast"
    assert result.date == date(2026, 1, 15)


def test_parse_meal_log_simple():
    result = parse_quick_entry("breakfast 2 eggs 1 banana 1 apple")
    assert result.meal_type == "breakfast"
    assert result.items == [
        MealItem(quantity=2, unit=None, food_name="eggs"),
        MealItem(quantity=1, unit=None, food_name="banana"),
        MealItem(quantity=1, unit=None, food_name="apple"),
    ]


def test_parse_meal_log_with_units_and_commas():
    result = parse_quick_entry("after breakfast 100g yogabar oats, 250ml milk, 2 spoon peanut butter")
    assert result.meal_type == "after breakfast"
    assert result.items == [
        MealItem(quantity=100, unit="g", food_name="yogabar oats"),
        MealItem(quantity=250, unit="ml", food_name="milk"),
        MealItem(quantity=2, unit="spoon", food_name="peanut butter"),
    ]


def test_parse_meal_log_bowl_unit():
    result = parse_quick_entry("lunch 2 bowl rice 1 bowl dal 1 bowl green veggies")
    assert result.meal_type == "lunch"
    assert result.items == [
        MealItem(quantity=2, unit="bowl", food_name="rice"),
        MealItem(quantity=1, unit="bowl", food_name="dal"),
        MealItem(quantity=1, unit="bowl", food_name="green veggies"),
    ]


def test_parse_unrecognized_raises():
    with pytest.raises(ParseError):
        parse_quick_entry("blah blah nothing useful")


def test_parse_empty_raises():
    with pytest.raises(ParseError):
        parse_quick_entry("   ")
