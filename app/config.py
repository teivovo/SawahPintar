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
    """How one sensor slot is currently wired up.

    ``name`` is the farmer-facing plot label shown on the field map (for
    example "Blok 1"); it falls back to the sensor id when empty. ``zone``
    is the plot outline the operator drew in the zone editor, a list of
    ``[x, y]`` points in the field image's coordinate space
    (``WorkshopConfig.field_view``). It is None until a zone has been
    placed, in which case that sensor simply does not appear on the map.
    """

    port: str = "COM9"
    profile: str = "data/profiles/sn3002.json"
    mode: str = "simulate"
    name: str = ""
    zone: list | None = None


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
    # The aerial photo the field map is drawn on, served from app/web, and
    # the coordinate space (width, height) that every sensor ``zone``
    # polygon is expressed in. A drone or satellite shot of the real plot
    # can replace the bundled default without touching any zone as long as
    # the operator re-traces against the new image.
    field_image: str = "assets/field-default.jpg"
    field_view: list = field(default_factory=lambda: [1537, 1023])
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
            field_image=data.get("field_image", "assets/field-default.jpg"),
            field_view=data.get("field_view") or [1537, 1023],
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
            "field_image": self.field_image,
            "field_view": list(self.field_view),
            "sensors": {
                sensor_id: asdict(binding) for sensor_id, binding in self.sensors.items()
            },
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
