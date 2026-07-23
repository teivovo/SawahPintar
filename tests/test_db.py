from datetime import datetime, timedelta, timezone

import pytest

from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc)


@pytest.fixture
def con():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    yield connection
    connection.close()


def test_initialise_schema_is_idempotent(con):
    db.initialise_schema(con)
    assert db.count_rows(con) == 0


def test_insert_and_read_back_a_reading(con):
    db.insert_reading(
        con,
        Reading(
            timestamp=NOW,
            sensor_id="probe-a",
            values={"moisture": 65.8, "ph": 5.6},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_LIVE,
        ),
    )
    assert db.count_rows(con) == 2

    latest = db.latest(con, "probe-a")
    assert latest is not None
    assert latest.values == {"moisture": 65.8, "ph": 5.6}
    assert latest.quality == "ok"
    assert latest.source == "live"


def test_latest_returns_none_for_unknown_sensor(con):
    assert db.latest(con, "nobody") is None


def test_latest_picks_the_newest_timestamp(con):
    db.insert_readings(
        con,
        [
            Reading(NOW, "probe-a", {"moisture": 10.0}),
            Reading(NOW + timedelta(minutes=5), "probe-a", {"moisture": 20.0}),
            Reading(NOW - timedelta(minutes=5), "probe-a", {"moisture": 30.0}),
        ],
    )
    latest = db.latest(con, "probe-a")
    assert latest.values["moisture"] == 20.0


def test_series_returns_oldest_first_and_respects_limit(con):
    db.insert_readings(
        con,
        [
            Reading(NOW + timedelta(minutes=i), "probe-a", {"moisture": float(i)})
            for i in range(10)
        ],
    )
    rows = db.series(con, "probe-a", "moisture", limit=3)
    assert [row[1] for row in rows] == [7.0, 8.0, 9.0]
    assert rows[0][2] == "live"


def test_series_isolates_sensors_and_metrics(con):
    db.insert_readings(
        con,
        [
            Reading(NOW, "probe-a", {"moisture": 1.0, "ph": 6.0}),
            Reading(NOW, "probe-b", {"moisture": 2.0}),
        ],
    )
    assert [row[1] for row in db.series(con, "probe-a", "moisture")] == [1.0]
    assert [row[1] for row in db.series(con, "probe-b", "moisture")] == [2.0]
    assert [row[1] for row in db.series(con, "probe-a", "ph")] == [6.0]


def test_source_flag_is_preserved(con):
    db.insert_reading(
        con,
        Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SEED),
    )
    rows = db.series(con, "probe-a", "moisture")
    assert rows[0][2] == "seed"


def test_latest_reports_uniform_quality_and_source_unchanged(con):
    db.insert_reading(
        con,
        Reading(
            NOW,
            "probe-a",
            values={"moisture": 65.8, "ph": 5.6},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_SEED,
        ),
    )
    latest = db.latest(con, "probe-a")
    assert latest.quality == Reading.QUALITY_OK
    assert latest.source == Reading.SOURCE_SEED


def test_latest_degrades_quality_when_rows_disagree(con):
    # Two rows land on the same timestamp with different quality flags, for
    # example a re-seed colliding with a live timestamp. insert_readings
    # cannot produce this directly since one Reading is uniform by
    # construction, so the rows are written with two separate calls.
    db.insert_reading(
        con,
        Reading(
            NOW,
            "probe-a",
            values={"moisture": 65.8},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_LIVE,
        ),
    )
    db.insert_reading(
        con,
        Reading(
            NOW,
            "probe-a",
            values={"ph": 5.6},
            quality=Reading.QUALITY_ERROR,
            source=Reading.SOURCE_LIVE,
        ),
    )
    latest = db.latest(con, "probe-a")
    assert latest.values == {"moisture": 65.8, "ph": 5.6}
    assert latest.quality == Reading.QUALITY_PARTIAL


def test_latest_never_reports_a_mixed_reading_as_purely_live(con):
    db.insert_reading(
        con,
        Reading(
            NOW,
            "probe-a",
            values={"moisture": 65.8},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_LIVE,
        ),
    )
    db.insert_reading(
        con,
        Reading(
            NOW,
            "probe-a",
            values={"ph": 5.6},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_SEED,
        ),
    )
    latest = db.latest(con, "probe-a")
    assert latest.source == Reading.SOURCE_SEED
    assert latest.source != Reading.SOURCE_LIVE


def test_latest_prefers_seed_over_sim_when_both_present(con):
    db.insert_reading(
        con,
        Reading(
            NOW,
            "probe-a",
            values={"moisture": 65.8},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_SIM,
        ),
    )
    db.insert_reading(
        con,
        Reading(
            NOW,
            "probe-a",
            values={"ph": 5.6},
            quality=Reading.QUALITY_OK,
            source=Reading.SOURCE_SEED,
        ),
    )
    latest = db.latest(con, "probe-a")
    assert latest.source == Reading.SOURCE_SEED


def test_concurrent_readers_and_writer_do_not_corrupt_the_connection(tmp_path):
    """A writer thread and reader threads sharing one connection must not
    crash or return corrupt results.

    This reproduces the field failure that a warm developer machine hid: the
    websocket loop writes a reading on one thread while a REST request reads
    state on another, both through the one shared DuckDB connection. Without
    serialisation this raised 'NoneType object is not subscriptable' from a
    half-finished query, or crashed the interpreter with a released-GIL fatal
    error. It is a race, so this hammers it hard enough to make the collision
    near-certain if the lock is ever removed.
    """
    import threading

    connection = db.connect(str(tmp_path / "concurrent.duckdb"))
    db.initialise_schema(connection)
    # Seed a baseline so latest() always has a row to fold.
    db.insert_reading(
        connection,
        Reading(NOW, "probe-a", {"moisture": 1.0, "ph": 6.0}),
    )

    errors: list[Exception] = []
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            try:
                db.insert_reading(
                    connection,
                    Reading(
                        NOW + timedelta(seconds=i),
                        "probe-a",
                        {"moisture": float(i % 50), "ph": 6.0},
                    ),
                )
            except Exception as error:  # noqa: BLE001 - the test records it
                errors.append(error)
                return
            i += 1

    def reader():
        for _ in range(120):
            try:
                latest = db.latest(connection, "probe-a")
                assert latest is not None
                db.series(connection, "probe-a", "moisture", limit=50)
                db.count_rows(connection)
            except Exception as error:  # noqa: BLE001 - the test records it
                errors.append(error)
                return

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads[1:]:
        thread.join()
    stop.set()
    threads[0].join()

    connection.close()
    assert errors == [], f"concurrent access raised: {errors[0]!r}"
