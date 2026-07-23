import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import WorkshopConfig
from app.server import broadcast_loop
from app.state import WorkshopState, build_state_payload
from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"


def fake_evaluate(reading, stage, calibration, rules, content):
    return []


def make_two_sensor_state():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict(
        {"sensors": {"probe-a": {"mode": "simulate"}, "probe-b": {"mode": "simulate"}}}
    )
    return WorkshopState.build(connection, config, "config.json", evaluate_fn=fake_evaluate)


def test_state_payload_has_no_comparison_with_one_sensor():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    state = WorkshopState.build(connection, config, "config.json", evaluate_fn=fake_evaluate)
    assert "comparison" not in build_state_payload(state)
    connection.close()


def test_state_payload_omits_comparison_until_both_sensors_have_a_reading():
    state = make_two_sensor_state()
    db.insert_reading(
        state.con, Reading(NOW, "probe-a", {"moisture": 40.0}, source=Reading.SOURCE_SIM)
    )
    assert "comparison" not in build_state_payload(state)
    state.con.close()


def test_state_payload_includes_comparison_once_both_sensors_have_a_reading():
    state = make_two_sensor_state()
    db.insert_reading(
        state.con, Reading(NOW, "probe-a", {"moisture": 60.0}, source=Reading.SOURCE_SIM)
    )
    db.insert_reading(
        state.con, Reading(NOW, "probe-b", {"moisture": 20.0}, source=Reading.SOURCE_SIM)
    )

    body = build_state_payload(state)

    assert body["comparison"]["sensor_a"] == "probe-a"
    assert body["comparison"]["sensor_b"] == "probe-b"
    assert body["comparison"]["metrics"]["moisture"]["higher"] == "a"
    assert body["comparison"]["metrics"]["moisture"]["difference"] == 40.0
    state.con.close()


class StubClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=2)
        return self.now


class RecordingWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


async def instant_sleep(seconds: float) -> None:
    return None


def test_websocket_payload_carries_the_comparison_once_the_other_sensor_has_a_reading():
    state = make_two_sensor_state()
    db.insert_reading(
        state.con, Reading(NOW, "probe-b", {"moisture": 5.0}, source=Reading.SOURCE_SIM)
    )
    websocket = RecordingWebSocket()

    asyncio.run(
        broadcast_loop(
            websocket, state, "probe-a", clock=StubClock(NOW), sleep=instant_sleep, stop_after=1
        )
    )

    assert "comparison" in websocket.sent[0]
    assert websocket.sent[0]["comparison"]["sensor_b"] == "probe-b"
    state.con.close()


def test_comparison_strip_present_in_markup():
    content = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="comparison-strip"' in content


def test_comparison_never_labels_a_nutrient_register():
    content = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "nitrogen" not in content.lower()
    assert "phosphorus" not in content.lower()
    assert "potassium" not in content.lower()


def test_comparison_strip_has_a_dark_mode_override():
    content = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert ".comparison-strip" in content
