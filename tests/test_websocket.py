import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.config import WorkshopConfig
from app.detector import StepChangeDetector
from app.server import broadcast_loop, create_app
from app.state import WorkshopState
from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakeAdviceCard:
    icon: str
    severity: str
    headline: str
    body: str
    subtitle_en: str
    rule_group: str


def fake_evaluate(reading, stage, calibration, rules, content):
    return [
        FakeAdviceCard(
            icon="water",
            severity="amber",
            headline="Contoh saran",
            body="Contoh isi",
            subtitle_en="Example advice",
            rule_group="water",
        )
    ]


class RecordingWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class StubClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=2)
        return self.now


def make_recording_sleep():
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    return sleep, slept


def make_state(evaluate_fn=fake_evaluate):
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    return WorkshopState.build(connection, config, "config.json", evaluate_fn=evaluate_fn)


def test_broadcast_loop_persists_and_sends_each_reading():
    state = make_state()
    state.readers["probe-a"].insert_probe()
    websocket = RecordingWebSocket()
    sleep, slept = make_recording_sleep()

    asyncio.run(
        broadcast_loop(
            websocket, state, "probe-a", interval=2.0, clock=StubClock(NOW), sleep=sleep, stop_after=3
        )
    )

    assert len(websocket.sent) == 3
    assert db.count_rows(state.con) == 3 * 4
    assert slept == [2.0, 2.0, 2.0]
    state.con.close()


def test_broadcast_loop_includes_advice_in_the_payload():
    state = make_state()
    state.readers["probe-a"].insert_probe()
    websocket = RecordingWebSocket()
    sleep, _ = make_recording_sleep()

    asyncio.run(
        broadcast_loop(websocket, state, "probe-a", clock=StubClock(NOW), sleep=sleep, stop_after=1)
    )

    advice = websocket.sent[0]["advice"]
    assert advice[0]["headline"] == "Contoh saran"
    assert advice[0]["rule_group"] == "water"
    state.con.close()


def test_broadcast_loop_flags_only_the_insertion_reading():
    state = make_state()
    websocket = RecordingWebSocket()
    sleep, _ = make_recording_sleep()
    clock = StubClock(NOW)

    async def scenario():
        await broadcast_loop(websocket, state, "probe-a", clock=clock, sleep=sleep, stop_after=3)
        state.readers["probe-a"].insert_probe()
        await broadcast_loop(websocket, state, "probe-a", clock=clock, sleep=sleep, stop_after=1)

    asyncio.run(scenario())
    state.con.close()

    assert websocket.sent[-1]["probe_inserted"] is True
    assert all(not message["probe_inserted"] for message in websocket.sent[:-1])


def test_broadcast_loop_marks_simulated_true_for_sim_source():
    state = make_state()
    state.readers["probe-a"].insert_probe()
    websocket = RecordingWebSocket()
    sleep, _ = make_recording_sleep()

    asyncio.run(
        broadcast_loop(websocket, state, "probe-a", clock=StubClock(NOW), sleep=sleep, stop_after=1)
    )

    assert websocket.sent[0]["simulated"] is True
    state.con.close()


@dataclass(frozen=True)
class StubReader:
    """A reader whose reading is fixed and recognisable, standing in for
    whatever build_reader() would have produced, so a test can prove which
    reader a given broadcast actually came from."""

    sensor_id: str
    moisture: float

    def read_once(self, now: datetime) -> Reading:
        return Reading(now, self.sensor_id, {"moisture": self.moisture}, source=Reading.SOURCE_SIM)


def test_broadcast_loop_picks_up_a_sensor_rebound_mid_loop():
    """POST /api/sensors/{id}/bind replaces state.readers[sensor_id] and
    state.detectors[sensor_id] while a socket may already be open (for
    example a second console window, or the farmer display itself). The
    loop must read the current reader/detector every tick, not only once
    before it starts, or the rebind never reaches that open socket."""
    state = make_state()
    state.readers["probe-a"] = StubReader("probe-a", 1.0)
    websocket = RecordingWebSocket()
    clock = StubClock(NOW)

    async def sleep(seconds: float) -> None:
        state.readers["probe-a"] = StubReader("probe-a", 999.0)
        state.detectors["probe-a"] = StepChangeDetector()

    asyncio.run(
        broadcast_loop(websocket, state, "probe-a", clock=clock, sleep=sleep, stop_after=2)
    )

    assert websocket.sent[0]["reading"]["values"]["moisture"] == 1.0
    assert websocket.sent[1]["reading"]["values"]["moisture"] == 999.0
    state.con.close()


