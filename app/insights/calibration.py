"""Calibration between raw probe quantities and the physical quantities the
published research thresholds are expressed in.

Both mappings here are marked provisional, in this docstring and in the
shipped YAML data, because neither has been checked against local South
Sulawesi soils yet. Design spec section 8.1 explains why they are needed:
the AWD 15 cm re-flood trigger is a water-table depth from a perforated
field tube, not a moisture percentage, and the published salinity
thresholds use saturated paste extract conductivity, not the probe's bulk
conductivity. Faculty adjust these values by editing the YAML, never the
code. Section 10 describes the field water tube as the route to
calibrating the water mapping properly; section 13 lists both mappings as
an explicitly open decision.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SalinityBreakpoint:
    """One boundary in the bulk conductivity to salinity class table.

    A reading at or below max_conductivity_us_cm belongs to salinity_class.
    Breakpoints are evaluated in ascending order, so the last breakpoint is
    the catch-all for anything above every other boundary.
    """

    max_conductivity_us_cm: float
    salinity_class: str


@dataclass(frozen=True)
class WaterTablePoint:
    """One control point in the moisture to water-table depth curve."""

    moisture_percent: float
    water_table_depth_cm: float


@dataclass(frozen=True)
class Calibration:
    """The two provisional physical mappings, loaded from one YAML file."""

    provisional: bool
    salinity_breakpoints: tuple[SalinityBreakpoint, ...]
    water_table_curve: tuple[WaterTablePoint, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "Calibration":
        for required in ("provisional", "salinity_breakpoints", "water_table_curve"):
            if required not in data:
                raise ValueError(f"calibration is missing required field: {required}")

        breakpoints = tuple(
            SalinityBreakpoint(
                max_conductivity_us_cm=entry["max_conductivity_us_cm"],
                salinity_class=entry["salinity_class"],
            )
            for entry in data["salinity_breakpoints"]
        )
        limits = [point.max_conductivity_us_cm for point in breakpoints]
        if limits != sorted(limits):
            raise ValueError("salinity_breakpoints must be sorted ascending by max_conductivity_us_cm")

        curve = tuple(
            WaterTablePoint(
                moisture_percent=entry["moisture_percent"],
                water_table_depth_cm=entry["water_table_depth_cm"],
            )
            for entry in data["water_table_curve"]
        )
        moisture_values = [point.moisture_percent for point in curve]
        if moisture_values != sorted(moisture_values):
            raise ValueError("water_table_curve must be sorted ascending by moisture_percent")
        if len(curve) < 2:
            raise ValueError("water_table_curve needs at least two points to interpolate")

        return cls(
            provisional=bool(data["provisional"]),
            salinity_breakpoints=breakpoints,
            water_table_curve=curve,
        )

    @classmethod
    def load(cls, path: str | Path) -> "Calibration":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def load_calibration(path: str | Path) -> Calibration:
    """Load a Calibration from a YAML file. The name matches SensorProfile.load
    and the other loaders in this project so every layer looks the same."""
    return Calibration.load(path)


def classify_salinity(calibration: Calibration, conductivity_us_cm: float) -> str:
    """Return the salinity class for a bulk conductivity reading.

    The last breakpoint always matches, since it is the catch-all for any
    value above every declared boundary.
    """
    for breakpoint in calibration.salinity_breakpoints:
        if conductivity_us_cm <= breakpoint.max_conductivity_us_cm:
            return breakpoint.salinity_class
    return calibration.salinity_breakpoints[-1].salinity_class


def water_table_depth_cm(calibration: Calibration, moisture_percent: float) -> float:
    """Return the estimated water-table depth for a moisture percentage.

    Piecewise linear interpolation across the calibration curve. A moisture
    value outside the curve's range clamps to the nearest end point, rather
    than extrapolating past a range faculty have not validated.
    """
    curve = calibration.water_table_curve

    if moisture_percent <= curve[0].moisture_percent:
        return curve[0].water_table_depth_cm
    if moisture_percent >= curve[-1].moisture_percent:
        return curve[-1].water_table_depth_cm

    for lower, upper in zip(curve, curve[1:]):
        if lower.moisture_percent <= moisture_percent <= upper.moisture_percent:
            span = upper.moisture_percent - lower.moisture_percent
            fraction = (moisture_percent - lower.moisture_percent) / span
            depth_span = upper.water_table_depth_cm - lower.water_table_depth_cm
            return lower.water_table_depth_cm + fraction * depth_span

    raise AssertionError("unreachable: moisture_percent was not within the curve range")
