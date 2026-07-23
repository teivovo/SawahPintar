from datetime import datetime, timezone

import pytest

from app.sensor.codec import build_read_request, crc16
from app.sensor.profile import SensorProfile
from app.sensor.reader import SensorReader
from app.sensor.transport import FakeTransport, TransportError
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc)


def build_response(address: int, function: int, registers: list[int]) -> bytes:
    body = bytes([address, function, 2 * len(registers)])
    for value in registers:
        body += value.to_bytes(2, "big")
    return body + crc16(body)


@pytest.fixture
def profile() -> SensorProfile:
    return SensorProfile.load("data/profiles/sn3002.json")


def test_read_once_returns_decoded_reading(profile):
    request = build_read_request(1, 3, 0, 9)
    response = build_response(1, 3, [658, 312, 1000, 56, 0, 0, 0, 0, 0])
    reader = SensorReader("probe-a", profile, FakeTransport({request: response}))

    reading = reader.read_once(NOW)

    assert reading.sensor_id == "probe-a"
    assert reading.timestamp == NOW
    assert reading.quality == Reading.QUALITY_OK
    assert reading.source == Reading.SOURCE_LIVE
    assert reading.values["moisture"] == pytest.approx(65.8)
    assert reading.values["ph"] == pytest.approx(5.6)


def test_read_once_opens_the_transport(profile):
    request = build_read_request(1, 3, 0, 9)
    response = build_response(1, 3, [0] * 9)
    transport = FakeTransport({request: response})
    reader = SensorReader("probe-a", profile, transport)

    reader.read_once(NOW)

    assert transport.is_open is True


def test_read_once_marks_out_of_range_values_partial(profile):
    request = build_read_request(1, 3, 0, 9)
    # A pH register of 200 decodes to 20.0, outside the declared 3 to 9 band.
    response = build_response(1, 3, [658, 312, 1000, 200, 0, 0, 0, 0, 0])
    reader = SensorReader("probe-a", profile, FakeTransport({request: response}))

    reading = reader.read_once(NOW)

    assert reading.quality == Reading.QUALITY_PARTIAL
    assert reading.values["ph"] == pytest.approx(20.0)


def test_read_once_marks_reading_as_error_when_every_plan_fails(profile):
    request = build_read_request(1, 3, 0, 9)
    reader = SensorReader("probe-a", profile, FakeTransport({request: b"\x00\x01"}))

    reading = reader.read_once(NOW)

    assert reading.quality == Reading.QUALITY_ERROR
    assert reading.values == {}


def test_read_once_propagates_transport_failure(profile):
    reader = SensorReader("probe-a", profile, FakeTransport({}, fail_on_open=True))

    with pytest.raises(TransportError):
        reader.read_once(NOW)
