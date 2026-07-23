"""DuckDB storage.

Readings are stored in long format, one row per metric, so that probes with
different register sets share a table without a schema migration.
"""

import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import duckdb

from app.storage.models import Reading

# A single process-wide reentrant lock guarding every access to a DuckDB
# connection.
#
# A DuckDB connection object is NOT safe to use from more than one thread at
# once. The server hits this directly: the websocket broadcast loop writes a
# reading on one thread while a REST request reads state on another, both
# through the one shared connection. Concurrent access corrupts the
# connection's in-flight result and, in the worst case, crashes the
# interpreter with "the GIL is released, the current Python thread state is
# NULL". It is a race, so it passes on a warm developer machine and only bites
# on a cold field laptop where the timing collides, which is exactly where it
# must not.
#
# Every function here, and in observations.py, reset.py and export.py, holds
# this lock around its whole execute-and-fetch sequence. That sequence is the
# atomic unit: DuckDB keeps the current result on the connection, so locking a
# single method call would not be enough. Reentrant so that a function holding
# it may call another that also takes it. The lock is uncontended in the tests,
# which each use their own single-threaded connection, so it costs nothing
# there. DuckDB's own documented multi-thread pattern is a cursor per thread;
# a single lock is chosen instead because this application's throughput is one
# reading every couple of seconds, where serialising is simpler and provably
# correct.
CONNECTION_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts          TIMESTAMPTZ NOT NULL,
    sensor_id   VARCHAR     NOT NULL,
    metric      VARCHAR     NOT NULL,
    value       DOUBLE      NOT NULL,
    quality     VARCHAR     NOT NULL,
    source      VARCHAR     NOT NULL
);
"""


def connect(path: str | Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path))


def initialise_schema(con: duckdb.DuckDBPyConnection) -> None:
    with CONNECTION_LOCK:
        con.execute(SCHEMA)


def insert_reading(con: duckdb.DuckDBPyConnection, reading: Reading) -> None:
    insert_readings(con, [reading])


def insert_readings(
    con: duckdb.DuckDBPyConnection, readings: Iterable[Reading]
) -> None:
    rows = [
        (
            reading.timestamp,
            reading.sensor_id,
            metric,
            float(value),
            reading.quality,
            reading.source,
        )
        for reading in readings
        for metric, value in reading.values.items()
    ]
    if rows:
        with CONNECTION_LOCK:
            con.executemany("INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?)", rows)


def count_rows(con: duckdb.DuckDBPyConnection) -> int:
    with CONNECTION_LOCK:
        return con.execute("SELECT count(*) FROM readings").fetchone()[0]


def latest(con: duckdb.DuckDBPyConnection, sensor_id: str) -> Reading | None:
    """Return the most recent Reading for one sensor, or None if it has none.

    Every metric row stored at the newest timestamp is folded into a single
    Reading. In the normal case every one of those rows shares one quality
    and one source, taken from insert_readings writing a whole Reading in
    one call, and both are reported unchanged.

    That uniformity is not enforced by the schema, so this function
    guarantees a fallback for when it does not hold, for example a re-seed
    landing on the same timestamp as a live reading. If the rows do not all
    share one quality, the returned quality is degraded to
    Reading.QUALITY_PARTIAL rather than picking one at random. If the rows
    do not all share one source, the returned source is chosen by priority
    (seed, then sim, then live) so that a mix is never reported as purely
    Reading.SOURCE_LIVE - synthetic data must never be mistaken for
    measured data. Callers can therefore trust that a Reading with
    quality == Reading.QUALITY_OK and source == Reading.SOURCE_LIVE really
    is uniformly live at that instant.
    """
    with CONNECTION_LOCK:
        newest = con.execute(
            "SELECT max(ts) FROM readings WHERE sensor_id = ?", [sensor_id]
        ).fetchone()[0]
        if newest is None:
            return None

        rows = con.execute(
            "SELECT metric, value, quality, source FROM readings "
            "WHERE sensor_id = ? AND ts = ? ORDER BY metric",
            [sensor_id, newest],
        ).fetchall()

    qualities = {row[2] for row in rows}
    quality = qualities.pop() if len(qualities) == 1 else Reading.QUALITY_PARTIAL

    sources = {row[3] for row in rows}
    if len(sources) == 1:
        source = sources.pop()
    else:
        source_priority = (Reading.SOURCE_SEED, Reading.SOURCE_SIM, Reading.SOURCE_LIVE)
        source = next(
            candidate for candidate in source_priority if candidate in sources
        )

    return Reading(
        timestamp=newest,
        sensor_id=sensor_id,
        values={row[0]: row[1] for row in rows},
        quality=quality,
        source=source,
    )


def series(
    con: duckdb.DuckDBPyConnection, sensor_id: str, metric: str, limit: int = 500
) -> list[tuple[datetime, float, str]]:
    """Return the most recent points for one metric, oldest first."""
    with CONNECTION_LOCK:
        rows = con.execute(
            "SELECT ts, value, source FROM readings "
            "WHERE sensor_id = ? AND metric = ? ORDER BY ts DESC LIMIT ?",
            [sensor_id, metric, limit],
        ).fetchall()
    return [(row[0], row[1], row[2]) for row in reversed(rows)]
