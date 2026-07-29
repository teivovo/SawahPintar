"""A synthetic probe for development and workshop fallback.

Readings carry the simulated source flag so the interface can watermark them.
Never present simulated data as measured.
"""

import random
from datetime import datetime

from app.storage.models import Reading

# N/P/K bases are in mg/kg to match how the detail's NPK estimate is banded.
# They are a demonstration convenience, not a physical model: the real probe
# derives N, P and K from one bulk conductivity reading, so these are only ever
# shown as an "estimasi sensor" and never as a fertiliser dose.
AIR = {
    "moisture": 0.0,
    "conductivity": 0.0,
    "ph": 4.7,
    "temperature": 31.2,
    "nitrogen_raw": 0.0,
    "phosphorus_raw": 0.0,
    "potassium_raw": 0.0,
}
SOIL = {
    "moisture": 42.0,
    "conductivity": 780.0,
    "ph": 5.4,
    "temperature": 28.8,
    "nitrogen_raw": 130.0,
    "phosphorus_raw": 18.0,
    "potassium_raw": 85.0,
}


class SimulatedReader:
    """Mimics the SensorReader interface without any hardware."""

    def __init__(self, sensor_id: str, rng_seed: int = 20260723) -> None:
        self.sensor_id = sensor_id
        self._rng = random.Random(f"{rng_seed}:{sensor_id}")
        self._in_soil = False
        # A stable per-sensor N/P/K offset drawn from a separate stream, so
        # each plot has its own distinct nutrient profile on the field map
        # without disturbing the moisture/conductivity sequence the existing
        # tests pin. Same sensor id gives the same offset, so it is
        # deterministic like the rest of the reader.
        npk_rng = random.Random(f"npk:{sensor_id}")
        self._npk_offset = {
            "nitrogen_raw": npk_rng.uniform(-70.0, 90.0),
            "phosphorus_raw": npk_rng.uniform(-9.0, 14.0),
            "potassium_raw": npk_rng.uniform(-45.0, 55.0),
        }

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
                # N/P/K estimate: per-sensor offset plus small jitter, drawn
                # after the four core metrics so their sequence is unchanged.
                "nitrogen_raw": round(
                    max(0.0, base["nitrogen_raw"] + self._npk_offset["nitrogen_raw"]
                        + self._rng.uniform(-8.0, 8.0))
                ),
                "phosphorus_raw": round(
                    max(0.0, base["phosphorus_raw"] + self._npk_offset["phosphorus_raw"]
                        + self._rng.uniform(-1.5, 1.5))
                ),
                "potassium_raw": round(
                    max(0.0, base["potassium_raw"] + self._npk_offset["potassium_raw"]
                        + self._rng.uniform(-5.0, 5.0))
                ),
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
                "nitrogen_raw": base["nitrogen_raw"],
                "phosphorus_raw": base["phosphorus_raw"],
                "potassium_raw": base["potassium_raw"],
            }

        return Reading(
            timestamp=now,
            sensor_id=self.sensor_id,
            values=values,
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_SIM,
        )
