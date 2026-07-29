"""The operator console must open showing the settings that are actually
saved, not blank fields or first-option defaults sitting over live values.
Regression guard for the "settings saved don't show correctly" report."""

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
    config = WorkshopConfig.from_dict(
        {
            "site_name": "Sidrap",
            "growth_stage": "flowering",
            "sensors": {"S1": {"mode": "live", "port": "COM7", "name": "Blok 1"}},
        }
    )
    state = WorkshopState.build(connection, config, "config.json", evaluate_fn=lambda *a, **k: [])
    yield TestClient(create_app(state))
    connection.close()


def test_start_prefills_the_saved_settings():
    content = (WEB_DIR / "operator.js").read_text(encoding="utf-8")
    assert "prefillSettings(state)" in content
    assert 'document.getElementById("growth-stage").value = state.growth_stage' in content
    assert 'document.getElementById("site-name").value = state.site_name' in content
    # The current binding is reflected on the bind selects.
    assert "function fillBindFields" in content
    assert 'ensureOption(document.getElementById("bind-mode")' in content


def test_state_exposes_everything_the_prefill_needs(client):
    body = client.get("/api/state").json()
    assert body["site_name"] == "Sidrap"
    assert body["growth_stage"] == "flowering"
    plot = body["sensors"]["S1"]
    assert plot["mode"] == "live"
    assert plot["port"] == "COM7"
    assert plot["name"] == "Blok 1"
