"""The content pack loads the shipped advice.yaml, including the review-only
npk_estimate block which must be skipped rather than parsed as advice."""

import pytest

from app.insights.content import ContentPack, load_content


def test_shipped_advice_loads_and_skips_the_npk_estimate_block():
    pack = load_content("data/content/advice.yaml")
    assert len(pack.entries) == 13  # the advice entries, not the npk_estimate block
    assert "npk_estimate" not in pack.entries
    assert "salinity_none" in pack.entries


def test_from_dict_skips_reserved_keys():
    data = {
        # A review-only block with none of the advice fields; must be ignored.
        "npk_estimate": {"nitrogen": {"low": {"range": "below 80"}}},
        "salinity_none": {
            "icon": "salinity",
            "headline_id": "h",
            "body_id": "b",
            "subtitle_en": "s",
            "draft": True,
        },
    }
    pack = ContentPack.from_dict(data)
    assert list(pack.entries) == ["salinity_none"]


def test_a_real_advice_entry_still_requires_its_fields():
    with pytest.raises(ValueError):
        ContentPack.from_dict({"salinity_none": {"icon": "salinity"}})
