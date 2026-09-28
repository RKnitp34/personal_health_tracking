"""Lightweight, deterministic parser for quick natural-language entries.

Deliberately regex-based rather than LLM-based: entry formats are small and
fixed, so a parser is faster, free, and 100% predictable. Supported forms:

    weight 72.4
    weight 72.4 18%
    weight 72.4 yesterday
    bench 60x10 60x8 55x10
    pullups x10 x8 x6
    food chicken salad
    food chicken salad cal 450 protein 35g
    ate 2 eggs and toast on 2026-01-15

Anything else raises ParseError with a message suitable for showing the user.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta


class ParseError(ValueError):
    pass


@dataclass
class ParsedBodyMetric:
    date: date
    weight_kg: float
    body_fat_pct: float | None = None


@dataclass
class ParsedWorkout:
    date: date
    exercise_name: str
    sets: list[tuple[float | None, int]] = field(default_factory=list)  # (weight_kg, reps)


@dataclass
class ParsedFoodLog:
    date: date
    description: str
    calories: float | None = None
    protein_g: float | None = None


@dataclass
class MealItem:
    quantity: float
    unit: str | None  # None means "piece" (a plain count, e.g. "1 banana")
    food_name: str


@dataclass
class ParsedMealLog:
    date: date
    meal_type: str
    items: list[MealItem] = field(default_factory=list)


_DATE_ON_RE = re.compile(r"\bon\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_DATE_YESTERDAY_RE = re.compile(r"\byesterday\b", re.IGNORECASE)
_DATE_TODAY_RE = re.compile(r"\btoday\b", re.IGNORECASE)

_WEIGHT_CMD_RE = re.compile(
    r"^w(?:eight)?\s+(?P<weight>\d+(?:\.\d+)?)(?:\s+(?P<bodyfat>\d+(?:\.\d+)?)\s*%)?$",
    re.IGNORECASE,
)
_FOOD_CMD_RE = re.compile(r"^(?:food|ate|meal)\s+(?P<rest>.+)$", re.IGNORECASE)
_FOOD_CAL_RE = re.compile(r"\bcal(?:ories)?\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_FOOD_PROTEIN_RE = re.compile(r"\bprotein\s+(\d+(?:\.\d+)?)\s*g?\b", re.IGNORECASE)

_SET_TOKEN_RE = re.compile(r"(?:(?P<weight>\d+(?:\.\d+)?)x|x)(?P<reps>\d+)", re.IGNORECASE)

_MEAL_ITEM_UNITS = ("g", "ml", "bowl", "spoon", "cup", "katori")
_MEAL_ITEM_QTY_RE = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>" + "|".join(_MEAL_ITEM_UNITS) + r")?\b",
    re.IGNORECASE,
)

_WEIGHT_RANGE = (20.0, 400.0)
_BODYFAT_RANGE = (1.0, 70.0)
_SET_WEIGHT_RANGE = (0.0, 500.0)
_REPS_RANGE = (1, 200)
_CALORIES_RANGE = (0.0, 10000.0)
_PROTEIN_RANGE = (0.0, 1000.0)


def _validate_range(value: float, low: float, high: float, label: str) -> None:
    if not (low <= value <= high):
        raise ParseError(f"{label} {value:g} looks out of range ({low:g}-{high:g}).")


def _extract_date(text: str) -> tuple[str, date]:
    """Pull a trailing date hint out of the text, returning (remaining_text, date)."""
    today = date.today()

    match = _DATE_ON_RE.search(text)
    if match:
        remaining = (text[: match.start()] + text[match.end() :]).strip()
        try:
            parsed_date = date.fromisoformat(match.group(1))
        except ValueError as exc:
            raise ParseError(f"Couldn't understand date '{match.group(1)}'.") from exc
        return remaining, parsed_date

    if _DATE_YESTERDAY_RE.search(text):
        remaining = _DATE_YESTERDAY_RE.sub("", text).strip()
        return remaining, today - timedelta(days=1)

    if _DATE_TODAY_RE.search(text):
        remaining = _DATE_TODAY_RE.sub("", text).strip()
        return remaining, today

    return text, today


def _parse_weight(text: str, entry_date: date) -> ParsedBodyMetric:
    match = _WEIGHT_CMD_RE.match(text.strip())
    if not match:
        raise ParseError(
            "Couldn't understand weight entry. Try: 'weight 72.4' or 'weight 72.4 18%'."
        )
    weight_kg = float(match.group("weight"))
    _validate_range(weight_kg, *_WEIGHT_RANGE, "Weight")

    body_fat_pct = None
    if match.group("bodyfat"):
        body_fat_pct = float(match.group("bodyfat"))
        _validate_range(body_fat_pct, *_BODYFAT_RANGE, "Body fat %")

    return ParsedBodyMetric(date=entry_date, weight_kg=weight_kg, body_fat_pct=body_fat_pct)


def _parse_food(text: str, entry_date: date) -> ParsedFoodLog:
    match = _FOOD_CMD_RE.match(text.strip())
    if not match:
        raise ParseError("Couldn't understand food entry. Try: 'food chicken salad cal 450'.")
    rest = match.group("rest").strip()

    calories = None
    cal_match = _FOOD_CAL_RE.search(rest)
    if cal_match:
        calories = float(cal_match.group(1))
        _validate_range(calories, *_CALORIES_RANGE, "Calories")
        rest = _FOOD_CAL_RE.sub("", rest)

    protein_g = None
    protein_match = _FOOD_PROTEIN_RE.search(rest)
    if protein_match:
        protein_g = float(protein_match.group(1))
        _validate_range(protein_g, *_PROTEIN_RANGE, "Protein")
        rest = _FOOD_PROTEIN_RE.sub("", rest)

    description = re.sub(r"\s+", " ", rest).strip(" ,.")
    if not description:
        raise ParseError("Food entry needs a description, e.g. 'food chicken salad'.")

    return ParsedFoodLog(date=entry_date, description=description, calories=calories, protein_g=protein_g)


def _parse_workout(text: str, entry_date: date) -> ParsedWorkout:
    tokens = list(_SET_TOKEN_RE.finditer(text))
    if not tokens:
        raise ParseError(
            "Couldn't understand entry. Try: 'weight 72.4', 'bench 60x10 60x8', "
            "or 'food chicken salad cal 450'."
        )

    exercise_name = text[: tokens[0].start()].strip(" ,.")
    if not exercise_name:
        raise ParseError("Workout entry needs an exercise name, e.g. 'bench 60x10 60x8'.")

    sets: list[tuple[float | None, int]] = []
    for token in tokens:
        reps = int(token.group("reps"))
        _validate_range(reps, *_REPS_RANGE, "Reps")
        weight_raw = token.group("weight")
        weight_kg = None
        if weight_raw is not None:
            weight_kg = float(weight_raw)
            _validate_range(weight_kg, *_SET_WEIGHT_RANGE, "Set weight")
        sets.append((weight_kg, reps))

    return ParsedWorkout(date=entry_date, exercise_name=exercise_name, sets=sets)


def _parse_meal_log(text: str, entry_date: date) -> ParsedMealLog:
    matches = list(_MEAL_ITEM_QTY_RE.finditer(text))
    if not matches:
        raise ParseError(
            "Couldn't understand entry. Try: 'weight 72.4', 'bench 60x10 60x8', "
            "or 'breakfast 2 eggs 1 banana'."
        )

    meal_type = text[: matches[0].start()].strip(" ,.")
    if not meal_type:
        raise ParseError("Meal entry needs a meal name, e.g. 'breakfast 2 eggs 1 banana'.")

    items: list[MealItem] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        name = text[match.end() : end].strip(" ,.")
        if not name:
            raise ParseError(f"Missing food name after '{match.group(0)}'.")
        qty = float(match.group("qty"))
        unit = match.group("unit").lower() if match.group("unit") else None
        items.append(MealItem(quantity=qty, unit=unit, food_name=name))

    return ParsedMealLog(date=entry_date, meal_type=meal_type, items=items)


def parse_quick_entry(raw_text: str) -> ParsedBodyMetric | ParsedWorkout | ParsedFoodLog | ParsedMealLog:
    if not raw_text or not raw_text.strip():
        raise ParseError("Entry text is empty.")

    text, entry_date = _extract_date(raw_text.strip())
    text = text.strip()
    if not text:
        raise ParseError("Entry has a date but no actual data.")

    if re.match(r"^w(?:eight)?\s", text, re.IGNORECASE):
        return _parse_weight(text, entry_date)

    if re.match(r"^(?:food|ate|meal)\s", text, re.IGNORECASE):
        return _parse_food(text, entry_date)

    try:
        return _parse_workout(text, entry_date)
    except ParseError:
        return _parse_meal_log(text, entry_date)
