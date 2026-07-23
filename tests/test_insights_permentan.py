import pytest

from app.insights.permentan import (
    PermentanTable,
    classify_phosphorus,
    classify_potassium,
    dose_for_status,
    load_permentan,
)

MINIMAL = {
    "phosphorus": {
        "low_max_exclusive": 20,
        "medium_max_inclusive": 40,
        "doses": {
            "rendah": {"p2o5_kg_per_ha": 36, "sp36_kg_per_ha": 100},
            "sedang": {"p2o5_kg_per_ha": 27, "sp36_kg_per_ha": 75},
            "tinggi": {"p2o5_kg_per_ha": 18, "sp36_kg_per_ha": 50},
        },
    },
    "potassium": {"low_max_exclusive": 10, "medium_max_inclusive": 20},
}


def test_from_dict_rejects_a_missing_dose_status():
    broken = {
        "phosphorus": {
            "low_max_exclusive": 20,
            "medium_max_inclusive": 40,
            "doses": {
                "rendah": {"p2o5_kg_per_ha": 36, "sp36_kg_per_ha": 100},
                "sedang": {"p2o5_kg_per_ha": 27, "sp36_kg_per_ha": 75},
            },
        },
        "potassium": {"low_max_exclusive": 10, "medium_max_inclusive": 20},
    }
    with pytest.raises(ValueError, match="tinggi"):
        PermentanTable.from_dict(broken)


def test_classify_phosphorus_boundaries_match_permentan_13_2022():
    table = PermentanTable.from_dict(MINIMAL)
    assert classify_phosphorus(table, 19.9) == "rendah"
    assert classify_phosphorus(table, 20) == "sedang"
    assert classify_phosphorus(table, 40) == "sedang"
    assert classify_phosphorus(table, 40.1) == "tinggi"


def test_classify_potassium_boundaries_match_permentan_13_2022():
    table = PermentanTable.from_dict(MINIMAL)
    assert classify_potassium(table, 9.9) == "rendah"
    assert classify_potassium(table, 10) == "sedang"
    assert classify_potassium(table, 20) == "sedang"
    assert classify_potassium(table, 20.1) == "tinggi"


def test_dose_for_status_matches_the_official_permentan_figures():
    table = PermentanTable.from_dict(MINIMAL)
    assert dose_for_status(table, "rendah").p2o5_kg_per_ha == 36
    assert dose_for_status(table, "rendah").sp36_kg_per_ha == 100
    assert dose_for_status(table, "sedang").p2o5_kg_per_ha == 27
    assert dose_for_status(table, "sedang").sp36_kg_per_ha == 75
    assert dose_for_status(table, "tinggi").p2o5_kg_per_ha == 18
    assert dose_for_status(table, "tinggi").sp36_kg_per_ha == 50


def test_dose_for_status_normalises_case_and_whitespace():
    table = PermentanTable.from_dict(MINIMAL)
    assert dose_for_status(table, " Rendah ").p2o5_kg_per_ha == 36


def test_dose_for_unknown_status_raises_a_clear_error():
    table = PermentanTable.from_dict(MINIMAL)
    with pytest.raises(KeyError, match="no Permentan dose for status: banyak"):
        dose_for_status(table, "banyak")


def test_classify_then_dose_round_trip_for_a_low_status_field():
    table = PermentanTable.from_dict(MINIMAL)
    status = classify_phosphorus(table, 15.0)
    dose = dose_for_status(table, status)
    assert status == "rendah"
    assert dose.p2o5_kg_per_ha == 36
    assert dose.sp36_kg_per_ha == 100


def test_shipped_permentan_table_loads_and_matches_the_design_spec():
    table = load_permentan("data/permentan_2022.yaml")
    assert dose_for_status(table, "rendah").sp36_kg_per_ha == 100
    assert dose_for_status(table, "sedang").sp36_kg_per_ha == 75
    assert dose_for_status(table, "tinggi").sp36_kg_per_ha == 50
    assert classify_phosphorus(table, 25.0) == "sedang"
    assert classify_potassium(table, 5.0) == "rendah"
