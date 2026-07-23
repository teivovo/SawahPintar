from datetime import datetime, timezone

import pytest

from app.insights.calibration import Calibration
from app.insights.rules import Condition, Rule, RuleSet, load_rules, rule_matches
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

MINIMAL = {
    "rules": [
        {
            "id": "acidity_low_ph",
            "group": "acidity",
            "severity": "attention",
            "content_key": "acidity_low_ph",
            "condition": {"source": "metric", "name": "ph", "op": "lt", "value": 5.5},
        }
    ]
}


def reading(**values) -> Reading:
    return Reading(timestamp=NOW, sensor_id="probe-a", values=values)


def test_from_dict_builds_a_rule_with_a_metric_condition():
    rule_set = RuleSet.from_dict(MINIMAL)
    assert len(rule_set.rules) == 1
    rule = rule_set.rules[0]
    assert rule.id == "acidity_low_ph"
    assert rule.group == "acidity"
    assert rule.severity == "attention"
    assert rule.condition == Condition(source="metric", name="ph", op="lt", value=5.5)
    assert rule.override is False


def test_from_dict_rejects_unknown_group():
    broken = {"rules": [{**MINIMAL["rules"][0], "group": "moon_phase"}]}
    with pytest.raises(ValueError, match="unknown group"):
        RuleSet.from_dict(broken)


def test_from_dict_rejects_unknown_severity():
    broken = {"rules": [{**MINIMAL["rules"][0], "severity": "catastrophic"}]}
    with pytest.raises(ValueError, match="unknown severity"):
        RuleSet.from_dict(broken)


def test_from_dict_rejects_duplicate_ids():
    broken = {"rules": [MINIMAL["rules"][0], MINIMAL["rules"][0]]}
    with pytest.raises(ValueError, match="duplicate rule id"):
        RuleSet.from_dict(broken)


def test_from_dict_rejects_a_rule_with_neither_condition_nor_stages():
    broken = {
        "rules": [
            {
                "id": "empty_rule",
                "group": "acidity",
                "severity": "good",
                "content_key": "x",
            }
        ]
    }
    with pytest.raises(ValueError, match="must specify a condition"):
        RuleSet.from_dict(broken)


def test_from_dict_rejects_an_unknown_growth_stage():
    broken = {
        "rules": [
            {
                "id": "bad_stage",
                "group": "water",
                "severity": "good",
                "content_key": "x",
                "stages": ["dormant"],
            }
        ]
    }
    with pytest.raises(ValueError, match="unknown growth stage"):
        RuleSet.from_dict(broken)


def test_from_dict_accepts_a_rule_with_only_stages():
    data = {
        "rules": [
            {
                "id": "flowering_note",
                "group": "water",
                "severity": "good",
                "content_key": "flowering_note",
                "stages": ["flowering"],
                "override": True,
            }
        ]
    }
    rule_set = RuleSet.from_dict(data)
    assert rule_set.rules[0].override is True
    assert rule_set.rules[0].condition is None


def test_condition_rejects_an_unknown_op():
    with pytest.raises(ValueError, match="op must be one of"):
        Condition(source="metric", name="ph", op="near", value=5.5)


def test_condition_rejects_an_unknown_derived_name():
    with pytest.raises(ValueError, match="unknown derived quantity"):
        Condition(source="derived", name="moon_phase", op="eq", value="full")


def test_rule_matches_a_true_metric_condition():
    rule = RuleSet.from_dict(MINIMAL).rules[0]
    assert rule_matches(rule, reading(ph=5.0), "tillering", CALIBRATION) is True


def test_rule_does_not_match_a_false_metric_condition():
    rule = RuleSet.from_dict(MINIMAL).rules[0]
    assert rule_matches(rule, reading(ph=6.5), "tillering", CALIBRATION) is False


def test_rule_does_not_match_when_the_metric_is_missing():
    rule = RuleSet.from_dict(MINIMAL).rules[0]
    assert rule_matches(rule, reading(moisture=30.0), "tillering", CALIBRATION) is False


def test_rule_matches_a_derived_condition():
    rule = Rule(
        id="salinity_none",
        group="salinity",
        severity="good",
        content_key="salinity_none",
        condition=Condition(source="derived", name="salinity_class", op="eq", value="non_saline"),
    )
    assert rule_matches(rule, reading(conductivity=500.0), "tillering", CALIBRATION) is True
    assert rule_matches(rule, reading(conductivity=5000.0), "tillering", CALIBRATION) is False


def test_rule_with_stages_only_matches_the_listed_stages():
    rule = Rule(
        id="flowering_note",
        group="water",
        severity="good",
        content_key="flowering_note",
        stages=("panicle_initiation", "flowering"),
    )
    assert rule_matches(rule, reading(), "flowering", CALIBRATION) is True
    assert rule_matches(rule, reading(), "tillering", CALIBRATION) is False


def test_rule_requires_both_condition_and_stages_to_match_when_both_are_set():
    rule = Rule(
        id="salinity_mild_reproductive",
        group="salinity",
        severity="act_now",
        content_key="salinity_reproductive",
        condition=Condition(source="derived", name="salinity_class", op="eq", value="non_saline"),
        stages=("flowering",),
    )
    assert rule_matches(rule, reading(conductivity=500.0), "flowering", CALIBRATION) is True
    assert rule_matches(rule, reading(conductivity=500.0), "tillering", CALIBRATION) is False
    assert rule_matches(rule, reading(conductivity=5000.0), "flowering", CALIBRATION) is False


def test_shipped_loader_reads_a_yaml_file(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        "rules:\n"
        "  - id: acidity_low_ph\n"
        "    group: acidity\n"
        "    severity: attention\n"
        "    content_key: acidity_low_ph\n"
        "    condition: {source: metric, name: ph, op: lt, value: 5.5}\n",
        encoding="utf-8",
    )
    rule_set = load_rules(rules_path)
    assert rule_set.rules[0].id == "acidity_low_ph"
