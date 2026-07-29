"""Field-map backend: zone geometry in the state payload, the zone status
derived from advice severity, per-plot rebind that preserves the drawn
outline, and the /api/zones layout endpoint."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import WorkshopConfig
from app.server import create_app
from app.state import WorkshopState, zone_status
from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 7, 0, tzinfo=timezone.utc)


class _Card:
    """Minimal advice-card stand-in with the six serialised attributes."""

    def __init__(self, severity):
        self.severity = severity
        self.icon = "water"
        self.headline = "h"
        self.body = "b"
        self.subtitle_en = "s"
        self.rule_group = "water"


def make_state(sensors=None, evaluate_fn=None, config_path="config.json", **config_extra):
    # config_path defaults to a name that is never written unless a test
    # POSTs a saving route; those tests pass a tmp_path so the real
    # repo-root config.json is never touched.
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict(
        {"sensors": sensors or {"probe-a": {"mode": "simulate"}}, **config_extra}
    )
    return WorkshopState.build(
        connection,
        config,
        config_path,
        evaluate_fn=evaluate_fn or (lambda *a, **k: []),
    )


# --- zone_status ---------------------------------------------------------

def test_zone_status_idle_without_a_reading():
    assert zone_status(None, [], "simulate") == "idle"


def test_zone_status_idle_when_detached_even_with_a_reading():
    reading = Reading(NOW, "s", {"moisture": 30.0}, source=Reading.SOURCE_SIM)
    assert zone_status(reading, [_Card("red")], "off") == "idle"


def test_zone_status_good_when_reading_but_no_advice():
    reading = Reading(NOW, "s", {"moisture": 30.0}, source=Reading.SOURCE_SIM)
    assert zone_status(reading, [], "simulate") == "good"


def test_zone_status_takes_the_worst_severity():
    reading = Reading(NOW, "s", {"moisture": 30.0}, source=Reading.SOURCE_SIM)
    advice = [_Card("green"), _Card("red"), _Card("amber")]
    assert zone_status(reading, advice, "live") == "critical"
    assert zone_status(reading, [_Card("green"), _Card("amber")], "live") == "attention"


# --- state payload -------------------------------------------------------

def test_state_payload_carries_field_and_plot_metadata():
    state = make_state(
        sensors={"S1": {"mode": "simulate", "name": "Blok 1", "zone": [[10, 10], [90, 10], [50, 80]]}},
        field_image="assets/field-default.jpg",
        field_view=[1537, 1023],
        site_name="Sidrap",
    )
    client = TestClient(create_app(state))
    body = client.get("/api/state").json()

    assert body["field_image"] == "assets/field-default.jpg"
    assert body["field_view"] == [1537, 1023]
    assert body["site_name"] == "Sidrap"
    plot = body["sensors"]["S1"]
    assert plot["name"] == "Blok 1"
    assert plot["zone"] == [[10, 10], [90, 10], [50, 80]]
    assert plot["mode"] == "simulate"
    assert plot["status"] == "idle"  # no reading yet


def test_state_payload_name_falls_back_to_sensor_id():
    state = make_state(sensors={"S1": {"mode": "simulate"}})
    body = TestClient(create_app(state)).get("/api/state").json()
    assert body["sensors"]["S1"]["name"] == "S1"


def test_detached_plot_reports_no_reading_even_with_seeded_history():
    # A plot switched off still has seeded rows in the DB; the map must not
    # surface advice for a plot that has no sensor.
    state = make_state(
        sensors={"S1": {"mode": "off", "zone": [[0, 0], [1, 0], [1, 1]]}},
        evaluate_fn=lambda *a, **k: [_Card("red")],
    )
    db.insert_reading(
        state.con, Reading(NOW, "S1", {"moisture": 12.0}, source=Reading.SOURCE_SEED)
    )
    plot = TestClient(create_app(state)).get("/api/state").json()["sensors"]["S1"]
    assert plot["reading"] is None
    assert plot["advice"] == []
    assert plot["status"] == "idle"


def test_state_payload_status_reflects_advice(monkeypatch):
    state = make_state(
        sensors={"S1": {"mode": "simulate", "zone": [[0, 0], [1, 0], [1, 1]]}},
        evaluate_fn=lambda *a, **k: [_Card("amber")],
    )
    db.insert_reading(
        state.con, Reading(NOW, "S1", {"moisture": 30.0}, source=Reading.SOURCE_SIM)
    )
    body = TestClient(create_app(state)).get("/api/state").json()
    assert body["sensors"]["S1"]["status"] == "attention"


# --- rebind preserves the drawn outline ---------------------------------

def test_rebind_preserves_name_and_zone(tmp_path):
    state = make_state(
        sensors={"S1": {"mode": "simulate", "name": "Blok 1", "zone": [[1, 1], [2, 2], [3, 1]]}},
        config_path=tmp_path / "config.json",
    )
    client = TestClient(create_app(state))

    # Switch S1 from simulation to live without sending a name or zone.
    response = client.post("/api/sensors/S1/bind", json={"port": "COM7", "mode": "live"})
    assert response.status_code == 200

    plot = client.get("/api/state").json()["sensors"]["S1"]
    assert plot["name"] == "Blok 1"
    assert plot["zone"] == [[1, 1], [2, 2], [3, 1]]
    assert plot["mode"] == "live"
    assert plot["port"] == "COM7"


# --- /api/zones layout ---------------------------------------------------

def test_zones_endpoint_replaces_the_plot_set(tmp_path):
    state = make_state(sensors={"probe-a": {"mode": "simulate"}}, config_path=tmp_path / "config.json")
    client = TestClient(create_app(state))

    response = client.post(
        "/api/zones",
        json={
            "field_image": "assets/field-default.jpg",
            "field_view": [1537, 1023],
            "zones": [
                {"id": "S1", "name": "Blok 1", "mode": "simulate", "zone": [[0, 0], [10, 0], [5, 9]]},
                {"id": "S2", "name": "Blok 2", "mode": "off", "zone": [[20, 20], [30, 20], [25, 29]]},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert set(body["sensors"]) == {"S1", "S2"}
    assert "probe-a" not in body["sensors"]
    assert body["sensors"]["S1"]["name"] == "Blok 1"
    assert body["sensors"]["S2"]["mode"] == "off"
    # A detached plot has no reader and never opens a feed.
    assert state.readers["S1"] is not None
    assert state.readers["S2"] is None
    assert "probe-a" not in state.readers


def test_zones_endpoint_starts_new_simulate_plots_in_soil(tmp_path):
    # A field-map demo treats simulated plots as probes already in the ground,
    # so a plot created via the zone editor reads soil, not air (which would
    # read moisture 0 and fire a false "reflood now" alert).
    state = make_state(sensors={"probe-a": {"mode": "simulate"}}, config_path=tmp_path / "config.json")
    client = TestClient(create_app(state))
    client.post(
        "/api/zones",
        json={"zones": [{"id": "S1", "name": "Blok 1", "mode": "simulate", "zone": [[0, 0], [10, 0], [5, 9]]}]},
    )
    reading = state.readers["S1"].read_once(NOW)
    assert reading.values["moisture"] > 20.0


def test_rebind_to_simulate_in_map_mode_starts_in_soil(tmp_path):
    # Switching a plot to simulation from the map detail must not read air.
    state = make_state(
        sensors={"S1": {"mode": "off", "name": "Blok 1", "zone": [[0, 0], [10, 0], [5, 9]]}},
        config_path=tmp_path / "config.json",
    )
    client = TestClient(create_app(state))
    client.post("/api/sensors/S1/bind", json={"mode": "simulate"})
    reading = state.readers["S1"].read_once(NOW)
    assert reading.values["moisture"] > 20.0


def test_rebind_without_any_zone_keeps_the_probe_in_air(tmp_path):
    # The single-probe demo (no zones) keeps its probe in air for the hands-on
    # insertion moment; a rebind must not silently put it in soil.
    state = make_state(sensors={"probe-a": {"mode": "simulate"}}, config_path=tmp_path / "config.json")
    client = TestClient(create_app(state))
    client.post("/api/sensors/probe-a/bind", json={"mode": "simulate"})
    reading = state.readers["probe-a"].read_once(NOW)
    assert reading.values["moisture"] == 0.0


def test_sensor_settings_rename_persists_without_rebuilding_reader(tmp_path):
    state = make_state(
        sensors={"S1": {"mode": "simulate", "name": "Blok 1", "zone": [[0, 0], [10, 0], [5, 9]]}},
        config_path=tmp_path / "config.json",
    )
    original_reader = state.readers["S1"]
    client = TestClient(create_app(state))
    response = client.post("/api/sensors/S1/settings", json={"name": "Sawah Utara"})
    assert response.status_code == 200
    assert state.config.sensors["S1"].name == "Sawah Utara"
    assert state.readers["S1"] is original_reader  # renaming does not rebuild the reader
    assert client.get("/api/state").json()["sensors"]["S1"]["name"] == "Sawah Utara"


def test_per_plot_growth_stage_changes_only_that_plots_advice(tmp_path):
    # Salinity advice is escalated during flowering, so a per-plot flowering
    # stage must push that plot's status up without touching the others.
    def stage_aware(reading, stage, *rest):
        return [_Card("red" if stage == "flowering" else "amber")]

    state = make_state(
        sensors={"S1": {"mode": "simulate", "zone": [[0, 0], [1, 0], [1, 1]]}},
        evaluate_fn=stage_aware,
        config_path=tmp_path / "config.json",
    )
    db.insert_reading(state.con, Reading(NOW, "S1", {"moisture": 30.0}, source=Reading.SOURCE_SIM))
    client = TestClient(create_app(state))
    assert client.get("/api/state").json()["sensors"]["S1"]["status"] == "attention"

    client.post("/api/sensors/S1/settings", json={"growth_stage": "flowering"})
    plot = client.get("/api/state").json()["sensors"]["S1"]
    assert plot["growth_stage"] == "flowering"
    assert plot["status"] == "critical"


def test_sensor_settings_rejects_an_unknown_growth_stage(tmp_path):
    state = make_state(sensors={"S1": {"mode": "simulate"}}, config_path=tmp_path / "config.json")
    client = TestClient(create_app(state))
    assert client.post("/api/sensors/S1/settings", json={"growth_stage": "bogus"}).status_code == 422


def test_zones_endpoint_reshape_keeps_existing_reader(tmp_path):
    state = make_state(
        sensors={"S1": {"mode": "simulate", "zone": [[0, 0], [1, 0], [1, 1]]}},
        config_path=tmp_path / "config.json",
    )
    original_reader = state.readers["S1"]
    client = TestClient(create_app(state))

    client.post(
        "/api/zones",
        json={"zones": [{"id": "S1", "name": "Blok 1", "mode": "simulate", "zone": [[0, 0], [2, 0], [2, 2]]}]},
    )
    # Only the outline changed, so the reader (and its simulation seed) is
    # not needlessly rebuilt.
    assert state.readers["S1"] is original_reader
    assert state.config.sensors["S1"].zone == [[0, 0], [2, 0], [2, 2]]
