from datetime import datetime, timedelta, timezone

from app.detector import StepChangeDetector
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 6, 0, tzinfo=timezone.utc)


def make_reading(moisture: float, conductivity: float, offset_seconds: int = 0) -> Reading:
    return Reading(
        timestamp=NOW + timedelta(seconds=offset_seconds),
        sensor_id="probe-a",
        values={
            "moisture": moisture,
            "conductivity": conductivity,
            "ph": 5.5,
            "temperature": 29.0,
        },
        quality=Reading.QUALITY_OK,
        source=Reading.SOURCE_LIVE,
    )


def test_flat_air_readings_never_trigger():
    detector = StepChangeDetector()
    triggered = [detector.observe(make_reading(0.5, 5.0, i)) for i in range(10)]
    assert not any(triggered)


def test_sharp_rise_in_both_metrics_triggers_once():
    detector = StepChangeDetector()
    for i in range(4):
        detector.observe(make_reading(1.0, 10.0, i))
    triggered = detector.observe(make_reading(42.0, 780.0, 5))
    assert triggered is True


def test_detection_fires_only_once_while_immersed():
    detector = StepChangeDetector(cooldown_readings=3)
    for i in range(4):
        detector.observe(make_reading(1.0, 10.0, i))
    first = detector.observe(make_reading(42.0, 780.0, 5))
    following = [detector.observe(make_reading(42.0, 780.0, 6 + i)) for i in range(5)]
    assert first is True
    assert not any(following)


def test_moisture_rise_alone_does_not_trigger():
    detector = StepChangeDetector()
    for i in range(4):
        detector.observe(make_reading(1.0, 10.0, i))
    triggered = detector.observe(make_reading(42.0, 12.0, 5))
    assert triggered is False


def test_conductivity_rise_alone_does_not_trigger():
    detector = StepChangeDetector()
    for i in range(4):
        detector.observe(make_reading(1.0, 10.0, i))
    triggered = detector.observe(make_reading(2.0, 780.0, 5))
    assert triggered is False


def test_withdrawal_then_reinsertion_triggers_a_second_time():
    detector = StepChangeDetector(cooldown_readings=2, baseline_window=3)
    for i in range(4):
        detector.observe(make_reading(1.0, 10.0, i))
    detector.observe(make_reading(42.0, 780.0, 4))
    for i in range(5, 8):
        detector.observe(make_reading(42.0, 780.0, i))
    for i in range(8, 12):
        detector.observe(make_reading(1.0, 10.0, i))
    second = detector.observe(make_reading(40.0, 760.0, 12))
    assert second is True


def test_reset_clears_the_rolling_baseline():
    detector = StepChangeDetector()
    for i in range(4):
        detector.observe(make_reading(1.0, 10.0, i))
    detector.observe(make_reading(42.0, 780.0, 5))
    detector.reset()
    triggered = detector.observe(make_reading(42.0, 780.0, 6))
    assert triggered is False


def test_missing_values_are_ignored_without_crashing():
    detector = StepChangeDetector()
    partial = Reading(
        timestamp=NOW,
        sensor_id="probe-a",
        values={"ph": 5.5},
        quality=Reading.QUALITY_PARTIAL,
        source=Reading.SOURCE_LIVE,
    )
    assert detector.observe(partial) is False


def test_baseline_window_bounds_how_far_back_the_average_looks():
    detector = StepChangeDetector(baseline_window=2, moisture_rise=5.0, conductivity_rise=50.0)
    detector.observe(make_reading(0.0, 0.0, 0))
    detector.observe(make_reading(0.0, 0.0, 1))
    detector.observe(make_reading(20.0, 200.0, 2))
    triggered = detector.observe(make_reading(20.5, 200.5, 3))
    assert triggered is False
