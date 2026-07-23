"""A synthetic probe for development and workshop fallback.

Readings carry the simulated source flag so the interface can watermark them.
Never present simulated data as measured.
"""

import random
from datetime import datetime

from app.storage.models import Reading

AIR = {"moisture": 0.0, "conductivity": 0.0, "ph": 4.7, "temperature": 31.2}
SOIL = {"moisture": 42.0, "conductivity": 780.0, "ph": 5.4, "temperature": 28.8}


class SimulatedReader:
    """Mimics the SensorReader interface without any hardware."""

    def __init__(self, sensor_id: str, rng_seed: int = 20260723) -> None:
        self.sensor_id = sensor_id
        self._rng = random.Random(f"{rng_seed}:{sensor_id}")
        self._in_soil = False

    def insert_probe(self) -> None:
        self._in_soil = True

    def withdraw_probe(self) -> None:
        self._in_soil = False

    def read_once(self, now: datetime) -> Reading:
        base = SOIL if self._in_soil else AIR

        if self._in_soil:
            values = {
                "moisture": round(base["moisture"] + self._rng.uniform(-1.2, 1.2), 1),
                "temperature": round(
                    base["temperature"] + self._rng.uniform(-0.3, 0.3), 1
                ),
                "conductivity": round(
                    base["conductivity"] + self._rng.uniform(-30.0, 30.0), 0
                ),
                "ph": round(base["ph"] + self._rng.uniform(-0.08, 0.08), 2),
            }
        else:
            # In air the probe reads flat zeros for moisture and conductivity,
            # exactly as the real probe did on 22 July 2026. Read from
            # AIR/base rather than hardcoding 0.0 here, so an edit to those
            # two entries in AIR actually takes effect instead of silently
            # doing nothing.
            values = {
                "moisture": base["moisture"],
                "conductivity": base["conductivity"],
                "ph": base["ph"],
                "temperature": round(
                    base["temperature"] + self._rng.uniform(-0.3, 0.3), 1
                ),
            }

        return Reading(
            timestamp=now,
            sensor_id=self.sensor_id,
            values=values,
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_SIM,
        )
