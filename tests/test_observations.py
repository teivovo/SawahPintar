from datetime import datetime, timedelta, timezone

from app.config import PutsResult
from app.observations import initialise_schema, list_observations, record_observation
from app.storage import db

NOW = datetime(2026, 7, 23, 11, 0, tzinfo=timezone.utc)


def make_con():
    connection = db.connect(":memory:")
    initialise_schema(connection)
    return connection


def test_initialise_schema_is_idempotent():
    con = make_con()
    initialise_schema(con)
    assert list_observations(con) == []
    con.close()


def test_record_and_list_one_observation():
    con = make_con()
    puts = PutsResult(
        nitrogen_class="rendah", phosphorus_class="sedang", potassium_class="tinggi", ph=6.4
    )
    record_observation(con, NOW, "Desa Bontomanai", "tillering", "probe-a", 780.0, puts)

    observations = list_observations(con)

    assert len(observations) == 1
    assert observations[0]["site_name"] == "Desa Bontomanai"
    assert observations[0]["nitrogen_class"] == "rendah"
    assert observations[0]["conductivity"] == 780.0
    con.close()


def test_observations_are_ordered_oldest_first():
    con = make_con()
    puts = PutsResult(nitrogen_class="rendah", phosphorus_class="rendah", potassium_class="rendah")
    record_observation(con, NOW + timedelta(days=1), "Site", "flowering", "probe-a", 100.0, puts)
    record_observation(con, NOW, "Site", "tillering", "probe-a", 90.0, puts)

    observations = list_observations(con)

    assert [o["growth_stage"] for o in observations] == ["tillering", "flowering"]
    con.close()


def test_conductivity_may_be_recorded_as_none_when_no_reading_exists():
    con = make_con()
    puts = PutsResult(nitrogen_class="sedang", phosphorus_class="sedang", potassium_class="sedang")
    record_observation(con, NOW, "Site", "ripening", "probe-a", None, puts)

    observations = list_observations(con)

    assert observations[0]["conductivity"] is None
    con.close()
