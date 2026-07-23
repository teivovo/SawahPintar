from datetime import datetime, timedelta, timezone

import pytest

from app.acquire import poll_forever
from app.sensor.simulator import SimulatedReader
from app.sensor.transport import TransportError
from app.storage import db

NOW = datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc)


@pytest.fixture
def con():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    yield connection
    connection.close()


class StubClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=2)
        return self.now


class FlakyReader:
    """Fails for the first two reads, then succeeds."""

    def __init__(self) -> None:
        self.attempts = 0
        self.sensor_id = "flaky"

    def read_once(self, now):
        self.attempts += 1
        if self.attempts <= 2:
            raise TransportError("dongle unplugged")
        return SimulatedReader("flaky").read_once(now)


def test_poll_forever_persists_readings(con):
    reader = SimulatedReader("sim-a")
    reader.insert_probe()
    slept = []

    poll_forever(reader, con, 2.0, StubClock(NOW), stop_after=3, sleeper=slept.append)

    assert db.count_rows(con) == 12  # three readings, four metrics each
    assert len(db.series(con, "sim-a", "moisture")) == 3


def test_poll_forever_recovers_from_transport_failure(con):
    reader = FlakyReader()
    slept = []

    poll_forever(reader, con, 2.0, StubClock(NOW), stop_after=3, sleeper=slept.append)

    assert reader.attempts == 5  # two failures then three successful reads
    assert len(db.series(con, "flaky", "moisture")) == 3


def test_backoff_grows_then_resets(con):
    reader = FlakyReader()
    slept = []

    poll_forever(reader, con, 2.0, StubClock(NOW), stop_after=1, sleeper=slept.append)

    # First failure waits one second, second waits two, then normal interval.
    assert slept[0] == 1.0
    assert slept[1] == 2.0
    assert slept[-1] == 2.0


def test_backoff_is_capped(con):
    class DeadReader:
        sensor_id = "dead"

        def read_once(self, now):
            raise TransportError("no port")

    slept = []
    poll_forever(
        DeadReader(),
        con,
        2.0,
        StubClock(NOW),
        stop_after=None,
        sleeper=slept.append,
        max_failures=12,
    )
    assert len(slept) == 12
    assert max(slept) == 30.0
    assert db.count_rows(con) == 0


def test_backoff_survives_a_very_long_outage(con):
    """A dongle left unplugged overnight must keep retrying, not crash.

    Failures past the sixth already sleep the full 30 second cap. The old
    expression computed 2.0 ** (failures - 1) before min() could clamp it,
    so it raised OverflowError once failures reached 1025 (about 8.5 hours
    of continuous failure at the capped rate). This drives the real loop
    past that threshold with a no-op sleeper so the test stays instant.
    """

    class DeadReader:
        sensor_id = "dead"

        def read_once(self, now):
            raise TransportError("no port")

    slept = []
    poll_forever(
        DeadReader(),
        con,
        2.0,
        StubClock(NOW),
        stop_after=None,
        sleeper=slept.append,
        max_failures=1030,
    )
    assert len(slept) == 1030
    assert max(slept) == 30.0
    assert db.count_rows(con) == 0
