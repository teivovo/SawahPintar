"""Workshop configuration.

The per-set settings an operator adjusts in the field, plus the domain
models the operator console fills in that no probe can supply: the field
card and the PUTS result. See design spec sections 8.2 and 9.2.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

GROWTH_STAGES = (
    "land_preparation",
    "transplanting",
    "tillering",
    "panicle_initiation",
    "flowering",
    "ripening",
)

LANGUAGES = ("id", "en")

DEFAULT_SENSOR_ID = "probe-a"


@dataclass
class SensorBinding:
    """How one sensor slot is currently wired up."""

    port: str = "COM9"
    profile: str = "data/profiles/sn3002.json"
    mode: str = "simulate"


@dataclass
class FieldCard:
    """Inputs Rice Crop Manager needs that no probe can supply.

    Captured once per focus group in the operator console. See design spec
    section 8.2.
    """

    field_size_ha: float | None = None
    variety: str = ""
    seedling_age_days: int | None = None
    water_source: str = ""
    previous_yield_t_ha: float | None = None
    fertiliser_available: str = ""


@dataclass
class PutsResult:
    """One PUTS field kit reading, entered by the operator.

    The three class fields each take 'rendah', 'sedang' or 'tinggi',
    matching Permentan 13 of 2022.
    """

    nitrogen_class: str
    phosphorus_class: str
    potassium_class: str
    ph: float | None = None


@dataclass
class WorkshopConfig:
    """Per-set settings, persisted to config.json."""

    language: str = "id"
    site_name: str = ""
    growth_stage: str = GROWTH_STAGES[0]
    transplanting_date: str | None = None
    sensors: dict[str, SensorBinding] = field(
        default_factory=lambda: {DEFAULT_SENSOR_ID: SensorBinding()}
    )

    def __post_init__(self) -> None:
        if self.language not in LANGUAGES:
            raise ValueError(f"language must be one of {LANGUAGES}")
        if self.growth_stage not in GROWTH_STAGES:
            raise ValueError(f"growth_stage must be one of {GROWTH_STAGES}")

    @classmethod
    def from_dict(cls, data: dict) -> "WorkshopConfig":
        raw_sensors = data.get("sensors") or {DEFAULT_SENSOR_ID: {}}
        sensors = {
            sensor_id: SensorBinding(**binding) for sensor_id, binding in raw_sensors.items()
        }
        return cls(
            language=data.get("language", "id"),
            site_name=data.get("site_name", ""),
            growth_stage=data.get("growth_stage", GROWTH_STAGES[0]),
            transplanting_date=data.get("transplanting_date"),
            sensors=sensors,
        )

    @classmethod
    def load(cls, path: str | Path) -> "WorkshopConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "site_name": self.site_name,
            "growth_stage": self.growth_stage,
            "transplanting_date": self.transplanting_date,
            "sensors": {
                sensor_id: asdict(binding) for sensor_id, binding in self.sensors.items()
            },
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
