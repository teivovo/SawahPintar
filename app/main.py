"""Composition root: loads configuration, wires in the insight engine, and
starts the server.

This is the one file most likely to need a small edit once Plan 2 lands,
if its module or function names differ from the Assumed interfaces
section of the interface and packaging plan. Every other module in that
plan depends only on the evaluate() signature and the AdviceCard shape,
never on these import paths directly.

Plan 2 has now landed: app.insights.engine.evaluate,
app.insights.rules.load_rules, app.insights.content.load_content and
app.insights.calibration.load_calibration all exist. The guarded import
below is kept anyway, cheap insurance against a future reorganisation of
that package, but its data file paths below are the real shipped paths
(data/calibration/default.yaml, data/rules/default.yaml,
data/content/advice.yaml), not the placeholder paths this plan's brief
assumed before the engine existed.

DuckDB does not support two writers on one database file. This process is
the only one that may hold an open connection to data/workshop.duckdb
while a workshop is running; app.acquire from Plan 1 is a standalone
command line tool for development and hardware verification and must
never run at the same time as this one against the same file.
"""

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from app.config import WorkshopConfig
from app.insights.permentan import load_permentan
from app.server import create_app
from app.state import WorkshopState, default_evaluate
from app.storage import db, seed

CONFIG_PATH = "config.json"
DATABASE_PATH = "data/workshop.duckdb"
HOST = "127.0.0.1"
DEFAULT_PORT = 8420

CALIBRATION_PATH = "data/calibration/default.yaml"
RULES_PATH = "data/rules/default.yaml"
CONTENT_PATH = "data/content/advice.yaml"
PERMENTAN_PATH = "data/permentan_2022.yaml"

# Written beside Start Workshop.bat (the batch file cd's to the program
# folder before launching python, so a relative path here lands in the
# right place) whenever startup fails. The design deliberately invites
# faculty to hand-edit the YAML files under data/, and start /min in the
# batch file gives a crashed process's own console window no time to be
# read before it closes, so a traceback that only reached stderr would be
# lost. This file is the diagnosis that survives that window closing.
STARTUP_ERROR_PATH = "startup-error.txt"


def load_insight_engine():
    """Wire in the real Plan 2 insight engine.

    Falls back to app.state.default_evaluate, which returns no advice
    cards, if Plan 2 has not been merged yet, so the server still starts
    for interface development and manual testing.
    """
    try:
        from app.insights.calibration import load_calibration
        from app.insights.content import load_content
        from app.insights.engine import evaluate
        from app.insights.rules import load_rules
    except ImportError:
        return default_evaluate, None, None, None

    calibration = load_calibration(CALIBRATION_PATH)
    rules = load_rules(RULES_PATH)
    content = load_content(CONTENT_PATH)
    return evaluate, calibration, rules, content


def ensure_seed_history(con, config: WorkshopConfig) -> None:
    """Seed demonstration history for every configured sensor on first run,
    so every chart is alive the moment the application opens."""
    if db.count_rows(con) > 0:
        return
    now = datetime.now(timezone.utc)
    for sensor_id in config.sensors:
        db.insert_readings(con, seed.generate_history(sensor_id, now))


def parse_port(argv: list[str]) -> int:
    if "--port" in argv:
        return int(argv[argv.index("--port") + 1])
    return DEFAULT_PORT


