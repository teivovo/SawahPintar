from datetime import datetime, timezone

from app.storage.models import Reading
from app.storage.seed import generate_history

END = datetime(2026, 7, 23, 0, 0, tzinfo=timezone.utc)


def test_history_is_deterministic():
    first = generate_history("probe-a", END, days=10)
    second = generate_history("probe-a", END, days=10)
    assert [r.values for r in first] == [r.values for r in second]
    assert [r.timestamp for r in first] == [r.timestamp for r in second]


def test_history_covers_the_requested_span():
    readings = generate_history("probe-a", END, days=10, step_minutes=60)
    assert len(readings) == 10 * 24
    assert readings[0].timestamp < readings[-1].timestamp
    assert readings[-1].timestamp <= END


def test_every_reading_is_flagged_as_seed():
    readings = generate_history("probe-a", END, days=5)
    assert all(r.source == Reading.SOURCE_SEED for r in readings)
    assert all(r.quality == Reading.QUALITY_OK for r in readings)


def test_values_stay_within_plausible_bounds():
    readings = generate_history("probe-a", END, days=90)
    for reading in readings:
        assert 0.0 <= reading.values["moisture"] <= 100.0
        assert 15.0 <= reading.values["temperature"] <= 45.0
        assert 3.0 <= reading.values["ph"] <= 9.0
        assert 0.0 <= reading.values["conductivity"] <= 20000.0


def test_fertiliser_event_raises_conductivity():
    readings = generate_history("probe-a", END, days=90)
    early = [r for r in readings if (END - r.timestamp).days > 50]
    late = [r for r in readings if (END - r.timestamp).days < 40]
    early_mean = sum(r.values["conductivity"] for r in early) / len(early)
    late_mean = sum(r.values["conductivity"] for r in late) / len(late)
    assert late_mean > early_mean * 1.3


def test_different_sensors_get_different_history():
    a = generate_history("probe-a", END, days=10)
    b = generate_history("probe-b", END, days=10)
    assert [r.values["moisture"] for r in a] != [r.values["moisture"] for r in b]


def test_moisture_shows_irrigation_cycles():
    readings = generate_history("probe-a", END, days=30)
    moisture = [r.values["moisture"] for r in readings]
    assert max(moisture) - min(moisture) > 20.0
