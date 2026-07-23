import re
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"


def read(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


def test_insertion_messages_are_not_applied_immediately():
    content = read("app.js")
    handler = content.split("function connectFeed(sensorId)", 1)[1]
    assert "if (message.probe_inserted) {" in handler
    assert "playProbeInsertionSequence(message);" in handler
    branch = handler.split("if (message.probe_inserted) {", 1)[1].split("} else {", 1)[0]
    assert "applyUpdate(" not in branch


def test_normal_updates_still_apply_immediately():
    content = read("app.js")
    handler = content.split("function connectFeed(sensorId)", 1)[1]
    else_branch = handler.split("} else {", 1)[1].split("}", 1)[0]
    assert "applyUpdate(message.sensor_id" in else_branch


def test_animation_delay_is_long_enough_to_read_but_not_too_long():
    content = read("app.js")
    match = re.search(r"PROBE_READING_ANIMATION_MS\s*=\s*(\d+)", content)
    assert match is not None
    delay = int(match.group(1))
    assert 800 <= delay <= 5000


def test_reveal_sequence_shows_overlay_then_hides_it_after_the_delay():
    content = read("app.js")
    sequence = content.split("function playProbeInsertionSequence(message) {", 1)[1]
    assert sequence.index("showProbeOverlay()") < sequence.index("window.setTimeout")
    assert sequence.index("applyUpdate(") < sequence.index("hideProbeOverlay()")


def test_reveal_animation_is_defined_in_css():
    content = read("style.css")
    assert "@keyframes reveal-card" in content
    assert ".advice-cards.reveal .advice-card" in content


def test_probe_overlay_starts_hidden_in_markup():
    content = read("index.html")
    assert 'id="probe-overlay" class="probe-overlay" hidden' in content
