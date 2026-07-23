from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import WorkshopConfig
from app.server import create_app
from app.state import WorkshopState
from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 7, 0, tzinfo=timezone.utc)


def fake_evaluate(reading, stage, calibration, rules, content):
    return []


@pytest.fixture
def state():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    workshop_state = WorkshopState.build(
        connection, config, "config.json", evaluate_fn=fake_evaluate
    )
    yield workshop_state
    connection.close()


@pytest.fixture
def client(state):
    return TestClient(create_app(state))


def test_api_state_returns_null_reading_before_any_polling(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    body = response.json()
    assert body["sensors"]["probe-a"]["reading"] is None
    assert body["sensors"]["probe-a"]["advice"] == []
    assert body["simulated"] is False


def test_api_state_reports_simulated_true_once_a_sim_reading_exists(client, state):
    db.insert_reading(
        state.con,
        Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SIM),
    )
    body = client.get("/api/state").json()
    assert body["simulated"] is True
    assert body["sensors"]["probe-a"]["reading"]["source"] == "sim"


def test_api_history_returns_points_oldest_first(client, state):
    db.insert_readings(
        state.con,
        [
            Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SEED),
            Reading(
                NOW + timedelta(minutes=1),
                "probe-a",
                {"moisture": 2.0},
                source=Reading.SOURCE_SEED,
            ),
        ],
    )
    body = client.get(
        "/api/history", params={"sensor_id": "probe-a", "metric": "moisture"}
    ).json()
    assert [p["value"] for p in body["points"]] == [1.0, 2.0]
    assert body["points"][0]["source"] == "seed"


def test_api_history_rejects_unknown_sensor(client):
    response = client.get("/api/history", params={"sensor_id": "nobody", "metric": "moisture"})
    assert response.status_code == 404


def test_api_state_growth_stage_and_language_come_from_config(client):
    body = client.get("/api/state").json()
    assert body["growth_stage"] == "land_preparation"
    assert body["language"] == "id"
