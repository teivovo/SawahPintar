from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import WorkshopConfig
from app.insights.permentan import load_permentan
from app.server import create_app
from app.state import WorkshopState
from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 13, 0, tzinfo=timezone.utc)
WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"


def fake_evaluate(reading, stage, calibration, rules, content):
    return []


@pytest.fixture
def state(tmp_path):
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    config_path = tmp_path / "config.json"
    config.save(config_path)
    workshop_state = WorkshopState.build(
        connection,
        config,
        config_path,
        evaluate_fn=fake_evaluate,
        permentan=load_permentan("data/permentan_2022.yaml"),
    )
    yield workshop_state
    connection.close()


@pytest.fixture
def client(state):
    return TestClient(create_app(state))


def test_operator_page_is_served(client):
    response = client.get("/operator")
    assert response.status_code == 200
    assert "Konsol Operator" in response.text


def test_load_ports_and_profiles_is_wrapped_in_try_catch_in_start():
    """A failing /api/ports must not kill every control on the operator
    console's recovery surface."""
    content = (WEB_DIR / "operator.js").read_text(encoding="utf-8")
    start_body = content.split("async function start() {", 1)[1]
    assert "try {" in start_body
    assert "await loadPortsAndProfiles();" in start_body
    try_block = start_body.split("try {", 1)[1].split("catch", 1)[0]
    assert "await loadPortsAndProfiles();" in try_block


def test_language_toggle_starts_from_the_real_current_language_not_a_hardcoded_default():
    content = (WEB_DIR / "operator.js").read_text(encoding="utf-8")
    assert 'let currentLanguage = "id";' not in content
    assert "function wireConfig(initialLanguage)" in content


def test_puts_button_surfaces_the_permentan_dose_when_one_is_returned():
    content = (WEB_DIR / "operator.js").read_text(encoding="utf-8")
    assert "data.phosphorus_dose" in content
    assert "p2o5_kg_per_ha" in content


def test_operator_console_is_never_linked_from_the_farmer_page():
    index_content = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert "/operator" not in index_content
    app_js_content = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "ctrlKey && event.altKey" in app_js_content


def test_list_ports_returns_a_list(client):
    response = client.get("/api/ports")
    assert response.status_code == 200
    assert isinstance(response.json()["ports"], list)


def test_list_profiles_finds_the_shipped_sn3002_profile(client):
    body = client.get("/api/profiles").json()
    keys = [entry["key"] for entry in body["profiles"]]
    assert "sn3002" in keys


def test_growth_stage_update_persists_and_is_reflected_in_state(client):
    response = client.post("/api/config", json={"growth_stage": "flowering"})
    assert response.status_code == 200
    assert client.get("/api/state").json()["growth_stage"] == "flowering"


def test_language_update_persists_and_is_reflected_in_state(client):
    response = client.post("/api/config", json={"language": "en"})
    assert response.status_code == 200
    assert client.get("/api/state").json()["language"] == "en"


def test_config_update_rejects_an_unknown_growth_stage(client):
    response = client.post("/api/config", json={"growth_stage": "harvest"})
    assert response.status_code == 422


def test_field_card_round_trips_through_the_endpoint(client):
    response = client.post(
        "/api/field-card",
        json={"variety": "Ciherang", "field_size_ha": 0.5, "water_source": "irigasi"},
    )
    assert response.status_code == 200
    assert response.json()["field_card"]["variety"] == "Ciherang"


def test_puts_result_is_recorded_against_the_latest_reading(client, state):
    db.insert_reading(
        state.con, Reading(NOW, "probe-a", {"conductivity": 640.0}, source=Reading.SOURCE_SIM)
    )
    response = client.post(
        "/api/puts",
        json={
            "nitrogen_class": "rendah",
            "phosphorus_class": "sedang",
            "potassium_class": "tinggi",
            "ph": 6.2,
        },
    )
    assert response.status_code == 200
    observations = response.json()["observations"]
    assert observations[-1]["conductivity"] == 640.0
    assert observations[-1]["nitrogen_class"] == "rendah"


