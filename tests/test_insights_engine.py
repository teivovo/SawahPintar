from datetime import datetime, timezone

import pytest

from app.insights.calibration import Calibration
from app.insights.content import ContentPack
from app.insights.engine import evaluate
from app.insights.rules import Condition, Rule, RuleSet
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)

CALIBRATION = Calibration.from_dict(
    {
        "provisional": True,
        "salinity_breakpoints": [
            {"max_conductivity_us_cm": 1000, "salinity_class": "non_saline"},
            {"max_conductivity_us_cm": 999999, "salinity_class": "severely_saline"},
        ],
        "water_table_curve": [
            {"moisture_percent": 20, "water_table_depth_cm": 20},
            {"moisture_percent": 40, "water_table_depth_cm": 0},
        ],
    }
)

CONTENT = ContentPack.from_dict(
    {
        "acidity_low_ph": {
            "icon": "acidity",
            "headline_id": "Tanah asam",
            "body_id": "Tambahkan kapur",
            "subtitle_en": "Acidic soil, add lime",
            "draft": True,
        },
        "acidity_ok": {
            "icon": "acidity",
            "headline_id": "pH tanah baik",
            "body_id": "Tidak perlu tindakan",
            "subtitle_en": "Soil pH is adequate",
            "draft": True,
        },
        "water_reflood_now": {
            "icon": "water",
            "headline_id": "Saatnya mengairi kembali",
            "body_id": "Muka air turun 15 cm",
            "subtitle_en": "Time to re-flood, water table has dropped",
            "draft": True,
        },
        "water_flowering_note": {
            "icon": "water",
            "headline_id": "Jaga sawah tetap tergenang",
            "body_id": "Fase bunga, jangan dikeringkan",
            "subtitle_en": "Flowering stage, keep the field flooded",
            "draft": True,
        },
    }
)


def reading(**values) -> Reading:
    return Reading(timestamp=NOW, sensor_id="probe-a", values=values)


def build_rules(*rules: Rule) -> RuleSet:
    return RuleSet(rules=tuple(rules))


ACIDITY_LOW = Rule(
    id="acidity_low_ph",
    group="acidity",
    severity="attention",
    content_key="acidity_low_ph",
    condition=Condition(source="metric", name="ph", op="lt", value=5.5),
)
ACIDITY_OK = Rule(
    id="acidity_ok",
    group="acidity",
    severity="good",
    content_key="acidity_ok",
    condition=Condition(source="metric", name="ph", op="ge", value=5.5),
)
WATER_REFLOOD = Rule(
    id="water_reflood_now",
    group="water",
    severity="act_now",
    content_key="water_reflood_now",
    condition=Condition(source="derived", name="water_table_depth_cm", op="ge", value=15),
)
WATER_FLOWERING_OVERRIDE = Rule(
    id="water_flowering_note",
    group="water",
    severity="good",
    content_key="water_flowering_note",
    stages=("panicle_initiation", "flowering"),
    override=True,
)


def test_evaluate_returns_a_card_for_a_matching_rule():
    rules = build_rules(ACIDITY_LOW, ACIDITY_OK)
    cards = evaluate(reading(ph=5.0), "tillering", CALIBRATION, rules, CONTENT)
    assert len(cards) == 1
    assert cards[0].headline == "Tanah asam"
    assert cards[0].severity == "amber"
    assert cards[0].rule_group == "acidity"
    assert cards[0].subtitle_en == "Acidic soil, add lime"


def test_evaluate_picks_the_matching_branch_not_the_other_one():
    rules = build_rules(ACIDITY_LOW, ACIDITY_OK)
    cards = evaluate(reading(ph=6.5), "tillering", CALIBRATION, rules, CONTENT)
    assert len(cards) == 1
    assert cards[0].headline == "pH tanah baik"
    assert cards[0].severity == "green"


def test_evaluate_returns_nothing_when_no_rule_matches():
    rules = build_rules(WATER_REFLOOD)
    cards = evaluate(reading(moisture=35.0), "tillering", CALIBRATION, rules, CONTENT)
    assert cards == []


def test_override_wins_regardless_of_the_severity_of_the_other_match():
    # water_reflood_now would match too (deep water table) and is act_now,
    # more severe than the override's good, but the override is absolute.
    rules = build_rules(WATER_REFLOOD, WATER_FLOWERING_OVERRIDE)
    cards = evaluate(reading(moisture=15.0), "flowering", CALIBRATION, rules, CONTENT)
    assert len(cards) == 1
    assert cards[0].headline == "Jaga sawah tetap tergenang"
    assert cards[0].severity == "green"


def test_override_does_not_apply_outside_its_stages():
    rules = build_rules(WATER_REFLOOD, WATER_FLOWERING_OVERRIDE)
    cards = evaluate(reading(moisture=15.0), "tillering", CALIBRATION, rules, CONTENT)
    assert len(cards) == 1
    assert cards[0].headline == "Saatnya mengairi kembali"
    assert cards[0].severity == "red"


def test_cards_are_ranked_by_severity_then_group_priority():
    rules = build_rules(ACIDITY_LOW, WATER_REFLOOD)
    cards = evaluate(reading(ph=5.0, moisture=15.0), "tillering", CALIBRATION, rules, CONTENT)
    assert [card.rule_group for card in cards] == ["water", "acidity"]
    assert [card.severity for card in cards] == ["red", "amber"]


def test_equal_severity_ranks_by_group_priority():
    salinity_good = Rule(
        id="salinity_none",
        group="salinity",
        severity="good",
        content_key="acidity_ok",
        condition=Condition(source="derived", name="salinity_class", op="eq", value="non_saline"),
    )
    rules = build_rules(ACIDITY_OK, salinity_good)
    cards = evaluate(reading(ph=6.5, conductivity=500.0), "tillering", CALIBRATION, rules, CONTENT)
    assert [card.rule_group for card in cards] == ["salinity", "acidity"]


def test_evaluate_slices_to_the_top_four_cards():
    groups = ["salinity", "water", "acidity", "nutrients", "temperature"]
    rules = build_rules(
        *[
            Rule(
                id=f"rule_{group}",
                group=group,
                severity="attention",
                content_key="acidity_low_ph",
                condition=Condition(source="metric", name="ph", op="lt", value=100),
            )
            for group in groups
        ]
    )
    cards = evaluate(reading(ph=5.0), "tillering", CALIBRATION, rules, CONTENT)
    assert len(cards) == 4
    assert "temperature" not in [card.rule_group for card in cards]
