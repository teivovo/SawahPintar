"""Acquisition entry point.

Reads a probe on an interval and persists every reading. The clock and the
sleep function are injected so that tests run instantly and deterministically.
"""

import argparse
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone

from app.sensor.profile import SensorProfile
from app.sensor.reader import SensorReader
from app.sensor.simulator import SimulatedReader
from app.sensor.transport import SerialTransport, TransportError
from app.storage import db, seed

MAX_BACKOFF_SECONDS = 30.0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_reader(
    port: str, profile_path: str, sensor_id: str, simulate: bool = False
):
    if simulate:
        return SimulatedReader(sensor_id)
    profile = SensorProfile.load(profile_path)
    return SensorReader(sensor_id, profile, SerialTransport(port, profile))


def poll_forever(
    reader,
    con,
    interval: float,
    clock: Callable[[], datetime] = utc_now,
    stop_after: int | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    max_failures: int | None = None,
) -> None:
    """Poll until stop_after readings have been stored.

    A transport failure is not fatal. The dongle may be knocked loose in a
    field and must recover without the facilitator restarting anything, so
    failures back off exponentially up to a cap and reset on success.
    """
    stored = 0
    failures = 0

    while True:
        if stop_after is not None and stored >= stop_after:
            return
        if max_failures is not None and failures >= max_failures:
            return

        try:
            reading = reader.read_once(clock())
        except TransportError:
            failures += 1
            # The exponent itself must be clamped, not just the result: 2.0
            # raised to a large enough power overflows a Python float before
            # min() ever gets a chance to cap it. Five is the smallest
            # exponent whose result already exceeds MAX_BACKOFF_SECONDS, so
            # clamping there leaves the schedule for failures 1 to 12
            # unchanged: [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, ...].
            sleeper(min(2.0 ** min(failures - 1, 5), MAX_BACKOFF_SECONDS))
            continue

        failures = 0
        db.insert_reading(con, reading)
        stored += 1
        sleeper(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SawahPintar acquisition")
    parser.add_argument("--port", default="COM9")
    parser.add_argument("--profile", default="data/profiles/sn3002.json")
    parser.add_argument("--sensor-id", default="probe-a")
    parser.add_argument("--database", default="data/workshop.duckdb")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--readings", type=int, default=None)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument(
        "--seed-history",
        action="store_true",
        help="Insert deterministic demonstration history before polling",
    )
    args = parser.parse_args(argv)

    con = db.connect(args.database)
    db.initialise_schema(con)

    if args.seed_history:
        db.insert_readings(con, seed.generate_history(args.sensor_id, utc_now()))
        print(f"Seeded history for {args.sensor_id}")

    reader = build_reader(args.port, args.profile, args.sensor_id, args.simulate)

    try:
        poll_forever(reader, con, args.interval, utc_now, stop_after=args.readings)
    except KeyboardInterrupt:
        print("Stopped")

    print(f"Stored rows: {db.count_rows(con)}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
