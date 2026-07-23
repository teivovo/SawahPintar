import pytest

from app.config import WorkshopConfig
from app.main import ensure_seed_history, load_insight_engine, main, parse_port
from app.state import default_evaluate
from app.storage import db


def test_parse_port_reads_the_flag():
    assert parse_port(["--port", "9000"]) == 9000


def test_parse_port_falls_back_to_the_default():
    assert parse_port([]) == 8420


def test_load_insight_engine_loads_the_real_plan_2_engine():
    """Plan 2 has landed in this repository: app.insights exists, so the
    guarded import in load_insight_engine succeeds and wires in the real
    evaluate function and the three loaded context objects, instead of
    falling back to app.state.default_evaluate.

    This test replaces the earlier
    test_load_insight_engine_falls_back_when_plan_2_is_absent, exactly as
    this plan's own note anticipated: once app.insights exists that test's
    name becomes inaccurate, and updating it to assert the real engine
    loads is expected, not a regression.
    """
    from app.insights.engine import evaluate

    evaluate_fn, calibration, rules, content = load_insight_engine()

    assert evaluate_fn is evaluate
    assert evaluate_fn is not default_evaluate
    assert calibration is not None
    assert rules is not None
    assert content is not None


def test_ensure_seed_history_seeds_every_configured_sensor_once():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict(
        {"sensors": {"probe-a": {"mode": "simulate"}, "probe-b": {"mode": "simulate"}}}
    )

    ensure_seed_history(connection, config)
    first_count = db.count_rows(connection)
    ensure_seed_history(connection, config)
    second_count = db.count_rows(connection)

    assert first_count > 0
    assert second_count == first_count
    connection.close()


def test_main_writes_a_startup_error_file_and_returns_nonzero_on_a_malformed_config(
    tmp_path, monkeypatch
):
    """A malformed config.json (or any of the field-editable YAML files)
    must produce a diagnosis a facilitator can read, not an unhandled
    exception in a console window that closes before anyone can see it."""
    monkeypatch.chdir(tmp_path)

    def broken_load(path):
        raise ValueError("boom: config.json is not valid JSON")

    monkeypatch.setattr(WorkshopConfig, "load", staticmethod(broken_load))

    exit_code = main([])

    assert exit_code == 1
    error_text = (tmp_path / "startup-error.txt").read_text(encoding="utf-8")
    assert "SawahPintar failed to start" in error_text
    assert "boom: config.json is not valid JSON" in error_text


def test_startup_error_guidance_matches_a_locked_database(tmp_path, monkeypatch):
    """A locked database means the application is already running, which is
    what happens when Start Workshop.bat is launched twice.

    The first real failure this reporter ever caught was exactly this, and it
    told the reader to go looking for a stray edit in YAML files that were
    perfectly fine. Wrong guidance is worse than none, because it sends a
    facilitator hunting in the wrong place while a group waits.
    """
    monkeypatch.chdir(tmp_path)

    def locked(path):
        raise ValueError(
            'IO Error: Cannot open file "workshop.duckdb": The process cannot '
            "access the file because it is being used by another process."
        )

    monkeypatch.setattr(WorkshopConfig, "load", staticmethod(locked))

    assert main([]) == 1

    error_text = (tmp_path / "startup-error.txt").read_text(encoding="utf-8")
    assert "ALREADY RUNNING" in error_text
    assert "no data has been lost" in error_text
    # The YAML advice must NOT appear: it is the wrong cause for this failure.
    assert "stray edit" not in error_text


def test_startup_error_guidance_still_points_at_yaml_for_a_parse_failure(
    tmp_path, monkeypatch
):
    """The locked-database branch must not swallow the common case."""
    monkeypatch.chdir(tmp_path)

    def broken(path):
        raise ValueError("while parsing a block mapping, expected <block end>")

    monkeypatch.setattr(WorkshopConfig, "load", staticmethod(broken))

    assert main([]) == 1

    error_text = (tmp_path / "startup-error.txt").read_text(encoding="utf-8")
    assert "stray edit" in error_text
    assert "ALREADY RUNNING" not in error_text


def test_main_startup_failure_does_not_raise(tmp_path, monkeypatch):
    """main() must return a failure code rather than let the exception
    propagate, so a caller (or a batch file wrapper) sees a clean exit
    rather than a bare traceback."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        WorkshopConfig,
        "load",
        staticmethod(lambda path: (_ for _ in ()).throw(OSError("missing file"))),
    )

    assert main([]) == 1


def test_parse_option_reads_a_flag_value_or_falls_back():
    from app.main import parse_option

    assert parse_option(["--database", "x.duckdb"], "--database", "d") == "x.duckdb"
    assert parse_option(["--port", "9"], "--database", "d") == "d"
    # A flag with no following value falls back rather than crashing.
    assert parse_option(["--database"], "--database", "d") == "d"


def test_simulate_flag_forces_every_sensor_to_simulation(tmp_path, monkeypatch):
    """--simulate must override a live binding left in config.json, in memory,
    without rewriting the file, so a kit bound to a dead COM port cannot start
    stuck on a broken feed."""
    import app.main as main_module
    from app.config import WorkshopConfig

    captured = {}

    def fake_load(path):
        return WorkshopConfig.from_dict(
            {"sensors": {"probe-a": {"mode": "live", "port": "COM7"}}}
        )

    def fake_build(con, config, config_path, **kwargs):
        captured["modes"] = {sid: b.mode for sid, b in config.sensors.items()}
        raise SystemExit(0)  # stop before uvicorn.run

    monkeypatch.setattr(WorkshopConfig, "load", staticmethod(fake_load))
    monkeypatch.setattr(main_module.WorkshopState, "build", staticmethod(fake_build))
    monkeypatch.setattr(main_module.db, "connect", lambda p: __import__("duckdb").connect(":memory:"))

    with pytest.raises(SystemExit):
        main_module.main(["--port", "8999", "--simulate"])

    assert captured["modes"] == {"probe-a": "simulate"}
