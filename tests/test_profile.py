import json

import pytest

from app.sensor.profile import RegisterDef, SensorProfile, decode

MINIMAL = {
    "key": "test",
    "label": "Test probe",
    "address": 1,
    "baud": 4800,
    "read_plans": [{"function": 3, "start": 0, "count": 4}],
    "registers": [
        {"name": "moisture", "offset": 0, "scale": 10, "unit": "percent",
         "minimum": 0, "maximum": 100},
        {"name": "temperature", "offset": 1, "scale": 10, "signed": True,
         "unit": "celsius", "minimum": -40, "maximum": 80},
        {"name": "conductivity", "offset": 2, "scale": 1, "unit": "uS/cm"},
        {"name": "ph", "offset": 3, "scale": 10, "unit": "pH",
         "minimum": 3, "maximum": 9},
    ],
}


def test_from_dict_applies_serial_defaults():
    profile = SensorProfile.from_dict(MINIMAL)
    assert profile.bytesize == 8
    assert profile.parity == "N"
    assert profile.stopbits == 1
    assert profile.timeout == 1.0
    assert profile.read_plans[0].count == 4


def test_from_dict_rejects_duplicate_register_names():
    broken = json.loads(json.dumps(MINIMAL))
    broken["registers"][1]["name"] = "moisture"
    with pytest.raises(ValueError, match="duplicate register name"):
        SensorProfile.from_dict(broken)


def test_from_dict_rejects_missing_key():
    broken = json.loads(json.dumps(MINIMAL))
    del broken["address"]
    with pytest.raises(ValueError, match="address"):
        SensorProfile.from_dict(broken)


def test_decode_scales_values():
    profile = SensorProfile.from_dict(MINIMAL)
    values, out_of_range = decode(profile, {0: 658, 1: 312, 2: 1000, 3: 56})
    assert values == {
        "moisture": 65.8,
        "temperature": 31.2,
        "conductivity": 1000.0,
        "ph": 5.6,
    }
    assert out_of_range == []


def test_decode_handles_negative_temperature():
    profile = SensorProfile.from_dict(MINIMAL)
    values, _ = decode(profile, {0: 0, 1: 0xFF9B, 2: 0, 3: 0})
    assert values["temperature"] == pytest.approx(-10.1)


def test_decode_flags_values_outside_declared_range():
    profile = SensorProfile.from_dict(MINIMAL)
    values, out_of_range = decode(profile, {0: 2000, 1: 312, 2: 0, 3: 56})
    assert values["moisture"] == 200.0
    assert out_of_range == ["moisture"]


def test_decode_skips_registers_that_were_not_read():
    profile = SensorProfile.from_dict(MINIMAL)
    values, _ = decode(profile, {0: 658})
    assert values == {"moisture": 65.8}


def test_shipped_sn3002_profile_loads_and_decodes_captured_frame():
    profile = SensorProfile.load("data/profiles/sn3002.json")
    assert profile.address == 1
    assert profile.baud == 4800
    assert profile.read_plans[0].count == 9
    # Registers from the frame captured on COM9 on 22 July 2026.
    raw = dict(enumerate([0, 312, 0, 47, 0, 0, 0, 0, 0]))
    values, out_of_range = decode(profile, raw)
    assert values["temperature"] == pytest.approx(31.2)
    assert values["ph"] == pytest.approx(4.7)
    assert values["moisture"] == 0.0
    assert out_of_range == []


def test_register_def_defaults():
    register = RegisterDef(name="x", offset=0, scale=1)
    assert register.signed is False
    assert register.unit == ""
    assert register.minimum is None


def test_register_def_rejects_a_zero_scale():
    with pytest.raises(ValueError, match="moisture"):
        RegisterDef(name="moisture", offset=0, scale=0)


def test_profile_from_dict_rejects_a_zero_scale_register():
    broken = json.loads(json.dumps(MINIMAL))
    broken["registers"][0]["scale"] = 0
    with pytest.raises(ValueError, match="scale: 0"):
        SensorProfile.from_dict(broken)
