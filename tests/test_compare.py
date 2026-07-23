from datetime import datetime, timezone

from app.compare import compare_readings
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 9, 0, tzinfo=timezone.utc)


def reading(values):
    return Reading(NOW, "probe-x", values, source=Reading.SOURCE_LIVE)


def test_reports_which_sensor_reads_higher():
    result = compare_readings(reading({"moisture": 60.0}), reading({"moisture": 20.0}))
    assert result["moisture"]["higher"] == "a"
    assert result["moisture"]["difference"] == 40.0


def test_reports_b_when_b_is_higher():
    result = compare_readings(reading({"ph": 5.0}), reading({"ph": 6.5}))
    assert result["ph"]["higher"] == "b"
    assert result["ph"]["difference"] == 1.5


def test_reports_equal_when_values_match():
    result = compare_readings(reading({"temperature": 28.0}), reading({"temperature": 28.0}))
    assert result["temperature"]["higher"] == "equal"
    assert result["temperature"]["difference"] == 0.0


def test_skips_metrics_missing_from_either_reading():
    result = compare_readings(reading({"moisture": 1.0}), reading({"ph": 6.0}))
    assert result == {}


def test_covers_all_four_comparable_metrics_when_present():
    values = {"moisture": 1.0, "temperature": 2.0, "conductivity": 3.0, "ph": 4.0}
    result = compare_readings(reading(values), reading(values))
    assert set(result.keys()) == {"moisture", "temperature", "conductivity", "ph"}


def test_ignores_nutrient_registers_entirely():
    result = compare_readings(
        reading({"moisture": 1.0, "nitrogen_raw": 5.0}),
        reading({"moisture": 2.0, "nitrogen_raw": 50.0}),
    )
    assert "nitrogen_raw" not in result
