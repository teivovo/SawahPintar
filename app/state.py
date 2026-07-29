"""Assembles everything the server needs into one object.

Built once at startup by app.main, and once per test with fakes standing in
for the parts Plan 2 and real hardware provide. Kept separate from
server.py so tests can construct a state without importing FastAPI at all.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import duckdb

from app.compare import compare_readings
from app.config import WorkshopConfig
from app.detector import StepChangeDetector
from app.registers import open_transport_for_inspection
from app.sensor.profile import SensorProfile
from app.sensor.reader import SensorReader
from app.sensor.simulator import SimulatedReader
from app.sensor.transport import SerialTransport
from app.storage import db
from app.storage.models import Reading

WEB_DIR = Path(__file__).parent / "web"


def build_reader(port: str, profile_path: str, sensor_id: str, mode: str) -> Any:
    """Construct a reader for one sensor slot.

    mode 'simulate' returns a SimulatedReader; mode 'live' returns a
    SensorReader over a real serial port; mode 'off' returns None, meaning
    the plot is drawn on the map but has no sensor and never opens a feed.
    Kept local to this plan rather than depending on app.acquire, which was
    not part of the interface contract this plan was given to build on.
    """
    if mode == "off":
        return None
    if mode == "simulate":
        return SimulatedReader(sensor_id)
    profile = SensorProfile.load(profile_path)
    return SensorReader(sensor_id, profile, SerialTransport(port, profile))


# The three farmer-facing plot states, keyed off the worst advice severity
# on the plot. The advice card severity strings are the colour names the
# insight engine emits (app.insights.models.Severity values): green, amber,
# red. A plot with no reading yet, or with no sensor (mode 'off'), is idle.
_SEVERITY_TO_STATUS = {"green": ("good", 1), "amber": ("attention", 2), "red": ("critical", 3)}


def zone_status(reading: Reading | None, advice: list, mode: str) -> str:
    """Overall plot state for the field map: good, attention, critical or idle."""
    if mode == "off" or reading is None:
        return "idle"
    worst_rank = 0
    label = "good"
    for card in advice:
        status_label, rank = _SEVERITY_TO_STATUS.get(card.severity, ("good", 1))
        if rank > worst_rank:
            worst_rank, label = rank, status_label
    return label


def default_evaluate(
    reading: Reading, stage: str, calibration: Any, rules: Any, content: Any
) -> list:
    """Fallback used only if no insight engine has been wired in.

    Returns no advice cards. The real implementation is
    app.insights.engine.evaluate from Plan 2; see the Assumed interfaces
    section of this plan for the reconciliation point.
    """
    return []


def serialise_reading(reading: Reading | None) -> dict | None:
    """Turn a Reading into a JSON-safe dict, or None if there is none yet."""
    if reading is None:
        return None
    return {
        "timestamp": reading.timestamp.isoformat(),
        "sensor_id": reading.sensor_id,
        "values": dict(reading.values),
        "quality": reading.quality,
        "source": reading.source,
    }


def serialise_advice(cards: list) -> list[dict]:
    """Turn a list of duck-typed advice cards into JSON-safe dicts.

    Reads only the six attribute names the Assumed interfaces section of
    this plan documents, so this function works against the real
    AdviceCard from Plan 2 or against any test stand-in with the same
    shape.
    """
    return [
        {
            "icon": card.icon,
            "severity": card.severity,
            "headline": card.headline,
            "body": card.body,
            "subtitle_en": card.subtitle_en,
            "rule_group": card.rule_group,
        }
        for card in cards
    ]


@dataclass
class WorkshopState:
    """Live, mutable state shared by every route and the websocket loop."""

    con: duckdb.DuckDBPyConnection
    config: WorkshopConfig
    config_path: Path
    readers: dict[str, Any] = field(default_factory=dict)
    detectors: dict[str, StepChangeDetector] = field(default_factory=dict)
    evaluate_fn: Callable[..., list] = default_evaluate
    calibration: Any = None
    rules: Any = None
    content: Any = None
    # The loaded Permentan 13 of 2022 dose table (app.insights.permentan),
    # or None if it has not been wired in. None is a legitimate state, not
    # only a startup failure: it is what every test in this codebase builds
    # by default, and POST /api/puts treats it as "no dose available" and
    # simply omits the phosphorus_dose key rather than erroring.
    permentan: Any = None
    field_card: Any = None
    puts_history: list = field(default_factory=list)
    transport_factory: Callable[..., Any] = open_transport_for_inspection

    @classmethod
    def build(
        cls,
        con: duckdb.DuckDBPyConnection,
        config: WorkshopConfig,
        config_path: str | Path,
        evaluate_fn: Callable[..., list] = default_evaluate,
        calibration: Any = None,
        rules: Any = None,
        content: Any = None,
        permentan: Any = None,
    ) -> "WorkshopState":
        readers = {
            sensor_id: build_reader(binding.port, binding.profile, sensor_id, binding.mode)
            for sensor_id, binding in config.sensors.items()
        }
        detectors = {sensor_id: StepChangeDetector() for sensor_id in config.sensors}
        return cls(
            con=con,
            config=config,
            config_path=Path(config_path),
            readers=readers,
            detectors=detectors,
            evaluate_fn=evaluate_fn,
            calibration=calibration,
            rules=rules,
            content=content,
            permentan=permentan,
        )

    def latest_advice(self, sensor_id: str, reading: Reading) -> list:
        return self.evaluate_fn(
            reading, self.config.growth_stage, self.calibration, self.rules, self.content
        )


def build_state_payload(state: WorkshopState) -> dict:
    """Build the JSON body for GET /api/state.

    Reports the latest reading and advice for every configured sensor, the
    shared growth stage and language, and a top level simulated flag that
    is True whenever any active sensor's latest reading is not from a live
    probe. The farmer-facing SIMULASI watermark reads only this flag. When
    exactly two sensors are configured and both have a reading, a
    comparison block is included for the split view.
    """
    sensors: dict[str, dict] = {}
    simulated = False
    readings: dict[str, Reading] = {}

    for sensor_id, binding in state.config.sensors.items():
        # A detached plot (mode 'off') has no sensor, so it reports no
        # reading and no advice regardless of any stale seeded history that
        # may exist for its id: it shows on the map as idle, not as a plot
        # carrying advice no probe produced.
        if binding.mode == "off":
            reading = None
        else:
            reading = db.latest(state.con, sensor_id)
        advice = state.latest_advice(sensor_id, reading) if reading is not None else []
        sensors[sensor_id] = {
            "reading": serialise_reading(reading),
            "advice": serialise_advice(advice),
            # Field-map metadata: the plot label, its outline, how the plot
            # is currently sourced, and its overall state. A plot with no
            # zone drawn yet is simply not shown on the map.
            "name": binding.name or sensor_id,
            "zone": binding.zone,
            "mode": binding.mode,
            "port": binding.port,
            "profile": binding.profile,
            "status": zone_status(reading, advice, binding.mode),
        }
        if reading is not None:
            readings[sensor_id] = reading
            if reading.source != Reading.SOURCE_LIVE:
                simulated = True

    payload = {
        "growth_stage": state.config.growth_stage,
        "language": state.config.language,
        # site_name and transplanting_date are exposed here, not only saved
        # to config.json, so the operator console can pre-fill its form with
        # what is already set rather than showing blank fields over live
        # values. See the operator console pre-fill on load.
        "site_name": state.config.site_name,
        "transplanting_date": state.config.transplanting_date,
        "field_image": state.config.field_image,
        "field_view": list(state.config.field_view),
        "simulated": simulated,
        "sensors": sensors,
    }

    sensor_ids = list(state.config.sensors)
    if len(sensor_ids) == 2 and all(sid in readings for sid in sensor_ids):
        payload["comparison"] = {
            "sensor_a": sensor_ids[0],
            "sensor_b": sensor_ids[1],
            "metrics": compare_readings(readings[sensor_ids[0]], readings[sensor_ids[1]]),
        }

    return payload


def build_history_payload(
    state: WorkshopState, sensor_id: str, metric: str, limit: int = 500
) -> dict:
    """Build the JSON body for GET /api/history."""
    rows = db.series(state.con, sensor_id, metric, limit=limit)
    return {
        "sensor_id": sensor_id,
        "metric": metric,
        "points": [
            {"timestamp": ts.isoformat(), "value": value, "source": source}
            for ts, value, source in rows
        ],
    }


def build_ws_payload(
    state: WorkshopState, sensor_id: str, reading: Reading, advice: list, probe_inserted: bool
) -> dict:
    """Build one websocket message: a fresh reading, its advice, whether
    this is the reading on which the probe insertion moment was detected,
    and a comparison block once a second configured sensor has a reading
    of its own."""
    binding = state.config.sensors.get(sensor_id)
    payload = {
        "sensor_id": sensor_id,
        "reading": serialise_reading(reading),
        "advice": serialise_advice(advice),
        "probe_inserted": probe_inserted,
        "growth_stage": state.config.growth_stage,
        # Carried on every tick, not only in GET /api/state, so a language
        # toggle from the operator console reaches a farmer display that is
        # already open in another window on its next broadcast, rather than
        # only taking effect on a fresh page load.
        "language": state.config.language,
        "simulated": reading.source != Reading.SOURCE_LIVE,
        # The plot's overall state, so the field map recolours this plot on
        # the tick rather than recomputing severity itself.
        "status": zone_status(reading, advice, binding.mode if binding else "simulate"),
    }

    sensor_ids = list(state.config.sensors)
    if len(sensor_ids) == 2:
        other_id = sensor_ids[1] if sensor_ids[0] == sensor_id else sensor_ids[0]
        other_reading = db.latest(state.con, other_id)
        if other_reading is not None:
            sensor_a, sensor_b = sensor_ids
            reading_a = reading if sensor_a == sensor_id else other_reading
            reading_b = reading if sensor_b == sensor_id else other_reading
            payload["comparison"] = {
                "sensor_a": sensor_a,
                "sensor_b": sensor_b,
                "metrics": compare_readings(reading_a, reading_b),
            }

    return payload
