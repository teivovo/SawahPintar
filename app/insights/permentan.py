"""Permentan 13 of 2022 status-class dose table.

Fertiliser recommendations in this application come only from operator
entered PUTS status classes read against this table, never from the
probe. Design spec section 8.4: the probe's nitrogen, phosphorus and
potassium registers are three functions of one conductivity measurement
and must never be used to derive a dose. The paired observation log,
design spec section 10, storing a PUTS result beside the concurrent
probe reading, is already implemented by the interface and packaging
plan's app.observations module; this module supplies only the dose
lookup those PUTS classes feed into, and never duplicates that log.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PhosphorusDose:
    """The official Permentan phosphorus dose for one status class."""

    status: str
    p2o5_kg_per_ha: float
    sp36_kg_per_ha: float


@dataclass(frozen=True)
class PermentanTable:
    """The Permentan 13 of 2022 status class boundaries and phosphorus doses."""

    phosphorus_low_max_exclusive: float
    phosphorus_medium_max_inclusive: float
    phosphorus_doses: dict[str, PhosphorusDose]
    potassium_low_max_exclusive: float
    potassium_medium_max_inclusive: float

    @classmethod
    def from_dict(cls, data: dict) -> "PermentanTable":
        phosphorus = data["phosphorus"]
        potassium = data["potassium"]
        doses = {
            status: PhosphorusDose(
                status=status,
                p2o5_kg_per_ha=values["p2o5_kg_per_ha"],
                sp36_kg_per_ha=values["sp36_kg_per_ha"],
            )
            for status, values in phosphorus["doses"].items()
        }
        for required in ("rendah", "sedang", "tinggi"):
            if required not in doses:
                raise ValueError(f"phosphorus doses is missing status: {required}")

        return cls(
            phosphorus_low_max_exclusive=phosphorus["low_max_exclusive"],
            phosphorus_medium_max_inclusive=phosphorus["medium_max_inclusive"],
            phosphorus_doses=doses,
            potassium_low_max_exclusive=potassium["low_max_exclusive"],
            potassium_medium_max_inclusive=potassium["medium_max_inclusive"],
        )

    @classmethod
    def load(cls, path: str | Path) -> "PermentanTable":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def load_permentan(path: str | Path) -> PermentanTable:
    """Load a PermentanTable from a YAML file. The name matches every other
    loader in this package."""
    return PermentanTable.load(path)


def classify_phosphorus(table: PermentanTable, p2o5_mg_per_100g: float) -> str:
    """Return the Permentan status class for a P2O5 soil test result."""
    if p2o5_mg_per_100g < table.phosphorus_low_max_exclusive:
        return "rendah"
    if p2o5_mg_per_100g <= table.phosphorus_medium_max_inclusive:
        return "sedang"
    return "tinggi"


def classify_potassium(table: PermentanTable, k2o_mg_per_100g: float) -> str:
    """Return the Permentan status class for a K2O soil test result."""
    if k2o_mg_per_100g < table.potassium_low_max_exclusive:
        return "rendah"
    if k2o_mg_per_100g <= table.potassium_medium_max_inclusive:
        return "sedang"
    return "tinggi"


def dose_for_status(table: PermentanTable, status: str) -> PhosphorusDose:
    """Return the official phosphorus dose for a PUTS or lab status class.

    Raises KeyError with the offending status named, rather than silently
    returning a default, since a mistyped status must never produce a
    silently wrong dose.
    """
    normalised = status.strip().lower()
    try:
        return table.phosphorus_doses[normalised]
    except KeyError:
        raise KeyError(f"no Permentan dose for status: {status}") from None
