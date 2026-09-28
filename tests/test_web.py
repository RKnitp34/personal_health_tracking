import pytest

from app.db import engine
from app.models import Base
from app.web import create_app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_loads(client):
    response = client.get("/")
    assert response.status_code == 200


def test_add_weight_entry(client):
    response = client.post("/entries", data={"text": "weight 72.4"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"72.4" in response.data


def test_add_workout_entry(client):
    response = client.post("/entries", data={"text": "bench 60x10 60x8"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"bench" in response.data


def test_add_food_entry(client):
    response = client.post(
        "/entries", data={"text": "food chicken salad cal 450 protein 35"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"chicken salad" in response.data


def test_invalid_entry_shows_error(client):
    response = client.post("/entries", data={"text": "gibberish text here"})
    assert response.status_code == 200
    assert b"Couldn&#39;t understand" in response.data or b"Couldn't understand" in response.data


def test_duplicate_weight_entry_is_flagged(client):
    client.post("/entries", data={"text": "weight 72.4"}, follow_redirects=True)
    response = client.post("/entries", data={"text": "weight 72.4"})
    assert response.status_code == 200
    assert b"Possible duplicate" in response.data


def test_duplicate_can_be_forced(client):
    client.post("/entries", data={"text": "weight 72.4"}, follow_redirects=True)
    response = client.post(
        "/entries", data={"text": "weight 72.4", "force": "1"}, follow_redirects=True
    )
    assert response.status_code == 200
    index = client.get("/")
    assert index.data.count(b"Weight: 72.4kg") == 2


def test_edit_body_metric(client):
    client.post("/entries", data={"text": "weight 72.4"}, follow_redirects=True)
    index = client.get("/")
    assert b"/entries/body/1/edit" in index.data

    response = client.post(
        "/entries/body/1/edit",
        data={"date": "2026-01-01", "weight_kg": "75.0", "body_fat_pct": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"75" in response.data


def test_delete_food_entry(client):
    client.post("/entries", data={"text": "food leftover curry"}, follow_redirects=True)
    response = client.post("/entries/food/1/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"leftover curry" not in response.data
    assert b"Nothing logged yet" in response.data


def test_add_food_to_database(client):
    response = client.post(
        "/foods",
        data={"name": "eggs", "unit": "piece", "calories": "70", "protein_g": "6", "carbs_g": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"eggs" in response.data
    assert b"70" in response.data


def test_meal_log_resolves_known_foods(client):
    client.post(
        "/foods", data={"name": "eggs", "unit": "piece", "calories": "70", "protein_g": "6", "carbs_g": ""}
    )
    client.post(
        "/foods", data={"name": "milk", "unit": "100ml", "calories": "60", "protein_g": "3", "carbs_g": "5"}
    )
    response = client.post(
        "/entries", data={"text": "breakfast 2 eggs 250ml milk"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"[breakfast]" in response.data
    # 2 eggs = 140 cal, 250ml milk = 150 cal -> 290
    assert b"290" in response.data


def test_meal_log_reports_unmatched_food(client):
    response = client.post(
        "/entries", data={"text": "lunch 1 bowl mystery food"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Not found" in response.data


def test_dashboard_loads_with_no_data(client):
    response = client.get("/dashboard")
    assert response.status_code == 200


def test_profile_update_and_bmi_on_dashboard(client):
    client.post("/profile", data={"height_cm": "175", "target_weight_kg": "68"}, follow_redirects=True)
    client.post("/entries", data={"text": "weight 70"}, follow_redirects=True)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"22.9" in response.data  # bmi(70, 175)
    assert b"68" in response.data  # target weight


def test_body_page_shows_weight_history_and_bmi(client):
    client.post("/profile", data={"height_cm": "175", "target_weight_kg": ""}, follow_redirects=True)
    client.post("/entries", data={"text": "weight 70"}, follow_redirects=True)
    response = client.get("/body")
    assert response.status_code == 200
    assert b"70" in response.data
    assert b"BMI 22.9" in response.data


def test_nutrition_page_shows_daily_totals(client):
    client.post("/foods", data={"name": "eggs", "unit": "piece", "calories": "70", "protein_g": "6", "carbs_g": ""})
    client.post("/entries", data={"text": "breakfast 2 eggs"}, follow_redirects=True)
    response = client.get("/nutrition")
    assert response.status_code == 200
    assert b"140" in response.data  # today's calories
    assert b"breakfast" in response.data


def test_calendar_loads_current_month(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b"cal-grid" in response.data


def test_calendar_shows_logged_day_data(client):
    client.post("/foods", data={"name": "eggs", "unit": "piece", "calories": "70", "protein_g": "6", "carbs_g": ""})
    client.post("/entries", data={"text": "breakfast 2 eggs"}, follow_redirects=True)
    client.post("/entries", data={"text": "weight 72.5"}, follow_redirects=True)

    from datetime import date

    today = date.today()
    response = client.get(f"/calendar?year={today.year}&month={today.month}")
    assert response.status_code == 200
    assert b"140 cal" in response.data
    assert b"72.5kg" in response.data


def test_calendar_navigation_links(client):
    response = client.get("/calendar?year=2026&month=6")
    assert response.status_code == 200
    assert b"year=2026&amp;month=5" in response.data
    assert b"year=2026&amp;month=7" in response.data


def test_manifest_json(client):
    response = client.get("/manifest.json")
    assert response.status_code == 200
    data = response.get_json()
    assert data["name"] == "Health Tracker"
    assert data["display"] == "standalone"


def test_calendar_day_detail_shows_logged_data(client):
    client.post("/foods", data={"name": "eggs", "unit": "piece", "calories": "70", "protein_g": "6", "carbs_g": ""})
    client.post("/entries", data={"text": "breakfast 2 eggs"}, follow_redirects=True)
    client.post("/entries", data={"text": "weight 72.5"}, follow_redirects=True)
    client.post("/entries", data={"text": "bench 60x10"}, follow_redirects=True)

    from datetime import date

    today = date.today().isoformat()
    response = client.get(f"/calendar/{today}")
    assert response.status_code == 200
    assert b"72.5kg" in response.data
    assert b"eggs" in response.data
    assert b"bench" in response.data


def test_calendar_day_invalid_date_redirects(client):
    response = client.get("/calendar/not-a-date", follow_redirects=True)
    assert response.status_code == 200
    assert b"cal-grid" in response.data


def test_calendar_page_links_to_day_detail(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b"/calendar/" in response.data


def test_dashboard_shows_workout_and_pr_sections(client):
    client.post("/entries", data={"text": "bench 60x10 60x8"}, follow_redirects=True)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"bench" in response.data
    assert b"1RM" in response.data


def test_exercises_list_and_detail(client):
    client.post("/entries", data={"text": "bench 60x10 60x8"}, follow_redirects=True)
    client.post("/entries", data={"text": "bench 65x8 65x6"}, follow_redirects=True)

    list_response = client.get("/exercises")
    assert b"bench" in list_response.data

    detail_response = client.get("/exercises/bench")
    assert detail_response.status_code == 200
    assert b"Current best" in detail_response.data
    assert b"65.0kg" in detail_response.data or b"65kg" in detail_response.data


def test_exercise_detail_unknown_redirects(client):
    response = client.get("/exercises/nonexistent", follow_redirects=True)
    assert response.status_code == 200
    assert b"No history" in response.data


def test_edit_workout_set(client):
    client.post("/entries", data={"text": "bench 60x10"}, follow_redirects=True)
    response = client.post(
        "/sets/1/update", data={"weight_kg": "65", "reps": "8"}, follow_redirects=True
    )
    assert response.status_code == 200
