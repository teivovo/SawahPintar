"""The paired PUTS observation log.

Whenever an operator enters PUTS classes, this stores them against the
concurrent probe reading, the site, the date and the growth stage. Across
sites and seasons this accumulates paired observations of a chemically
extracted nutrient status beside an in-situ conductivity reading. This is a
research output, not a calibration input: design spec sections 8.4 and 10
explain why the probe's own nutrient registers must never be calibrated
against it.
"""

from datetime import datetime

import duckdb

from app.config import PutsResult
from app.storage.db import CONNECTION_LOCK

SCHEMA = """
CREATE TABLE IF NOT EXISTS puts_observations (
    ts                TIMESTAMPTZ NOT NULL,
    site_name         VARCHAR     NOT NULL,
    growth_stage      VARCHAR     NOT NULL,
    sensor_id         VARCHAR     NOT NULL,
    conductivity      DOUBLE,
    nitrogen_class    VARCHAR     NOT NULL,
    phosphorus_class  VARCHAR     NOT NULL,
    potassium_class   VARCHAR     NOT NULL,
    puts_ph           DOUBLE
);
"""

COLUMNS = (
    "ts",
    "site_name",
    "growth_stage",
    "sensor_id",
    "conductivity",
    "nitrogen_class",
    "phosphorus_class",
    "potassium_class",
    "puts_ph",
)


def initialise_schema(con: duckdb.DuckDBPyConnection) -> None:
    with CONNECTION_LOCK:
        con.execute(SCHEMA)


def record_observation(
    con: duckdb.DuckDBPyConnection,
    now: datetime,
    site_name: str,
    growth_stage: str,
    sensor_id: str,
    conductivity: float | None,
    puts: PutsResult,
) -> None:
    """Store one paired observation: a PUTS result beside the concurrent
    probe conductivity reading, the site, the date and the growth stage."""
    with CONNECTION_LOCK:
        con.execute(
            "INSERT INTO puts_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                now,
                site_name,
                growth_stage,
                sensor_id,
                conductivity,
                puts.nitrogen_class,
                puts.phosphorus_class,
                puts.potassium_class,
                puts.ph,
            ],
        )


def list_observations(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Return every paired observation, oldest first."""
    with CONNECTION_LOCK:
        rows = con.execute(
            f"SELECT {', '.join(COLUMNS)} FROM puts_observations ORDER BY ts"
        ).fetchall()
    return [dict(zip(COLUMNS, row)) for row in rows]
