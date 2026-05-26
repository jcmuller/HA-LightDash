"""Integration tests for the full parse→render→serve pipeline."""
from __future__ import annotations

from pathlib import Path

import httpx
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "simple.yaml"


def test_config_exists():
    assert CONFIG_PATH.exists(), f"Config not found at {CONFIG_PATH}"


def test_config_is_valid_yaml():
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "lvgl" in data, "Missing 'lvgl' section"
    assert "pages" in data["lvgl"], "Missing 'pages' in lvgl config"


def test_parse_and_render():
    from app.parser import parse_config
    from app.renderer import render_page

    dashboard = parse_config(str(CONFIG_PATH))
    assert len(dashboard.pages) > 0, "No pages parsed"
    assert dashboard.display_width == 800
    assert dashboard.display_height == 480

    for page in dashboard.pages:
        html = render_page(page, dashboard)
        assert "<!DOCTYPE html>" in html
        assert f'id="page-{page.id}"' in html
        assert "htmx.org" in html
        assert "lv-page" in html
        assert len(html) > 200


def test_render_all_widget_types():
    from app.parser import _parse_widget
    from app.renderer import render_page as _rp
    from app.models import Dashboard, Page

    widget_configs = [
        {"label": {"text": "Hello", "text_color": 0xFFFFFF}},
        {"button": {"text": "Click", "bg_color": 0x2F8CD8}},
        {"slider": {"value": 50, "min": 0, "max": 100}},
        {"switch": {"text": "Toggle"}},
        {"switch": {"text": "On", "state": True}},
        {"checkbox": {"text": "Check", "checked": True}},
        {"bar": {"value": 75, "width": 200, "height": 20}},
        {"arc": {"value": 60, "width": 100, "height": 100}},
        {"led": {"color": 0x00FF00, "brightness": 255}},
        {"spinner": {"width": 40, "height": 40}},
        {"textarea": {"text": "Type here", "placeholder": "Enter..."}},
        {"dropdown": {"options": ["A", "B", "C"], "selected": 1}},
        {"roller": {"options": ["X", "Y", "Z"], "selected": 0, "visible_row_count": 3}},
        {"line": {"points": [0, 0, 100, 50, 200, 0], "line_color": 0x00FF00, "line_width": 2}},
        {"obj": {"width": "100%", "widgets": [{"label": {"text": "nested"}}]}},
    ]

    for wc in widget_configs:
        w = _parse_widget(wc)
        assert w is not None, f"Failed to parse: {wc}"
        assert w.type == list(wc.keys())[0], f"Bad type: {w.type}"

    dashboard = Dashboard(pages=[Page(id="test", title="Test")])
    parsed = []
    for wc in widget_configs:
        w = _parse_widget(wc)
        if w is not None:
            parsed.append(w)
    dashboard.pages[0].widgets = parsed

    html = _rp(dashboard.pages[0], dashboard)
    assert "<!DOCTYPE html>" in html

    for wc in widget_configs:
        wtype = list(wc.keys())[0]
        assert f'lv-{wtype}' in html, f"Missing class lv-{wtype} in output"


def test_server_starts_and_serves(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", str(CONFIG_PATH))

    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "LightDash" in r.text
        assert "main" in r.text

        r2 = client.get("/page/main")
        assert r2.status_code == 200
        assert "<!DOCTYPE html>" in r2.text
        assert "lv-page" in r2.text

        r3 = client.get("/page/nonexistent")
        assert r3.status_code == 404

        r4 = client.get("/health")
        assert r4.status_code == 200
        data = r4.json()
        assert "status" in data
        assert "ha_connected" in data


def test_action_endpoint():
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        r = client.post("/action", json={"widget_id": "test", "event": "on_click", "type": "button"})
        assert r.status_code == 200
