import pytest

from app.insights.calibration import (
    Calibration,
    classify_salinity,
    load_calibration,
    water_table_depth_cm,
)

MINIMAL = {
    "provisional": True,
    "salinity_breakpoints": [
        {"max_conductivity_us_cm": 1000, "salinity_class": "non_saline"},
        {"max_conductivity_us_cm": 2000, "salinity_class": "slightly_saline"},
    ],
    "water_table_curve": [
        {"moisture_percent": 20, "water_table_depth_cm": 20},
        {"moisture_percent": 40, "water_table_depth_cm": 0},
    ],
}


def test_from_dict_reads_the_provisional_flag():
    calibration = Calibration.from_dict(MINIMAL)
    assert calibration.provisional is True


def test_from_dict_rejects_missing_field():
    broken = {"provisional": True, "salinity_breakpoints": []}
    with pytest.raises(ValueError, match="water_table_curve"):
        Calibration.from_dict(broken)


def test_from_dict_rejects_unsorted_salinity_breakpoints():
    broken = dict(MINIMAL)
    broken["salinity_breakpoints"] = list(reversed(MINIMAL["salinity_breakpoints"]))
    with pytest.raises(ValueError, match="sorted ascending"):
        Calibration.from_dict(broken)


def test_from_dict_rejects_unsorted_water_table_curve():
    broken = dict(MINIMAL)
    broken["water_table_curve"] = list(reversed(MINIMAL["water_table_curve"]))
    with pytest.raises(ValueError, match="sorted ascending"):
        Calibration.from_dict(broken)


def test_from_dict_rejects_a_curve_with_one_point():
    broken = dict(MINIMAL)
    broken["water_table_curve"] = [MINIMAL["water_table_curve"][0]]
    with pytest.raises(ValueError, match="at least two points"):
        Calibration.from_dict(broken)


def test_classify_salinity_picks_the_matching_breakpoint():
    calibration = Calibration.from_dict(MINIMAL)
    assert classify_salinity(calibration, 500) == "non_saline"
    assert classify_salinity(calibration, 1000) == "non_saline"
    assert classify_salinity(calibration, 1500) == "slightly_saline"


def test_classify_salinity_falls_back_to_the_last_breakpoint_above_range():
    calibration = Calibration.from_dict(MINIMAL)
    assert classify_salinity(calibration, 999999) == "slightly_saline"


def test_water_table_depth_interpolates_between_points():
    calibration = Calibration.from_dict(MINIMAL)
    assert water_table_depth_cm(calibration, 20) == pytest.approx(20.0)
    assert water_table_depth_cm(calibration, 40) == pytest.approx(0.0)
    assert water_table_depth_cm(calibration, 30) == pytest.approx(10.0)


def test_water_table_depth_clamps_outside_the_curve():
    calibration = Calibration.from_dict(MINIMAL)
    assert water_table_depth_cm(calibration, 5) == pytest.approx(20.0)
    assert water_table_depth_cm(calibration, 90) == pytest.approx(0.0)


def test_shipped_default_calibration_loads_and_is_provisional():
    calibration = load_calibration("data/calibration/default.yaml")
    assert calibration.provisional is True
    # The AWD re-flood trigger of 15 cm below the surface, design spec
    # section 4.1, is reachable through the shipped default at 25 per cent
    # moisture.
    assert water_table_depth_cm(calibration, 25) == pytest.approx(15.0)
    assert classify_salinity(calibration, 500) == "non_saline"
    assert classify_salinity(calibration, 5000) == "severely_saline"