def test_broadcast_loop_runs_read_once_off_the_event_loop_thread():
    """reader.read_once() is a blocking, synchronous serial call. It must
    run via asyncio.to_thread, not directly on the event loop, so a probe
    that has stopped answering stalls only this call rather than every
    other websocket and route the server is handling."""
    state = make_state()
    main_thread_ident = threading.get_ident()
    observed_idents = []

    class ThreadRecordingReader:
        def read_once(self, now: datetime) -> Reading:
            observed_idents.append(threading.get_ident())
            return Reading(now, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SIM)

    state.readers["probe-a"] = ThreadRecordingReader()
    websocket = RecordingWebSocket()
    sleep, _ = make_recording_sleep()

    asyncio.run(
        broadcast_loop(websocket, state, "probe-a", clock=StubClock(NOW), sleep=sleep, stop_after=1)
    )

    assert observed_idents == [observed_idents[0]]
    assert observed_idents[0] != main_thread_ident
    state.con.close()


def test_websocket_route_rejects_an_unconfigured_sensor():
    from fastapi import WebSocketDisconnect
    from fastapi.testclient import TestClient

    state = make_state()
    client = TestClient(create_app(state))

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?sensor_id=nobody"):
            pass

    state.con.close()


class FailingReader:
    """A reader whose read_once always fails, like a live probe that is not
    connected or whose port is held by another program."""

    def __init__(self) -> None:
        self.calls = 0

    def read_once(self, now):
        self.calls += 1
        from app.sensor.transport import TransportError

        raise TransportError("could not open COM9")


def test_broadcast_loop_survives_a_read_failure_and_keeps_the_socket_alive():
    """A read failure must not kill the feed.

    If it did, the websocket would close, the display would fall into a
    permanent reconnect loop, and the operator could not recover by switching
    back to simulation, because the replacement reader is only picked up on the
    next tick of this same loop. So the loop stays alive, sends an error
    message the client can show as a sensor-offline cue, and carries on.
    """
    state = make_state()
    state.readers["probe-a"] = FailingReader()
    websocket = RecordingWebSocket()
    sleep, slept = make_recording_sleep()

    # Would raise out of broadcast_loop before the fix; now it completes.
    asyncio.run(
        broadcast_loop(
            websocket, state, "probe-a", clock=StubClock(NOW), sleep=sleep, stop_after=3
        )
    )

    assert len(websocket.sent) == 3
    assert all(m.get("error") == "sensor-not-responding" for m in websocket.sent)
    # No reading was stored, since none could be taken.
    assert db.count_rows(state.con) == 0
    assert slept == [2.0, 2.0, 2.0]
    state.con.close()


def test_broadcast_loop_recovers_when_the_reader_is_swapped_back_to_simulate():
    """After a failing live reader is replaced with a working one, the very
    next tick produces a real reading, without the socket ever closing. This
    is the switch-back-to-simulation recovery the operator relies on."""
    state = make_state()
    state.readers["probe-a"] = FailingReader()
    websocket = RecordingWebSocket()
    sleep, slept = make_recording_sleep()

    async def run():
        # One tick failing, then swap in a working simulated reader.
        await broadcast_loop(
            websocket, state, "probe-a", clock=StubClock(NOW), sleep=sleep, stop_after=1
        )
        from app.sensor.simulator import SimulatedReader

        working = SimulatedReader("probe-a")
        working.insert_probe()
        state.readers["probe-a"] = working
        await broadcast_loop(
            websocket, state, "probe-a", clock=StubClock(NOW), sleep=sleep, stop_after=1
        )

    asyncio.run(run())

    assert websocket.sent[0].get("error") == "sensor-not-responding"
    assert "error" not in websocket.sent[1]
    assert websocket.sent[1]["reading"]["values"]["moisture"] > 0
    state.con.close()


def test_a_websocket_library_is_installed_for_uvicorn():
    """uvicorn ships no websocket implementation of its own. Without one, the
    /ws endpoint returns 404 at runtime and no live data ever flows, yet every
    other test in this file still passes because Starlette's TestClient has its
    own websocket support that real uvicorn does not use. This asserts the
    runtime dependency is actually installed, so its accidental removal fails
    fast here instead of silently on a field laptop. See the websockets entry
    in pyproject.toml and the server-smoke toolkit tool."""
    import importlib.util

    assert (
        importlib.util.find_spec("websockets") is not None
        or importlib.util.find_spec("wsproto") is not None
    ), "no websocket library installed; real uvicorn cannot upgrade /ws"
