"""A synthetic probe for development and workshop fallback.

Readings carry the simulated source flag so the interface can watermark them.
Never present simulated data as measured.
"""

import random
import re
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

# Per-sensor soil conditions, so a demo field shows a spread of green / amber
# / red rather than one uniform colour. Each scenario sets only the three
# status drivers - moisture, pH and conductivity; temperature and N/P/K keep
# the SOIL bases. Every scenario stays in the range the simulator tests pin
# (moisture > 20, conductivity > 100 in soil), so a red plot comes from
# salinity, never from a dry probe. A reader picks one deterministically from
# its sensor id (round-robin by trailing number, else hashed), so plots
# numbered in sequence get different conditions.
SOIL_SCENARIOS = [
    {"moisture": 44.0, "ph": 6.4, "conductivity": 700.0},    # good -> green
    {"moisture": 40.0, "ph": 5.0, "conductivity": 760.0},    # acidic -> amber
    {"moisture": 37.0, "ph": 6.1, "conductivity": 4500.0},   # severely saline -> red
    {"moisture": 43.0, "ph": 6.6, "conductivity": 660.0},    # good -> green
    {"moisture": 36.0, "ph": 6.0, "conductivity": 4200.0},   # severely saline -> red
    {"moisture": 39.0, "ph": 6.2, "conductivity": 1700.0},   # slightly saline -> amber
]


def _scenario_for(sensor_id: str) -> dict:
    match = re.search(r"(\d+)$", sensor_id)
    if match:
        index = int(match.group(1)) % len(SOIL_SCENARIOS)
    else:
        index = random.Random(f"scenario:{sensor_id}").randrange(len(SOIL_SCENARIOS))
    return SOIL_SCENARIOS[index]


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
        # This plot's soil condition, fixed for the life of the reader.
        self._soil = _scenario_for(sensor_id)

    def insert_probe(self) -> None:
        self._in_soil = True

    def withdraw_probe(self) -> None:
        self._in_soil = False

    def read_once(self, now: datetime) -> Reading:
        base = SOIL if self._in_soil else AIR

        if self._in_soil:
            soil = self._soil
            values = {
                "moisture": round(soil["moisture"] + self._rng.uniform(-1.2, 1.2), 1),
                "temperature": round(
                    SOIL["temperature"] + self._rng.uniform(-0.3, 0.3), 1
                ),
                "conductivity": round(
                    soil["conductivity"] + self._rng.uniform(-30.0, 30.0), 0
                ),
                "ph": round(soil["ph"] + self._rng.uniform(-0.08, 0.08), 2),
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
