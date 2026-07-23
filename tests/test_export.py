import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from app.config import PutsResult
from app.export import export_session
from app.observations import initialise_schema as initialise_puts_schema, record_observation
from app.storage import db
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 5, 0, tzinfo=timezone.utc)


@pytest.fixture
def con():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    yield connection
    connection.close()


def test_export_raises_when_nothing_to_export(con, tmp_path):
    with pytest.raises(ValueError, match="no readings"):
        export_session(con, tmp_path)


def test_export_writes_both_files(con, tmp_path):
    db.insert_reading(
        con,
        Reading(NOW, "probe-a", {"moisture": 42.0, "ph": 5.6}, source=Reading.SOURCE_LIVE),
    )
    paths = export_session(con, tmp_path, now=NOW)
    assert Path(paths["parquet"]).exists()
    assert Path(paths["csv"]).exists()


def test_exported_csv_matches_row_count(con, tmp_path):
    db.insert_readings(
        con,
        [
            Reading(NOW, "probe-a", {"moisture": 1.0}),
            Reading(NOW, "probe-a", {"ph": 5.5}),
        ],
    )
    paths = export_session(con, tmp_path, now=NOW)
    with open(paths["csv"], newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert {"ts", "sensor_id", "metric", "value", "quality", "source"} <= set(rows[0].keys())


def test_exported_parquet_matches_row_count(con, tmp_path):
    db.insert_readings(
        con,
        [Reading(NOW, "probe-a", {"moisture": float(i)}) for i in range(5)],
    )
    paths = export_session(con, tmp_path, now=NOW)
    row_count = duckdb.sql(f"SELECT count(*) FROM '{paths['parquet']}'").fetchone()[0]
    assert row_count == 5


def test_export_creates_out_dir_if_missing(con, tmp_path):
    db.insert_reading(con, Reading(NOW, "probe-a", {"moisture": 1.0}))
    target = tmp_path / "nested" / "exports"
    paths = export_session(con, target, now=NOW)
    assert Path(paths["csv"]).parent == target


def test_export_file_names_carry_a_utc_timestamp_and_the_site_name(con, tmp_path):
    db.insert_reading(con, Reading(NOW, "probe-a", {"moisture": 1.0}))
    paths = export_session(con, tmp_path, site_name="Blok A", now=NOW)
    assert "20260723T050000Z" in paths["parquet"]
    assert "Blok_A" in paths["parquet"]
    assert "20260723T050000Z" in paths["csv"]
    assert "Blok_A" in paths["csv"]


def test_export_falls_back_to_a_placeholder_when_site_name_is_blank(con, tmp_path):
    db.insert_reading(con, Reading(NOW, "probe-a", {"moisture": 1.0}))
    paths = export_session(con, tmp_path, site_name="", now=NOW)
    assert Path(paths["parquet"]).name == "readings_20260723T050000Z_site.parquet"


def test_a_second_export_never_overwrites_the_first(con, tmp_path):
    """The second focus group's export must not destroy the first group's.
    Two exports a minute apart from the same site land at two distinct
    paths, and both files are still present afterwards."""
    db.insert_reading(con, Reading(NOW, "probe-a", {"moisture": 1.0}))
    first = export_session(con, tmp_path, site_name="Blok A", now=NOW)

    db.insert_reading(con, Reading(NOW, "probe-a", {"moisture": 2.0}))
    second = export_session(con, tmp_path, site_name="Blok A", now=NOW + timedelta(minutes=1))

    assert first["parquet"] != second["parquet"]
    assert Path(first["parquet"]).exists()
    assert Path(second["parquet"]).exists()


def test_export_includes_puts_observations_when_any_were_recorded(con, tmp_path):
    """This is the one research output that cannot be reconstructed: the
    paired PUTS-and-probe dataset design spec section 10 exists for. It
    must travel with every export, not only live in workshop.duckdb."""
    db.insert_reading(con, Reading(NOW, "probe-a", {"conductivity": 640.0}))
    initialise_puts_schema(con)
    record_observation(
        con, NOW, "Blok A", "tillering", "probe-a", 640.0,
        PutsResult(nitrogen_class="rendah", phosphorus_class="sedang", potassium_class="tinggi"),
    )

    paths = export_session(con, tmp_path, site_name="Blok A", now=NOW)

    assert "puts_parquet" in paths
    assert "puts_csv" in paths
    assert Path(paths["puts_parquet"]).exists()
    row_count = duckdb.sql(f"SELECT count(*) FROM '{paths['puts_parquet']}'").fetchone()[0]
    assert row_count == 1


def test_export_omits_puts_files_when_no_puts_result_was_recorded(con, tmp_path):
    db.insert_reading(con, Reading(NOW, "probe-a", {"moisture": 1.0}))
    paths = export_session(con, tmp_path, now=NOW)
    assert "puts_parquet" not in paths
    assert "puts_csv" not in paths


def test_export_succeeds_even_if_the_puts_table_was_never_created(tmp_path):
    """export_session must not depend on POST /api/puts having run first in
    this connection's lifetime to create puts_observations."""
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    db.insert_reading(connection, Reading(NOW, "probe-a", {"moisture": 1.0}))
    paths = export_session(connection, tmp_path, now=NOW)
    assert Path(paths["parquet"]).exists()
    connection.close()


def test_export_writes_a_readme_carrying_the_nutrient_caveat(con, tmp_path):
    db.insert_reading(con, Reading(NOW, "probe-a", {"moisture": 1.0}))
    paths = export_session(con, tmp_path, now=NOW)
    readme = Path(paths["readme"]).read_text(encoding="utf-8")
    assert "must not have its nitrogen, phosphorus and potassium outputs" in readme
    assert "Permentan" in readme
