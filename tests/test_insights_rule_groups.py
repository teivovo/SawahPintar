from datetime import datetime, timezone

import pytest

from app.insights.calibration import load_calibration
from app.insights.content import load_content
from app.insights.engine import evaluate
from app.insights.rules import load_rules
from app.storage.models import Reading

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc)

CALIBRATION = load_calibration("data/calibration/default.yaml")
RULES = load_rules("data/rules/default.yaml")
CONTENT = load_content("data/content/advice.yaml")


def reading(**values) -> Reading:
    return Reading(timestamp=NOW, sensor_id="probe-a", values=values)


def card_for_group(cards, group):
    matches = [card for card in cards if card.rule_group == group]
    assert matches, f"no card for group {group} among {[c.rule_group for c in cards]}"
    return matches[0]


def test_mild_salinity_outside_the_reproductive_window_is_attention():
    reading_ = reading(conductivity=1500.0, moisture=35.0, ph=6.5)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    salinity = card_for_group(cards, "salinity")
    assert salinity.severity == "amber"
    assert salinity.headline == "Salinitas mulai meningkat"


def test_the_same_mild_salinity_escalates_to_act_now_at_flowering():
    reading_ = reading(conductivity=1500.0, moisture=45.0, ph=6.5)
    cards = evaluate(reading_, "flowering", CALIBRATION, RULES, CONTENT)
    salinity = card_for_group(cards, "salinity")
    assert salinity.severity == "red"
    assert salinity.headline == "Salinitas berisiko tinggi pada fase ini"


def test_the_same_mild_salinity_also_escalates_at_panicle_initiation():
    reading_ = reading(conductivity=1500.0, moisture=45.0, ph=6.5)
    cards = evaluate(reading_, "panicle_initiation", CALIBRATION, RULES, CONTENT)
    salinity = card_for_group(cards, "salinity")
    assert salinity.severity == "red"


def test_severe_salinity_is_act_now_at_every_stage():
    reading_ = reading(conductivity=8000.0, moisture=45.0, ph=6.5)
    tillering_cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    flowering_cards = evaluate(reading_, "flowering", CALIBRATION, RULES, CONTENT)
    assert card_for_group(tillering_cards, "salinity").severity == "red"
    assert card_for_group(flowering_cards, "salinity").severity == "red"


def test_a_deep_water_table_calls_for_reflooding_outside_flowering():
    # 15 per cent moisture maps to a 30 cm water table depth under the
    # shipped default calibration, well past the 15 cm re-flood trigger.
    reading_ = reading(conductivity=200.0, moisture=15.0, ph=6.5)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    water = card_for_group(cards, "water")
    assert water.severity == "red"
    assert water.headline == "Saatnya mengairi kembali"


def test_flowering_suspension_is_absolute_even_with_a_deep_water_table():
    reading_ = reading(conductivity=200.0, moisture=15.0, ph=6.5)
    cards = evaluate(reading_, "flowering", CALIBRATION, RULES, CONTENT)
    water = card_for_group(cards, "water")
    assert water.severity == "green"
    assert water.headline == "Jaga sawah tetap tergenang"


def test_flowering_suspension_also_applies_at_panicle_initiation():
    reading_ = reading(conductivity=200.0, moisture=15.0, ph=6.5)
    cards = evaluate(reading_, "panicle_initiation", CALIBRATION, RULES, CONTENT)
    water = card_for_group(cards, "water")
    assert water.headline == "Jaga sawah tetap tergenang"


def test_water_within_range_needs_no_action_outside_flowering():
    reading_ = reading(conductivity=200.0, moisture=45.0, ph=6.5)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    water = card_for_group(cards, "water")
    assert water.severity == "green"
    assert water.headline == "Pengeringan berkala berjalan aman"


def test_acidic_soil_below_5_5_recommends_lime():
    reading_ = reading(conductivity=200.0, moisture=35.0, ph=5.0)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    acidity = card_for_group(cards, "acidity")
    assert acidity.severity == "amber"
    assert "kapur" in acidity.body


def test_ph_at_exactly_5_5_counts_as_adequate():
    reading_ = reading(conductivity=200.0, moisture=35.0, ph=5.5)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    acidity = card_for_group(cards, "acidity")
    assert acidity.severity == "green"


def test_nutrients_card_never_needs_the_raw_nutrient_registers():
    # Only moisture, conductivity and ph are supplied. If any rule needed
    # nitrogen_raw, phosphorus_raw or potassium_raw this would come back
    # with fewer than four cards instead of the full set.
    reading_ = reading(conductivity=1500.0, moisture=15.0, ph=5.0)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    assert len(cards) == 4
    nutrients = card_for_group(cards, "nutrients")
    assert nutrients.severity == "green"
    assert nutrients.icon == "nutrient"


def test_nutrients_card_is_always_good_never_alarming():
    for conductivity in (200.0, 1500.0, 3000.0, 8000.0):
        reading_ = reading(conductivity=conductivity, moisture=35.0, ph=6.5)
        cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
        assert card_for_group(cards, "nutrients").severity == "green"


def test_full_ranking_matches_salinity_above_water_above_acidity_above_nutrients():
    # Severe salinity and a deep water table are both act_now; salinity
    # must still rank first because its group priority is higher.
    reading_ = reading(conductivity=8000.0, moisture=15.0, ph=5.0)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    assert [card.rule_group for card in cards] == ["salinity", "water", "acidity", "nutrients"]
    assert [card.severity for card in cards] == ["red", "red", "amber", "green"]


def test_overall_status_is_the_severity_of_the_top_ranked_card():
    reading_ = reading(conductivity=8000.0, moisture=15.0, ph=5.0)
    cards = evaluate(reading_, "tillering", CALIBRATION, RULES, CONTENT)
    overall_status = cards[0].severity
    assert overall_status == "red"


def test_no_content_string_quotes_the_pooled_meta_analysis_figure():
    for entry in CONTENT.entries.values():
        for text in (entry.headline_id, entry.body_id, entry.subtitle_en):
            assert "64.5" not in text
            assert "64,5" not in text


def test_every_shipped_content_entry_is_marked_draft():
    assert len(CONTENT.entries) == 13
    assert all(entry.draft is True for entry in CONTENT.entries.values())


def test_every_rule_content_key_resolves_in_the_shipped_content_pack():
    for rule in RULES.rules:
        CONTENT.get(rule.content_key)  # raises KeyError if missing