def report_startup_failure(error: BaseException) -> None:
    """Write a plain-text startup failure report where a facilitator will
    find it, and print the same text to stderr.

    A malformed edit to one of the field-editable YAML files, or a missing
    file after an incomplete USB copy, raises before uvicorn.run ever gets
    called. Start Workshop.bat launches python in a minimized window that
    closes the instant the process dies, so without this file the only
    diagnosis anyone ever had was a window that flashed and vanished.

    The guidance is matched to the failure. An earlier version offered the
    same advice for every cause, and the first real failure it caught was a
    locked database file, for which it told the reader to go hunting for a
    stray edit in YAML that was perfectly fine. Wrong guidance is worse than
    none, because it sends a facilitator looking in the wrong place while a
    group waits.
    """
    detail = str(error)
    already_running = (
        "being used by another process" in detail
        or "already open in" in detail
        or isinstance(error, PermissionError)
    )

    if already_running:
        guidance = (
            "SawahPintar is most likely ALREADY RUNNING on this laptop.\n\n"
            "The workshop database can only be opened by one copy of the "
            "application at a time, and something else is holding it. This "
            "usually means Start Workshop.bat was run twice.\n\n"
            "What to do:\n"
            "1. Look for a SawahPintar window that is already open, including "
            "a minimised one on the taskbar. If you find it, use that and "
            "close this message.\n"
            "2. If you cannot find one, close every SawahPintar and Edge "
            "window, wait ten seconds, then run Start Workshop.bat once.\n"
            "3. If it still will not start, restart the laptop. That always "
            "releases the file.\n\n"
            "Nothing is broken and no data has been lost.\n"
        )
    else:
        guidance = (
            "Check config.json and the YAML files under data/calibration, "
            "data/rules, data/content and data/permentan_2022.yaml for a "
            "stray edit (indentation, a missing colon, a deleted line), then "
            "run Start Workshop.bat again. If nothing there looks wrong, "
            "re-copy the SawahPintar folder from a known-good source.\n"
        )

    message = (
        "SawahPintar failed to start.\n\n"
        f"{type(error).__name__}: {error}\n\n"
        f"{traceback.format_exc()}\n"
        f"{guidance}"
    )
    print(message, file=sys.stderr)
    Path(STARTUP_ERROR_PATH).write_text(message, encoding="utf-8")


def parse_option(argv: list[str], flag: str, default: str) -> str:
    """Return the value following flag in argv, or default if absent."""
    if flag in argv:
        index = argv.index(flag)
        if index + 1 < len(argv):
            return argv[index + 1]
    return default


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    database_path = parse_option(argv, "--database", DATABASE_PATH)
    force_simulate = "--simulate" in argv

    try:
        config = WorkshopConfig.load(CONFIG_PATH)
        if force_simulate:
            # Force every sensor to simulation for this run, in memory only,
            # without rewriting config.json. This is the workshop's safe
            # default: the demonstration is a simulation with seeded history
            # and the SIMULASI watermark, and the operator switches a slot to
            # live during the session when a real probe is connected. Starting
            # this way means a live binding left in config.json from a previous
            # session, for example a slot bound to a Bluetooth COM port with no
            # probe, can never leave the kit stuck on a dead feed at launch.
            for binding in config.sensors.values():
                binding.mode = "simulate"
        con = db.connect(database_path)
        db.initialise_schema(con)
        ensure_seed_history(con, config)

        evaluate_fn, calibration, rules, content = load_insight_engine()
        permentan = load_permentan(PERMENTAN_PATH)
    except Exception as error:  # noqa: BLE001 - deliberately broad: any
        # failure this early must produce a diagnosis, not a vanished window.
        report_startup_failure(error)
        return 1

    state = WorkshopState.build(
        con,
        config,
        CONFIG_PATH,
        evaluate_fn=evaluate_fn,
        calibration=calibration,
        rules=rules,
        content=content,
        permentan=permentan,
    )

    # In a field-map demo (plots have been drawn) every simulated plot is a
    # probe already in the ground, so the map shows live soil values and the
    # NPK estimate the moment it opens. The single-probe demo, with no zones,
    # keeps its probe in air for the hands-on insertion moment.
    if any(binding.zone for binding in config.sensors.values()):
        for reader in state.readers.values():
            if hasattr(reader, "insert_probe"):
                reader.insert_probe()

    app = create_app(state)

    uvicorn.run(app, host=HOST, port=parse_port(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
