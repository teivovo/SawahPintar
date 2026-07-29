from datetime import datetime, timedelta, timezone

from app.sensor.simulator import SimulatedReader
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc)


def test_readings_are_flagged_as_simulated():
    reader = SimulatedReader("sim-a")
    reading = reader.read_once(NOW)
    assert reading.source == Reading.SOURCE_SIM
    assert reading.sensor_id == "sim-a"


def test_in_air_readings_show_no_moisture_or_conductivity():
    reader = SimulatedReader("sim-a")
    reading = reader.read_once(NOW)
    assert reading.values["moisture"] == 0.0
    assert reading.values["conductivity"] == 0.0


def test_inserting_the_probe_raises_moisture_and_conductivity():
    reader = SimulatedReader("sim-a")
    reader.insert_probe()
    reading = reader.read_once(NOW)
    assert reading.values["moisture"] > 20.0
    assert reading.values["conductivity"] > 100.0


def test_withdrawing_the_probe_returns_to_air():
    reader = SimulatedReader("sim-a")
    reader.insert_probe()
    reader.withdraw_probe()
    reading = reader.read_once(NOW)
    assert reading.values["moisture"] == 0.0


def test_successive_readings_vary_but_stay_plausible():
    reader = SimulatedReader("sim-a")
    reader.insert_probe()
    values = [
        reader.read_once(NOW + timedelta(seconds=2 * i)).values["moisture"]
        for i in range(20)
    ]
    assert len(set(values)) > 1
    assert all(0.0 <= value <= 100.0 for value in values)


def test_simulator_is_deterministic_for_a_given_seed():
    first = SimulatedReader("sim-a", rng_seed=7)
    second = SimulatedReader("sim-a", rng_seed=7)
    first.insert_probe()
    second.insert_probe()
    assert first.read_once(NOW).values == second.read_once(NOW).values


def test_soil_scenarios_differ_between_plots():
    # Each plot gets its own soil condition, so the map is not one flat colour.
    first = SimulatedReader("S1")
    first.insert_probe()
    second = SimulatedReader("S2")
    second.insert_probe()
    a = first.read_once(NOW).values
    b = second.read_once(NOW).values
    assert (a["ph"], a["conductivity"]) != (b["ph"], b["conductivity"])


def test_soil_scenarios_span_saline_and_non_saline():
    conductivities = []
    for index in range(1, 7):
        reader = SimulatedReader(f"S{index}")
        reader.insert_probe()
        conductivities.append(reader.read_once(NOW).values["conductivity"])
    # At least one plot severely saline (red) and one non-saline (green).
    assert max(conductivities) > 4000
    assert min(conductivities) < 1000


def test_in_air_moisture_and_conductivity_are_read_from_the_air_dict(monkeypatch):
    """The in-air branch must read AIR (via base), not hardcode 0.0, so a
    faculty edit to AIR's moisture or conductivity entries actually takes
    effect instead of silently doing nothing."""
    import app.sensor.simulator as simulator

    monkeypatch.setitem(simulator.AIR, "moisture", 3.3)
    monkeypatch.setitem(simulator.AIR, "conductivity", 12.0)

    reader = simulator.SimulatedReader("sim-a")
    reading = reader.read_once(NOW)

    assert reading.values["moisture"] == 3.3
    assert reading.values["conductivity"] == 12.0
