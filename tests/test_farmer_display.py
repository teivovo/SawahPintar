import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import WorkshopConfig
from app.server import create_app
from app.state import WorkshopState
from app.storage import db

WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"


def fake_evaluate(reading, stage, calibration, rules, content):
    return []


def make_client():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    state = WorkshopState.build(connection, config, "config.json", evaluate_fn=fake_evaluate)
    return TestClient(create_app(state)), state


def test_index_page_serves_as_html():
    client, state = make_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    state.con.close()


def test_style_and_script_are_served_locally():
    client, state = make_client()
    assert client.get("/style.css").status_code == 200
    assert client.get("/app.js").status_code == 200
    state.con.close()


def test_no_asset_references_a_remote_url():
    for name in ("index.html", "style.css", "app.js"):
        content = (WEB_DIR / name).read_text(encoding="utf-8")
        assert re.search(r"https?://", content) is None, f"{name} references a remote URL"
        assert "cdn" not in content.lower(), f"{name} references a CDN"


def test_farmer_display_never_renders_raw_nutrient_registers():
    content = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    for forbidden in ("nitrogen_raw", "phosphorus_raw", "potassium_raw"):
        assert forbidden not in content


def test_simulation_watermark_is_removed():
    """The SIMULASI ribbon was removed at the operator's request; guard against
    it creeping back."""
    index_html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="watermark"' not in index_html
    assert "SIMULASI" not in index_html
    app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "updateWatermark" not in app_js
    assert "simulatedSensors" not in app_js


def test_advice_cards_rank_by_severity_then_rule_group_priority():
    content = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "RULE_GROUP_PRIORITY" in content
    assert ".slice(0, 4)" in content
    for group in ("salinity", "water", "acidity", "nutrients"):
        assert group in content


def test_trends_section_starts_collapsed_in_markup():
    content = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'class="trends collapsed"' in content
    assert "trends-content" in content


def test_trends_toggle_reruns_load_history_when_expanding():
    """loadHistory only ran once, at page load in start(), so the trends
    panel always excluded whatever readings had arrived since. It must be
    re-run when the facilitator opens the panel."""
    content = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    toggle_handler = content.split('toggle.addEventListener("click"', 1)[1].split(
        "});", 1
    )[0]
    assert "loadHistory(sensorId, panels[sensorId]);" in toggle_handler


def test_socket_close_shows_a_reconnect_banner_and_open_hides_it():
    """Stale numbers presented as current, indefinitely, is worse than no
    connection at all: a dead feed must be visibly announced."""
    content = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "showReconnectBanner" in content
    assert "hideReconnectBanner" in content
    close_handler = content.split('socket.addEventListener("close"', 1)[1].split(
        "});", 1
    )[0]
    assert "showReconnectBanner();" in close_handler
    assert 'socket.addEventListener("open", hideReconnectBanner);' in content


def test_reconnect_banner_element_starts_hidden_in_markup():
    content = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="reconnect-banner" class="reconnect-banner" hidden' in content


def test_language_is_carried_on_the_websocket_and_reapplied():
    """A language toggle pressed in the operator console must reach a
    farmer display already open in another window, not only a fresh page
    load."""
    content = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    message_handler = content.split('socket.addEventListener("message"', 1)[1].split(
        "});", 1
    )[0]
    assert "document.body.dataset.language = message.language" in message_handler


def test_farmer_stylesheet_never_follows_the_os_dark_theme():
    """A two-class selector such as .advice-card.severity-green always beats
    a one-class selector such as .advice-card inside an @media block, no
    matter the media query, so a dark-mode override on .advice-card alone
    can never win against the pastel severity backgrounds and left the
    headline and body text unreadable (contrast about 1:1) on a laptop
    whose OS theme was set to dark. The farmer display is specified for
    daylight legibility and commits to the light palette instead of
    maintaining a second one; see the color-scheme: light rule on :root."""
    content = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in content
    assert "color-scheme: light" in content
