"""Mobile-friendly web app for quick data entry.

One text box for natural/shorthand entry (see app.parser), plus a recent
entries list with simple edit/delete forms for corrections.
"""
from __future__ import annotations

import calendar as calendar_module
from datetime import date, datetime, timedelta, UTC

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from app import analytics
from app.config import SECRET_KEY
from app.db import get_session, init_db
from app.parser import ParseError, ParsedBodyMetric, ParsedFoodLog, ParsedMealLog, ParsedWorkout, parse_quick_entry
from app import repository as repo


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    init_db()

    @app.route("/")
    def index():
        with get_session() as session:
            entries = repo.list_recent_entries(session)
        return render_template("index.html", entries=entries)

    @app.route("/entries", methods=["POST"])
    def add_entry():
        text = request.form.get("text", "")
        force = request.form.get("force") == "1"

        try:
            parsed = parse_quick_entry(text)
        except ParseError as exc:
            flash(str(exc), "error")
            return render_template("index.html", entries=_recent(), prefill=text)

        with get_session() as session:
            if isinstance(parsed, ParsedBodyMetric):
                existing = repo.find_recent_duplicate_body_metric(session, parsed)
                if existing and not force:
                    return _confirm_duplicate(text, f"Weight {existing.weight_kg:g}kg", existing.created_at)
                repo.create_body_metric(session, parsed)
                flash(f"Logged weight: {parsed.weight_kg:g}kg", "success")

            elif isinstance(parsed, ParsedWorkout):
                existing = repo.find_recent_duplicate_workout(session, parsed)
                if existing and not force:
                    return _confirm_duplicate(text, f"Workout '{existing.name}'", existing.created_at)
                repo.create_workout(session, parsed)
                set_count = len(parsed.sets)
                flash(f"Logged {parsed.exercise_name}: {set_count} set(s)", "success")

            elif isinstance(parsed, ParsedFoodLog):
                existing = repo.find_recent_duplicate_food_log(session, parsed)
                if existing and not force:
                    return _confirm_duplicate(text, f"Food '{existing.description}'", existing.created_at)
                repo.create_food_log(session, parsed)
                flash(f"Logged food: {parsed.description}", "success")

            elif isinstance(parsed, ParsedMealLog):
                resolution = repo.resolve_meal_items(session, parsed.items)
                existing = repo.find_recent_duplicate_meal_log(session, parsed, resolution.description)
                if existing and not force:
                    return _confirm_duplicate(
                        text, f"{existing.meal_type} '{existing.description}'", existing.created_at
                    )
                repo.create_meal_log(session, parsed, resolution)
                msg = f"Logged {parsed.meal_type}: {resolution.description} ({resolution.calories:g} cal)"
                flash(msg, "success")
                if resolution.unmatched:
                    flash(
                        "Not found, so skipped: " + ", ".join(resolution.unmatched)
                        + ". Add them on the Foods page to include them next time.",
                        "warning",
                    )

        return redirect(url_for("index"))

    @app.route("/dashboard")
    def dashboard():
        today = date.today()
        week_ago = today - timedelta(days=6)

        with get_session() as session:
            today_totals = repo.get_daily_nutrition(session, today)
            weekly_avg = repo.get_weekly_nutrition_average(session, today)
            latest_weight = repo.get_latest_weight(session)
            profile = repo.get_profile(session)
            weight_history = repo.get_weight_history(session, limit=12)
            todays_workouts = repo.get_todays_workout_sessions(session, today)
            recent_sessions = repo.get_recent_workout_sessions(session, limit=5)
            weekly_volume = repo.get_workout_volume_since(session, week_ago)
            recent_prs = repo.get_recent_prs(session, limit=5)
            recent_activity = repo.list_recent_entries(session, limit=8)

        current_bmi = None
        if latest_weight and profile and profile.height_cm:
            current_bmi = analytics.bmi(latest_weight.weight_kg, profile.height_cm)

        weight_trend_svg = analytics.render_progression_svg([(m.date, m.weight_kg) for m in weight_history])

        session_summaries = [
            (s, sum((es.weight_kg or 0) * es.reps for es in s.exercise_sets)) for s in recent_sessions
        ]

        return render_template(
            "dashboard.html",
            today_totals=today_totals,
            weekly_avg=weekly_avg,
            latest_weight=latest_weight,
            target_weight_kg=profile.target_weight_kg if profile else None,
            current_bmi=current_bmi,
            bmi_category=analytics.bmi_category(current_bmi) if current_bmi else None,
            weight_trend_svg=weight_trend_svg,
            todays_workouts=todays_workouts,
            session_summaries=session_summaries,
            weekly_volume=weekly_volume,
            recent_prs=recent_prs,
            estimated_1rm=analytics.estimated_1rm,
            recent_activity=recent_activity,
        )

    @app.route("/calendar")
    def calendar_view():
        today = date.today()
        try:
            year = int(request.args.get("year", today.year))
            month = int(request.args.get("month", today.month))
        except ValueError:
            year, month = today.year, today.month

        with get_session() as session:
            summary = repo.get_month_summary(session, year, month)

        weeks = calendar_module.monthcalendar(year, month)
        max_calories = max((s.calories for s in summary.values()), default=0)

        grid = []
        for week in weeks:
            row = []
            for day_num in week:
                if day_num == 0:
                    row.append(None)
                    continue
                cell_date = date(year, month, day_num)
                day_summary = summary.get(cell_date)
                row.append(
                    {
                        "day": day_num,
                        "date": cell_date,
                        "summary": day_summary,
                        "color": analytics.calendar_heat_color(
                            day_summary.calories if day_summary else 0, max_calories
                        ),
                        "is_today": cell_date == today,
                    }
                )
            grid.append(row)

        prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
        next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

        return render_template(
            "calendar.html",
            grid=grid,
            month_label=f"{calendar_module.month_name[month]} {year}",
            prev_year=prev_year,
            prev_month=prev_month,
            next_year=next_year,
            next_month=next_month,
        )

    @app.route("/profile", methods=["GET", "POST"])
    def profile():
        with get_session() as session:
            if request.method == "POST":
                try:
                    height_raw = request.form.get("height_cm", "").strip()
                    target_raw = request.form.get("target_weight_kg", "").strip()
                    height_cm = float(height_raw) if height_raw else None
                    target_weight_kg = float(target_raw) if target_raw else None
                except ValueError:
                    flash("Please enter valid numbers.", "error")
                    return render_template("profile.html", profile=repo.get_profile(session))

                repo.upsert_profile(session, height_cm=height_cm, target_weight_kg=target_weight_kg)
                flash("Profile updated.", "success")
                return redirect(url_for("dashboard"))

            return render_template("profile.html", profile=repo.get_profile(session))

    @app.route("/body")
    def body():
        with get_session() as session:
            history = repo.get_weight_history(session, limit=30)
            profile_row = repo.get_profile(session)

        rows = []
        for m in reversed(history):  # most recent first for the table
            row_bmi = analytics.bmi(m.weight_kg, profile_row.height_cm) if profile_row and profile_row.height_cm else None
            rows.append((m, row_bmi))

        trend_svg = analytics.render_progression_svg([(m.date, m.weight_kg) for m in history])

        return render_template(
            "body.html",
            rows=rows,
            trend_svg=trend_svg,
            target_weight_kg=profile_row.target_weight_kg if profile_row else None,
        )

    @app.route("/nutrition")
    def nutrition():
        with get_session() as session:
            meals = repo.get_meal_history(session, limit=30)
            today = date.today()
            today_totals = repo.get_daily_nutrition(session, today)
            weekly_avg = repo.get_weekly_nutrition_average(session, today)

        return render_template(
            "nutrition.html", meals=meals, today_totals=today_totals, weekly_avg=weekly_avg
        )

    @app.route("/exercises")
    def exercises():
        with get_session() as session:
            names = repo.list_exercise_names(session)
        return render_template("exercises.html", names=names)

    @app.route("/exercises/<name>")
    def exercise_detail(name: str):
        with get_session() as session:
            records = repo.get_exercise_history(session, name)
            recent_sessions = repo.get_exercise_sessions(session, name)

        if not records:
            flash(f"No history for '{name}' yet.", "error")
            return redirect(url_for("exercises"))

        current = analytics.best_set(records)
        previous = analytics.previous_best(records, current) if current else None
        best_1rm = analytics.best_estimated_1rm(records)
        chart_svg = analytics.render_progression_svg(analytics.progression_by_date(records))

        return render_template(
            "exercise_detail.html",
            name=name,
            recent_sessions=recent_sessions,
            total_sets=len(records),
            total_volume=analytics.total_volume(records),
            current_best=current,
            previous_best=previous,
            best_1rm=best_1rm,
            best_reps_by_weight=analytics.best_reps_by_weight(records),
            weekly_volume=list(reversed(analytics.weekly_volume(records)))[:8],
            chart_svg=chart_svg,
            estimated_1rm=analytics.estimated_1rm,
        )

    @app.route("/calendar/<date_str>")
    def calendar_day(date_str: str):
        try:
            day = date.fromisoformat(date_str)
        except ValueError:
            flash("Invalid date.", "error")
            return redirect(url_for("calendar_view"))

        with get_session() as session:
            weights = repo.get_body_metrics_on_date(session, day)
            foods = repo.get_food_logs_on_date(session, day)
            workouts = repo.get_todays_workout_sessions(session, day)

        return render_template(
            "calendar_day.html",
            day=day,
            weights=weights,
            foods=foods,
            workouts=workouts,
            prev_day=day - timedelta(days=1),
            next_day=day + timedelta(days=1),
        )

    @app.route("/manifest.json")
    def manifest():
        return jsonify(
            {
                "name": "Health Tracker",
                "short_name": "Health",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#f7f8fa",
                "theme_color": "#2563eb",
                "icons": [
                    {"src": url_for("static", filename="icon.svg"), "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}
                ],
            }
        )

    @app.route("/foods", methods=["GET", "POST"])
    def foods():
        with get_session() as session:
            if request.method == "POST":
                try:
                    name = request.form["name"].strip()
                    unit = request.form["unit"].strip()
                    calories = float(request.form["calories"])
                    protein_raw = request.form.get("protein_g", "").strip()
                    carbs_raw = request.form.get("carbs_g", "").strip()
                    protein_g = float(protein_raw) if protein_raw else None
                    carbs_g = float(carbs_raw) if carbs_raw else None
                    if not name:
                        raise ValueError("empty name")
                except ValueError:
                    flash("Please check the values entered.", "error")
                    return render_template("foods.html", foods=repo.list_foods(session))

                if repo.find_food_by_name(session, name):
                    flash(f"'{name}' already exists — edit it instead of adding a duplicate.", "error")
                    return render_template("foods.html", foods=repo.list_foods(session))

                repo.create_food(
                    session, name=name, unit=unit, calories=calories, protein_g=protein_g, carbs_g=carbs_g
                )
                flash(f"Added '{name}'.", "success")
                return redirect(url_for("foods"))

            return render_template("foods.html", foods=repo.list_foods(session))

    @app.route("/foods/<int:food_id>/edit", methods=["GET", "POST"])
    def edit_food(food_id: int):
        with get_session() as session:
            food = repo.get_food(session, food_id)
            if not food:
                flash("Food not found.", "error")
                return redirect(url_for("foods"))

            if request.method == "POST":
                try:
                    name = request.form["name"].strip()
                    unit = request.form["unit"].strip()
                    calories = float(request.form["calories"])
                    protein_raw = request.form.get("protein_g", "").strip()
                    carbs_raw = request.form.get("carbs_g", "").strip()
                    protein_g = float(protein_raw) if protein_raw else None
                    carbs_g = float(carbs_raw) if carbs_raw else None
                    if not name:
                        raise ValueError("empty name")
                except ValueError:
                    flash("Please check the values entered.", "error")
                    return render_template("edit_food_item.html", food=food)

                repo.update_food(
                    session, food, name=name, unit=unit, calories=calories, protein_g=protein_g, carbs_g=carbs_g
                )
                flash(f"Updated '{name}'.", "success")
                return redirect(url_for("foods"))

            return render_template("edit_food_item.html", food=food)

    @app.route("/foods/<int:food_id>/delete", methods=["POST"])
    def delete_food_item(food_id: int):
        with get_session() as session:
            food = repo.get_food(session, food_id)
            if food:
                repo.delete_food(session, food)
                flash("Deleted.", "success")
        return redirect(url_for("foods"))

    @app.route("/entries/<entry_type>/<int:entry_id>/edit", methods=["GET", "POST"])
    def edit_entry(entry_type: str, entry_id: int):
        with get_session() as session:
            if entry_type == "body":
                return _edit_body(session, entry_id)
            if entry_type == "workout":
                return _edit_workout(session, entry_id)
            if entry_type == "food":
                return _edit_food(session, entry_id)
        flash("Unknown entry type.", "error")
        return redirect(url_for("index"))

    @app.route("/entries/<entry_type>/<int:entry_id>/delete", methods=["POST"])
    def delete_entry(entry_type: str, entry_id: int):
        with get_session() as session:
            if entry_type == "body":
                metric = repo.get_body_metric(session, entry_id)
                if metric:
                    repo.delete_body_metric(session, metric)
            elif entry_type == "workout":
                workout = repo.get_workout(session, entry_id)
                if workout:
                    repo.delete_workout(session, workout)
            elif entry_type == "food":
                food = repo.get_food_log(session, entry_id)
                if food:
                    repo.delete_food_log(session, food)
        flash("Deleted.", "success")
        return redirect(url_for("index"))

    @app.route("/sets/<int:set_id>/update", methods=["POST"])
    def update_set(set_id: int):
        return _update_set(set_id)

    @app.route("/sets/<int:set_id>/delete", methods=["POST"])
    def delete_set(set_id: int):
        with get_session() as session:
            from app.models import ExerciseSet

            exercise_set = session.get(ExerciseSet, set_id)
            if exercise_set:
                workout_id = exercise_set.workout_session_id
                repo.delete_workout_set(session, exercise_set)
                flash("Set deleted.", "success")
                return redirect(url_for("edit_entry", entry_type="workout", entry_id=workout_id))
        flash("Set not found.", "error")
        return redirect(url_for("index"))

    def _update_set(set_id: int):
        from app.models import ExerciseSet

        with get_session() as session:
            exercise_set = session.get(ExerciseSet, set_id)
            if not exercise_set:
                flash("Set not found.", "error")
                return redirect(url_for("index"))
            try:
                reps = int(request.form["reps"])
                weight_raw = request.form.get("weight_kg", "").strip()
                weight_kg = float(weight_raw) if weight_raw else None
            except ValueError:
                flash("Reps/weight must be numbers.", "error")
                return redirect(url_for("edit_entry", entry_type="workout", entry_id=exercise_set.workout_session_id))

            workout_id = exercise_set.workout_session_id
            repo.update_workout_set(session, exercise_set, weight_kg=weight_kg, reps=reps)
            flash("Set updated.", "success")
            return redirect(url_for("edit_entry", entry_type="workout", entry_id=workout_id))

    def _recent():
        with get_session() as session:
            return repo.list_recent_entries(session)

    def _confirm_duplicate(text: str, existing_summary: str, existing_created_at: datetime):
        now = datetime.now(UTC)
        created_at = existing_created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        seconds_ago = int((now - created_at).total_seconds())
        return render_template(
            "confirm_duplicate.html",
            text=text,
            existing_summary=existing_summary,
            seconds_ago=max(seconds_ago, 0),
        )

    def _edit_body(session, entry_id: int):
        metric = repo.get_body_metric(session, entry_id)
        if not metric:
            flash("Entry not found.", "error")
            return redirect(url_for("index"))

        if request.method == "POST":
            try:
                entry_date = date.fromisoformat(request.form["date"])
                weight_kg = float(request.form["weight_kg"])
                bodyfat_raw = request.form.get("body_fat_pct", "").strip()
                body_fat_pct = float(bodyfat_raw) if bodyfat_raw else None
            except ValueError:
                flash("Please check the values entered.", "error")
                return render_template("edit_body.html", metric=metric)

            repo.update_body_metric(session, metric, date=entry_date, weight_kg=weight_kg, body_fat_pct=body_fat_pct)
            flash("Weight entry updated.", "success")
            return redirect(url_for("index"))

        return render_template("edit_body.html", metric=metric)

    def _edit_workout(session, entry_id: int):
        workout = repo.get_workout(session, entry_id)
        if not workout:
            flash("Entry not found.", "error")
            return redirect(url_for("index"))

        if request.method == "POST":
            try:
                entry_date = date.fromisoformat(request.form["date"])
                name = request.form["name"].strip()
                if not name:
                    raise ValueError("empty name")
            except ValueError:
                flash("Please check the values entered.", "error")
                return render_template("edit_workout.html", workout=workout)

            repo.update_workout_session(session, workout, date=entry_date, name=name)
            flash("Workout updated.", "success")
            return redirect(url_for("index"))

        return render_template("edit_workout.html", workout=workout)

    def _edit_food(session, entry_id: int):
        food = repo.get_food_log(session, entry_id)
        if not food:
            flash("Entry not found.", "error")
            return redirect(url_for("index"))

        if request.method == "POST":
            try:
                entry_date = date.fromisoformat(request.form["date"])
                description = request.form["description"].strip()
                if not description:
                    raise ValueError("empty description")
                cal_raw = request.form.get("calories", "").strip()
                calories = float(cal_raw) if cal_raw else None
                protein_raw = request.form.get("protein_g", "").strip()
                protein_g = float(protein_raw) if protein_raw else None
            except ValueError:
                flash("Please check the values entered.", "error")
                return render_template("edit_food.html", food=food)

            repo.update_food_log(
                session, food, date=entry_date, description=description, calories=calories, protein_g=protein_g
            )
            flash("Food entry updated.", "success")
            return redirect(url_for("index"))

        return render_template("edit_food.html", food=food)

    return app
