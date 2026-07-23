import pytest

from app.insights.models import (
    RULE_GROUP_PRIORITY,
    RULE_GROUPS,
    SEVERITY_BY_YAML_WORD,
    SEVERITY_RANK,
    AdviceCard,
    GrowthStage,
    Severity,
)


def test_severity_values_match_the_interface_layer_colour_names():
    assert Severity.GOOD.value == "green"
    assert Severity.ATTENTION.value == "amber"
    assert Severity.ACT_NOW.value == "red"


def test_severity_by_yaml_word_covers_every_level():
    assert SEVERITY_BY_YAML_WORD == {
        "good": Severity.GOOD,
        "attention": Severity.ATTENTION,
        "act_now": Severity.ACT_NOW,
    }


def test_severity_rank_orders_act_now_highest():
    assert SEVERITY_RANK[Severity.ACT_NOW] > SEVERITY_RANK[Severity.ATTENTION]
    assert SEVERITY_RANK[Severity.ATTENTION] > SEVERITY_RANK[Severity.GOOD]


def test_growth_stage_values_match_the_standard_sequence():
    assert [stage.value for stage in GrowthStage] == [
        "land_preparation",
        "transplanting",
        "tillering",
        "panicle_initiation",
        "flowering",
        "ripening",
    ]


def test_rule_groups_and_priority_match_the_interface_layer():
    assert RULE_GROUPS == ("salinity", "water", "acidity", "nutrients")
    assert RULE_GROUP_PRIORITY == {
        "salinity": 4,
        "water": 3,
        "acidity": 2,
        "nutrients": 1,
    }


def test_advice_card_holds_the_six_fields_in_order():
    card = AdviceCard(
        icon="water",
        severity="amber",
        headline="Contoh saran",
        body="Contoh isi",
        subtitle_en="Example advice",
        rule_group="water",
    )
    assert card.icon == "water"
    assert card.severity == "amber"
    assert card.headline == "Contoh saran"
    assert card.body == "Contoh isi"
    assert card.subtitle_en == "Example advice"
    assert card.rule_group == "water"


def test_advice_card_is_immutable():
    card = AdviceCard(
        icon="water",
        severity="amber",
        headline="a",
        body="b",
        subtitle_en="c",
        rule_group="water",
    )
    with pytest.raises(AttributeError):
        card.severity = "red"
