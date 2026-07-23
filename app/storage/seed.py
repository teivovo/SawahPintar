"""Deterministic demonstration history.

Charts must be alive the moment the application opens, because farmers will
not stand in a field waiting for data to accumulate. Everything generated here
is flagged as seed data and is rendered differently from measured data, so it
is never mistaken for a real observation.

The generator is deterministic so that every laptop in a workshop shows the
same history.
"""

import math
import random
from datetime import datetime, timedelta

from app.storage.models import Reading

IRRIGATION_PERIOD_HOURS = 7 * 24
FERTILISER_DAYS_BEFORE_END = 45


def generate_history(
    sensor_id: str,
    end: datetime,
    days: int = 90,
    step_minutes: int = 60,
    rng_seed: int = 20260723,
) -> list[Reading]:
    """Return a plausible wet season paddy history ending at end."""
    rng = random.Random(f"{rng_seed}:{sensor_id}")
    steps = (days * 24 * 60) // step_minutes
    start = end - timedelta(minutes=step_minutes * steps)

    readings: list[Reading] = []
    for index in range(steps):
        timestamp = start + timedelta(minutes=step_minutes * index)
        hours_elapsed = index * step_minutes / 60
        days_before_end = (end - timestamp).days

        # Irrigation sawtooth: a sharp rise then a slow recession.
        phase = (hours_elapsed % IRRIGATION_PERIOD_HOURS) / IRRIGATION_PERIOD_HOURS
        moisture = 34.0 + 26.0 * math.exp(-3.0 * phase) + rng.uniform(-1.5, 1.5)

        # Daily temperature swing around a tropical mean.
        hour_of_day = (hours_elapsed % 24)
        temperature = (
            28.5
            + 4.0 * math.sin((hour_of_day - 9.0) / 24.0 * 2.0 * math.pi)
            + rng.uniform(-0.6, 0.6)
        )

        # Conductivity steps up once fertiliser has been applied, then decays.
        conductivity = 420.0 + rng.uniform(-25.0, 25.0)
        if days_before_end < FERTILISER_DAYS_BEFORE_END:
            decay = math.exp(-(FERTILISER_DAYS_BEFORE_END - days_before_end) / 60.0)
            conductivity += 520.0 * decay

        # Slow acidification across the season.
        ph = 6.3 - 0.010 * (days - days_before_end) + rng.uniform(-0.05, 0.05)

        readings.append(
            Reading(
                timestamp=timestamp,
                sensor_id=sensor_id,
                values={
                    "moisture": round(max(0.0, min(100.0, moisture)), 1),
                    "temperature": round(max(15.0, min(45.0, temperature)), 1),
                    "conductivity": round(max(0.0, min(20000.0, conductivity)), 0),
                    "ph": round(max(3.0, min(9.0, ph)), 2),
                },
                quality=Reading.QUALITY_OK,
                source=Reading.SOURCE_SEED,
            )
        )

    return readings
