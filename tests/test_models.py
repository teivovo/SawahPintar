from datetime import datetime, timedelta, timezone

import pytest

from app.storage.models import Reading


def test_reading_holds_values_and_flags():
    reading = Reading(
        timestamp=datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc),
        sensor_id="probe-a",
        values={"moisture": 31.4, "temperature": 28.2},
        quality=Reading.QUALITY_OK,
        source=Reading.SOURCE_LIVE,
    )
    assert reading.sensor_id == "probe-a"
    assert reading.values["moisture"] == 31.4
    assert reading.quality == "ok"
    assert reading.source == "live"


def test_reading_is_immutable():
    reading = Reading(
        timestamp=datetime(2026, 7, 23, tzinfo=timezone.utc),
        sensor_id="probe-a",
        values={},
        quality=Reading.QUALITY_OK,
        source=Reading.SOURCE_LIVE,
    )
    with pytest.raises(AttributeError):
        reading.sensor_id = "probe-b"


def test_reading_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        Reading(
            timestamp=datetime(2026, 7, 23, 4, 30),
            sensor_id="probe-a",
            values={},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_LIVE,
        )


def test_reading_normalises_non_utc_timestamp_to_utc():
    # Western Indonesia Time (WIB, UTC+7) is a plausible facilitator laptop
    # timezone, distinct from the UTC+8 used elsewhere in this project.
    wib = timezone(timedelta(hours=7))
    local = datetime(2026, 7, 23, 11, 30, tzinfo=wib)

    reading = Reading(
        timestamp=local,
        sensor_id="probe-a",
        values={},
        quality=Reading.QUALITY_OK,
        source=Reading.SOURCE_LIVE,
    )

    # Normalised to a UTC offset of zero.
    assert reading.timestamp.utcoffset() == timedelta(0)
    assert reading.timestamp == datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc)
    # The instant itself is unchanged, not shifted, by the normalisation.
    assert reading.timestamp == local
