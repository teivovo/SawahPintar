"""The Reading record shared by every layer of the application."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Reading:
    """One observation of a sensor at one moment.

    Values are decoded and scaled, so moisture is a percentage and
    temperature is degrees Celsius. The source flag keeps seeded
    demonstration data permanently distinguishable from measured data.
    """

    QUALITY_OK = "ok"
    QUALITY_PARTIAL = "partial"
    QUALITY_ERROR = "error"

    SOURCE_LIVE = "live"
    SOURCE_SEED = "seed"
    SOURCE_SIM = "sim"

    timestamp: datetime
    sensor_id: str
    values: dict[str, float] = field(default_factory=dict)
    quality: str = QUALITY_OK
    source: str = SOURCE_LIVE

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Reading.timestamp must be timezone-aware")
        # Every stored timestamp is normalised to UTC rather than rejected if
        # it arrives in another zone. DuckDB's TIMESTAMPTZ returns values in
        # the session's local timezone, not UTC, so a Reading reconstructed
        # from a database row is timezone-aware but not necessarily UTC; a
        # strict UTC-only guard here would make app/storage/db.py's latest()
        # raise on every read. Normalising instead keeps the instant intact
        # and gives every layer of the application one consistent offset.
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))
