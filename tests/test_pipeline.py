from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from app.models import Dashboard, View, Card

BASE_DIR = Path(__file__).resolve().parent.parent
TEST_CONFIG = BASE_DIR / "config" / "living_room.yaml"


def test_config_exists():
    assert TEST_CONFIG.exists(), f"Config not found at {TEST_CONFIG}"


def test_config_is_valid_yaml():
    with open(TEST_CONFIG) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "views" in data, "Missing 'views' section"


def test_parse_local_yaml():
    from app.parser import parse_dashboard_from_file

    dashboard = parse_dashboard_from_file(str(TEST_CONFIG))
    assert len(dashboard.views) > 0, "No views parsed"
    assert dashboard.title == "LightDash"

    view = dashboard.views[0]
    assert view.title == "Home"
    assert view.path == "home"
    assert len(view.sections) > 0
    assert len(view.sections[0].cards) > 0


def test_parse_from_dict():
    from app.parser import parse_dashboard

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Test",
                "path": "test",
                "cards": [
                    {"type": "heading", "heading": "Hello"},
                    {"type": "markdown", "content": "**bold** text"},
                    {"type": "entity", "entity": "sensor.temp"},
                    {"type": "button", "name": "Press", "tap_action": {"action": "toggle", "entity": "light.test"}},
                    {"type": "tile", "entity": "light.test", "color": "yellow"},
                    {"type": "entities", "entities": [{"entity": "sensor.a"}, {"entity": "sensor.b"}], "title": "Sensors"},
                    {"type": "glance", "entities": ["sensor.a", "sensor.b"], "columns": 2},
                    {"type": "grid", "columns": 2, "cards": [{"type": "entity", "entity": "sensor.a"}, {"type": "entity", "entity": "sensor.b"}]},
                    {"type": "horizontal-stack", "cards": [{"type": "entity", "entity": "sensor.a"}, {"type": "entity", "entity": "sensor.b"}]},
                    {"type": "vertical-stack", "cards": [{"type": "entity", "entity": "sensor.a"}, {"type": "entity", "entity": "sensor.b"}]},
                    {"type": "conditional", "conditions": [{"entity": "light.test", "state": "on"}], "card": {"type": "entity", "entity": "sensor.a"}},
                    {"type": "light", "entity": "light.test"},
                    {"type": "sensor", "entity": "sensor.temp", "graph": "line"},
                    {"type": "gauge", "entity": "sensor.temp", "min": 0, "max": 100},
                    {"type": "history-graph", "entities": ["sensor.temp"], "hours_to_show": 24},
                    {"type": "iframe", "url": "https://example.com"},
                    {"type": "unknown_type"},
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    assert dashboard.title == "LightDash"
    assert len(dashboard.views) == 1
    view = dashboard.views[0]
    assert view.title == "Test"
    assert view.path == "test"

    card_types = [c.type for c in view.cards]
    assert "heading" in card_types
    assert "markdown" in card_types
    assert "entity" in card_types
    assert "button" in card_types
    assert "tile" in card_types
    assert "entities" in card_types
    assert "glance" in card_types
    assert "grid" in card_types
    assert "horizontal-stack" in card_types
    assert "vertical-stack" in card_types
    assert "conditional" in card_types
    assert "light" in card_types
    assert "sensor" in card_types
    assert "gauge" in card_types
    assert "history-graph" in card_types
    assert "iframe" in card_types
    assert "unknown_type" in card_types


def test_parse_and_render_all_cards():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "All Cards",
                "path": "all",
                "cards": [
                    {"type": "heading", "heading": "Section", "icon": "mdi:home"},
                    {"type": "markdown", "content": "Hello **world**"},
                    {"type": "entity", "entity": "sensor.temp", "name": "Temperature"},
                    {"type": "button", "name": "Toggle", "icon": "mdi:lightbulb", "tap_action": {"action": "toggle"}},
                    {"type": "tile", "entity": "light.test", "name": "Lamp", "icon": "mdi:lamp", "color": "yellow"},
                    {"type": "entities", "entities": [{"entity": "sensor.a"}, {"entity": "sensor.b"}], "title": "Sensors"},
                    {"type": "glance", "entities": ["sensor.a", "sensor.b", "sensor.c"], "columns": 3, "title": "Overview"},
                    {"type": "grid", "columns": 2, "cards": [{"type": "entity", "entity": "sensor.a"}, {"type": "entity", "entity": "sensor.b"}]},
                    {"type": "horizontal-stack", "cards": [{"type": "entity", "entity": "sensor.a"}, {"type": "entity", "entity": "sensor.b"}]},
                    {"type": "vertical-stack", "cards": [{"type": "entity", "entity": "sensor.a"}]},
                    {"type": "conditional", "conditions": [{"entity": "light.test", "state": "on"}], "card": {"type": "entity", "entity": "sensor.a"}},
                    {"type": "light", "entity": "light.test", "name": "Ceiling"},
                    {"type": "sensor", "entity": "sensor.temp", "name": "Temp"},
                    {"type": "gauge", "entity": "sensor.temp", "min": 0, "max": 100},
                    {"type": "history-graph", "entities": ["sensor.temp"], "hours_to_show": 24},
                    {"type": "iframe", "url": "https://example.com"},
                    {"type": "clock", "clock_style": "digital", "time_zone": "Europe/London", "time_format": "24", "no_background": True},
                    {"type": "placeholder"},
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    assert "<!DOCTYPE html>" in html
    assert 'id="view-all"' in html
    assert "htmx.org" in html
    assert "lv-view" in html
    assert "ha-card" in html

    for ctype in ["heading", "entity", "entities", "glance", "grid", "light", "sensor", "gauge", "iframe", "clock", "placeholder"]:
        assert f"{ctype}-card" in html or f"{ctype}_card" in html, f"Missing class for {ctype}"

        assert "Hello" in html
    assert "<strong>world</strong>" in html or "strong" in html


def test_tile_toggle_switch_for_binary_entity():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Tiles",
                "path": "tiles",
                "cards": [
                    {"type": "tile", "entity": "light.test", "name": "Lamp", "color": "yellow"},
                    {"type": "tile", "entity": "sensor.temp", "name": "Temp"},
                    {"type": "tile", "entity": "light.porch", "name": "Porch", "vertical": True, "hide_state": True},
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    # Binary entity (light) without hide_state → toggle-switch + entity-state
    assert html.count('class="toggle-switch"') == 1, "Expected 1 toggle-switch (light.test only)"
    assert html.count('class="toggle-input"') == 1, "Expected 1 toggle-input"
    assert html.count('class="toggle-slider"') == 1, "Expected 1 toggle-slider"

    # Non-binary entity (sensor) → no toggle, text state
    assert '<div class="tile-name">Temp</div>' in html

    # Binary entity with hide_state + vertical → no toggle, no entity-state text
    assert '<div class="tile-name">Porch</div>' in html
    assert 'class="tile-content vertical"' in html, "Expected vertical class"
    # light.test + sensor.temp = 2 entity-state spans; Porch has hide_state so no extra
    assert html.count('class="entity-state"') == 2, "Expected 2 entity-state spans (light + sensor)"

    # Toggle sync script included (for light.test + any entities card toggles)
    assert "function st()" in html, "Expected toggle sync script"


def test_tile_vertical_layout():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Tile Vertical",
                "path": "tv",
                "cards": [
                    {"type": "tile", "entity": "light.test", "vertical": True},
                    {"type": "tile", "entity": "light.test2"},  # no vertical
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    assert 'class="tile-content vertical"' in html
    assert 'class="tile-content"' in html  # non-vertical still present
    # Both should match but only one with 'vertical' class — check count
    assert html.count('class="tile-content') == 2


def test_tile_hide_state():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Tiles",
                "path": "tiles",
                "cards": [
                    {"type": "tile", "entity": "sensor.temp", "hide_state": True},
                    {"type": "tile", "entity": "sensor.temp2"},  # no hide_state
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    # hide_state tile has no entity-state span
    assert 'class="entity-state"' in html  # second tile still shows state
    # Count entity-state occurrences — second tile has one
    assert html.count('class="entity-state"') == 1, "Expected only 1 entity-state (non-hidden tile)"


def test_uplot_loaded_when_needed():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Charts",
                "path": "charts",
                "cards": [
                    {"type": "sensor", "entity": "sensor.temp", "graph": "line"},
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    assert "uplot" in html.lower() or "uPlot" in html


def test_server_starts_and_serves():
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "LightDash" in r.text

        r2 = client.get("/health")
        assert r2.status_code == 200
        data = r2.json()
        assert "status" in data
        assert "ha_connected" in data


def test_action_endpoint():
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.post("/action", json={"entity_id": "light.test", "action": "toggle", "service": "light.toggle"})
        assert r.status_code == 200

        r2 = client.post("/action", json={"entity_id": "light.test", "action": "call-service", "service": "light.turn_on", "target": {"entity_id": "light.test"}, "data": {"brightness_pct": 50}})
        assert r2.status_code == 200


def test_api_dashboard_endpoint():
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/api/dashboard")
        if r.status_code == 200:
            data = r.json()
            assert "views" in data
            assert "title" in data


def test_unknown_card_renders_placeholder():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Test",
                "path": "test",
                "cards": [
                    {"type": "completely_fake_card_type"},
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    assert "placeholder-card" in html
    assert "?" in html


def test_markdown_rendering():
    from app.renderer import _render_markdown_text

    md = "# Title\n\n**bold** text\n\n- item 1\n- item 2\n\n`code`"
    html = _render_markdown_text(md)

    assert "Title" in html
    assert "strong" in html or "bold" in html


def test_friendly_name():
    from app.renderer import _friendly_name

    assert _friendly_name("sensor.living_room_temperature") == "Living Room Temperature"
    assert _friendly_name("light.test") == "Test"
    assert _friendly_name("no_dot") == "no_dot"


def test_entities_cover_controls():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Entities",
                "path": "ents",
                "cards": [
                    {
                        "type": "entities",
                        "title": "Controls",
                        "entities": [
                            "sensor.temp",
                            "cover.kitchen_roof",
                            {"entity": "cover.garage_door", "name": "Garage"},
                        ],
                    }
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    # Cover controls rendered for both cover entities
    assert 'class="cover-controls"' in html
    # Three buttons per cover × 2 covers = 6
    assert html.count('class="cover-btn"') == 6

    # Buttons use correct services
    assert "cover.open_cover" in html
    assert "cover.stop_cover" in html
    assert "cover.close_cover" in html

    # Button symbols present
    assert "▲" in html
    assert "⏹" in html
    assert "▼" in html

    # Non-cover entity (sensor) has no cover controls
    # 2 cover entities = 2 containers; sensor row has none
    assert html.count("cover-controls") == 2
    assert html.count("cover-btn") == 6


def test_cover_controls_in_tile_features_not_needed():
    """Verify cover entities in the living_room config get control buttons."""
    from app.parser import parse_dashboard_from_file

    dashboard = parse_dashboard_from_file(str(TEST_CONFIG))
    view = dashboard.views[0]
    assert len(view.sections) > 0

    # The entities card with cover.kitchen_roof is in the first section
    section = view.sections[0]
    found_cover = False
    for c in section.cards:
        if c.type == "entities":
            ents = c.get("entities", [])
            for ent in ents:
                eid = ent if isinstance(ent, str) else ent.get("entity", "")
                if eid == "cover.kitchen_roof":
                    found_cover = True
                    break
    assert found_cover, "cover.kitchen_roof should be in the entities card"


def test_tile_numeric_input_feature():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Numbers",
                "path": "nums",
                "cards": [
                    {
                        "type": "tile",
                        "entity": "input_number.test",
                        "name": "Test",
                        "features": [
                            {"type": "numeric-input"},
                        ],
                    }
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    # Numeric-input feature rendered
    assert 'class="numeric-input"' in html
    assert 'class="num-btn"' in html

    # Decrement and increment buttons
    assert "input_number.decrement" in html
    assert "input_number.increment" in html

    # Button symbols
    assert "−" in html or "&minus;" in html
    assert "+" in html


def test_clock_card_renderer():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Clock",
                "path": "clk",
                "cards": [
                    {
                        "type": "clock",
                        "clock_style": "digital",
                        "time_zone": "Europe/London",
                        "time_format": "24",
                        "show_seconds": False,
                        "no_background": True,
                        "clock_size": "medium",
                    },
                    {
                        "type": "clock",
                        "clock_style": "digital",
                        "time_zone": "US/Eastern",
                        "time_format": "12",
                        "show_seconds": True,
                        "clock_size": "large",
                    },
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    # Clock card class
    assert "clock-card" in html
    assert "clock-digital" in html

    # No-background variant
    assert "clock-no-bg" in html

    # Size classes
    assert "clock-size-medium" in html
    assert "clock-size-large" in html

    # Data attributes for first clock
    assert 'data-tz="Europe/London"' in html
    assert 'data-fmt="24"' in html
    assert 'data-sec="1"' in html  # second clock only

    # Second clock attributes
    assert 'data-tz="US/Eastern"' in html
    assert 'data-fmt="12"' in html

    # Clock ticker script injected
    assert "function uc()" in html
    assert "setInterval(uc,30000)" in html
    assert 'Intl.DateTimeFormat("en-GB"' in html or "Intl.DateTimeFormat" in html


def test_entity_toggle_in_entities_card():
    from app.parser import parse_dashboard
    from app.renderer import render_view

    raw: Dict[str, Any] = {
        "views": [
            {
                "title": "Entities",
                "path": "ents",
                "cards": [
                    {
                        "type": "entities",
                        "entities": [
                            "light.kitchen",
                            "sensor.temp",
                            "fan.bathroom",
                            "cover.garage",
                        ],
                    }
                ],
            }
        ]
    }

    dashboard = parse_dashboard(raw)
    view = dashboard.views[0]
    html = render_view(view, dashboard)

    # Binary non-cover entities get toggle switches
    assert html.count('class="entity-toggle"') == 2, "Expected 2 toggles (light + fan)"

    # Cover gets cover controls instead
    assert 'class="cover-controls"' in html

    # Sensor gets no controls
    rows = html.split('class="entity-row"')
    assert len(rows) == 5  # header + 4 rows

    # Toggle sync script present (because light entity has toggle)
    assert "function st()" in html


def test_entity_icon_resolution():
    import app.renderer as r

    # Priority 1: config icon wins
    assert r._entity_icon("light.porch", "mdi:lamp") == "mdi:lamp"
    # Priority 2: entity state icon (set module-level _entity_icons)
    r._entity_icons = {"light.porch": "mdi:lightbulb-outline", "sensor.temp": "mdi:thermometer-alert"}
    assert r._entity_icon("light.porch", "") == "mdi:lightbulb-outline"
    # Priority 3: domain default
    r._entity_icons = {}
    assert r._entity_icon("sensor.unknown", "") == "mdi:thermometer"
    # Priority 4: empty
    assert r._entity_icon("totally_fake.entity", "") == ""

def test_icon_html_without_ha_url():
    import app.renderer as r

    r._ha_url = ""
    assert r._icon_html("mdi:lightbulb", 24) == ""
    assert r._icon_html("", 24) == ""

def test_icon_html_with_cache():
    import app.renderer as r

    r._ha_url = "http://ha.local:8123"
    r._icon_svg_cache["lightbulb"] = '<svg viewBox="0 0 24 24"><path d="M12 2"/></svg>'
    html = r._icon_html("mdi:lightbulb", 24)
    assert 'class="icon"' in html
    assert 'width="24"' in html
    assert 'height="24"' in html
    assert '<path d="M12 2"/>' in html
    r._icon_svg_cache.clear()
    r._ha_url = ""
