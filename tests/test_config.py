import pytest

from app.config import (
    GROWTH_STAGES,
    FieldCard,
    PutsResult,
    SensorBinding,
    WorkshopConfig,
)


def test_default_config_has_one_simulated_sensor():
    config = WorkshopConfig()
    assert config.language == "id"
    assert config.growth_stage == GROWTH_STAGES[0]
    assert config.sensors["probe-a"].mode == "simulate"


def test_from_dict_fills_in_missing_fields():
    config = WorkshopConfig.from_dict({"site_name": "Desa Bontomanai"})
    assert config.site_name == "Desa Bontomanai"
    assert config.language == "id"
    assert "probe-a" in config.sensors


def test_from_dict_rejects_unknown_language():
    with pytest.raises(ValueError, match="language"):
        WorkshopConfig.from_dict({"language": "fr"})


def test_from_dict_rejects_unknown_growth_stage():
    with pytest.raises(ValueError, match="growth_stage"):
        WorkshopConfig.from_dict({"growth_stage": "harvest"})


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "config.json"
    original = WorkshopConfig.from_dict(
        {
            "language": "en",
            "site_name": "Bench site",
            "growth_stage": "flowering",
            "sensors": {
                "probe-a": {
                    "port": "COM9",
                    "profile": "data/profiles/sn3002.json",
                    "mode": "live",
                },
                "probe-b": {
                    "port": "COM10",
                    "profile": "data/profiles/sn3002.json",
                    "mode": "simulate",
                },
            },
        }
    )
    original.save(path)

    loaded = WorkshopConfig.load(path)

    assert loaded.language == "en"
    assert loaded.site_name == "Bench site"
    assert loaded.sensors["probe-a"].mode == "live"
    assert loaded.sensors["probe-b"].port == "COM10"


def test_shipped_config_template_loads():
    config = WorkshopConfig.load("config.json")
    assert config.growth_stage in GROWTH_STAGES
    assert "probe-a" in config.sensors


def test_field_card_defaults_are_blank():
    card = FieldCard()
    assert card.field_size_ha is None
    assert card.variety == ""


def test_puts_result_requires_three_classes():
    result = PutsResult(
        nitrogen_class="rendah", phosphorus_class="sedang", potassium_class="tinggi"
    )
    assert result.ph is None


def test_sensor_binding_defaults_to_simulate():
    binding = SensorBinding()
    assert binding.mode == "simulate"
    assert binding.port == "COM9"
