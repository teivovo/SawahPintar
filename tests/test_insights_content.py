import pytest

from app.insights.content import ContentPack, load_content

MINIMAL = {
    "example_key": {
        "icon": "water",
        "headline_id": "Contoh judul",
        "body_id": "Contoh isi saran",
        "subtitle_en": "Example advice",
        "draft": True,
    }
}


def test_from_dict_builds_a_content_entry():
    pack = ContentPack.from_dict(MINIMAL)
    entry = pack.get("example_key")
    assert entry.icon == "water"
    assert entry.headline_id == "Contoh judul"
    assert entry.body_id == "Contoh isi saran"
    assert entry.subtitle_en == "Example advice"
    assert entry.draft is True


def test_get_raises_a_clear_error_for_a_missing_key():
    pack = ContentPack.from_dict(MINIMAL)
    with pytest.raises(KeyError, match="no entry for key: missing_key"):
        pack.get("missing_key")


def test_from_dict_rejects_an_entry_missing_the_draft_flag():
    broken = {
        "example_key": {
            "icon": "water",
            "headline_id": "a",
            "body_id": "b",
            "subtitle_en": "c",
        }
    }
    with pytest.raises(ValueError, match="draft"):
        ContentPack.from_dict(broken)


def test_from_dict_rejects_an_entry_missing_the_icon():
    broken = {
        "example_key": {
            "headline_id": "a",
            "body_id": "b",
            "subtitle_en": "c",
            "draft": True,
        }
    }
    with pytest.raises(ValueError, match="icon"):
        ContentPack.from_dict(broken)


def test_load_reads_a_yaml_file(tmp_path):
    content_path = tmp_path / "content.yaml"
    content_path.write_text(
        "example_key:\n"
        "  icon: water\n"
        "  headline_id: Contoh judul\n"
        "  body_id: Contoh isi saran\n"
        "  subtitle_en: Example advice\n"
        "  draft: true\n",
        encoding="utf-8",
    )
    pack = load_content(content_path)
    assert pack.get("example_key").headline_id == "Contoh judul"
    assert pack.get("example_key").draft is True


def test_load_handles_an_empty_file(tmp_path):
    content_path = tmp_path / "empty.yaml"
    content_path.write_text("", encoding="utf-8")
    pack = load_content(content_path)
    with pytest.raises(KeyError):
        pack.get("anything")