def test_puts_result_includes_the_official_permentan_dose_for_the_entered_class(client, state):
    """Design spec 8.1: a dose must appear once the operator has entered
    PUTS status classes, sourced from Permentan 13 of 2022, never the
    probe."""
    db.insert_reading(
        state.con, Reading(NOW, "probe-a", {"conductivity": 640.0}, source=Reading.SOURCE_SIM)
    )
    response = client.post(
        "/api/puts",
        json={
            "nitrogen_class": "rendah",
            "phosphorus_class": "sedang",
            "potassium_class": "tinggi",
            "ph": 6.2,
        },
    )
    assert response.status_code == 200
    dose = response.json()["phosphorus_dose"]
    assert dose["status"] == "sedang"
    assert dose["p2o5_kg_per_ha"] == 27
    assert dose["sp36_kg_per_ha"] == 75
    assert "Permentan" in dose["source"]
    assert "PUTS" in dose["source"]


def test_puts_result_omits_the_dose_key_when_no_permentan_table_is_wired_in(client):
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    bare_state = WorkshopState.build(connection, config, "config.json", evaluate_fn=fake_evaluate)
    bare_client = TestClient(create_app(bare_state))

    response = bare_client.post(
        "/api/puts",
        json={"nitrogen_class": "rendah", "phosphorus_class": "sedang", "potassium_class": "tinggi"},
    )

    assert response.status_code == 200
    assert "phosphorus_dose" not in response.json()
    connection.close()


def test_puts_rejects_an_unrecognised_phosphorus_class_and_records_nothing(client, state):
    from app.observations import list_observations

    before = len(list_observations(state.con))

    response = client.post(
        "/api/puts",
        json={"nitrogen_class": "rendah", "phosphorus_class": "banyak", "potassium_class": "tinggi"},
    )

    assert response.status_code == 422
    assert len(list_observations(state.con)) == before


def test_scenario_insert_moves_a_simulated_reader_into_soil(client, state):
    response = client.post("/api/scenario", json={"sensor_id": "probe-a", "action": "insert"})
    assert response.status_code == 200
    reading = state.readers["probe-a"].read_once(NOW)
    assert reading.values["moisture"] > 0.0


def test_scenario_rejects_an_unknown_sensor(client):
    response = client.post("/api/scenario", json={"sensor_id": "nobody", "action": "insert"})
    assert response.status_code == 404


def test_bind_sensor_adds_a_new_sensor_slot(client, state):
    response = client.post(
        "/api/sensors/probe-b/bind",
        json={"port": "COM10", "profile": "data/profiles/sn3002.json", "mode": "simulate"},
    )
    assert response.status_code == 200
    assert "probe-b" in state.readers
    assert "probe-b" in state.config.sensors


def test_demo_reset_clears_live_rows_but_keeps_seed_rows(client, state):
    db.insert_readings(
        state.con,
        [
            Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SIM),
            Reading(NOW, "probe-a", {"moisture": 2.0}, source=Reading.SOURCE_SEED),
        ],
    )
    response = client.post("/api/demo-reset")
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert db.count_rows(state.con) == 1


def test_export_endpoint_reports_no_readings_as_a_client_error(client):
    response = client.post("/api/export")
    assert response.status_code == 422


def test_export_endpoint_returns_file_paths_once_there_are_readings(client, state, tmp_path, monkeypatch):
    import app.server as server_module

    monkeypatch.setattr(server_module, "EXPORT_DIR", tmp_path / "exports")
    db.insert_reading(
        state.con, Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SIM)
    )
    response = client.post("/api/export")
    assert response.status_code == 200
    body = response.json()
    assert body["parquet"].endswith(".parquet")
    assert "readings_" in body["parquet"]
