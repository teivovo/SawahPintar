"""The operator zone editor: served as a static page, wired to /api/state
(load the current layout) and /api/zones (save it), and reachable from the
operator console."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import WorkshopConfig
from app.server import create_app
from app.state import WorkshopState
from app.storage import db

WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"


@pytest.fixture
def client():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    state = WorkshopState.build(connection, config, "config.json", evaluate_fn=lambda *a, **k: [])
    yield TestClient(create_app(state))
    connection.close()


def test_zone_editor_page_and_assets_are_served(client):
    assert client.get("/zone-editor.html").status_code == 200
    assert client.get("/zone-editor.js").status_code == 200
    assert client.get("/zone-editor.css").status_code == 200


def test_zone_editor_loads_state_and_saves_to_zones():
    content = (WEB_DIR / "zone-editor.js").read_text(encoding="utf-8")
    assert 'fetch("/api/state")' in content
    assert '/api/zones' in content
    assert "field_view" in content and "field_image" in content


def test_zone_editor_uses_no_remote_assets():
    for name in ("zone-editor.html", "zone-editor.js", "zone-editor.css"):
        text = (WEB_DIR / name).read_text(encoding="utf-8")
        import re

        assert re.search(r"https?://", text) is None, f"{name} references a remote URL"
        assert "cdn" not in text.lower()


def test_operator_console_links_to_the_zone_editor():
    operator = (WEB_DIR / "operator.html").read_text(encoding="utf-8")
    assert "/zone-editor.html" in operator
