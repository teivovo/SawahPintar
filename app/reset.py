"""Clearing live and simulated readings for a fresh focus group.

Never touches seeded history, since that would defeat the entire point of
the seed generator from Plan 1: charts must be alive the moment the
application opens, for every group that uses the laptop that day.
"""

import duckdb

from app.storage.db import CONNECTION_LOCK
from app.storage.models import Reading


def reset_live_data(con: duckdb.DuckDBPyConnection) -> int:
    """Delete every row whose source is not seed. Returns rows deleted.

    Depends only on the readings table schema Plan 1 documents in
    app.storage.db: columns ts, sensor_id, metric, value, quality, source.
    """
    with CONNECTION_LOCK:
        before = con.execute("SELECT count(*) FROM readings").fetchone()[0]
        con.execute("DELETE FROM readings WHERE source != ?", [Reading.SOURCE_SEED])
        after = con.execute("SELECT count(*) FROM readings").fetchone()[0]
    return before - after
