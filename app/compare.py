"""Comparison support for the two-sensor split view.

With two sensors connected the display splits for comparison, the
strongest teaching device available: a flooded paddy beside a dry bund, or
a fertilised plot beside an untreated one. See design spec section 9.1.
Deliberately covers only the four dial metrics, never a raw nutrient
register, matching the Global Constraints section of this plan.
"""

from app.storage.models import Reading

COMPARABLE_METRICS = ("moisture", "temperature", "conductivity", "ph")


def compare_readings(reading_a: Reading, reading_b: Reading) -> dict[str, dict]:
    """Return a per-metric comparison between two simultaneous readings.

    Each entry reports which sensor read higher and by how much, so the
    interface can render a plain-language comparison line such as
    'Sensor A memiliki kelembapan lebih tinggi'.
    """
    result: dict[str, dict] = {}
    for metric in COMPARABLE_METRICS:
        value_a = reading_a.values.get(metric)
        value_b = reading_b.values.get(metric)
        if value_a is None or value_b is None:
            continue
        difference = round(value_a - value_b, 2)
        if difference > 0:
            higher = "a"
        elif difference < 0:
            higher = "b"
        else:
            higher = "equal"
        result[metric] = {
            "sensor_a": value_a,
            "sensor_b": value_b,
            "difference": abs(difference),
            "higher": higher,
        }
    return result
