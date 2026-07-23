from datetime import datetime, timezone

from app.reset import reset_live_data
from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def make_con():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    return connection


def test_clears_live_and_simulated_rows():
    con = make_con()
    db.insert_readings(
        con,
        [
            Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_LIVE),
            Reading(NOW, "probe-a", {"moisture": 2.0}, source=Reading.SOURCE_SIM),
        ],
    )
    deleted = reset_live_data(con)
    assert deleted == 2
    assert db.count_rows(con) == 0
    con.close()


def test_never_touches_seeded_rows():
    con = make_con()
    db.insert_readings(
        con,
        [
            Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SEED),
            Reading(NOW, "probe-a", {"moisture": 2.0}, source=Reading.SOURCE_LIVE),
        ],
    )
    reset_live_data(con)
    assert db.count_rows(con) == 1
    assert db.series(con, "probe-a", "moisture")[0][2] == "seed"
    con.close()


def test_returns_zero_when_nothing_to_clear():
    con = make_con()
    db.insert_reading(
        con, Reading(NOW, "probe-a", {"moisture": 1.0}, source=Reading.SOURCE_SEED)
    )
    assert reset_live_data(con) == 0
    con.close()
