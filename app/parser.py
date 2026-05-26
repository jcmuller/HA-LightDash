from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from app.models import Dashboard, GridCell, LayoutConfig, Page, Widget


EVENT_KEYS = {
    "on_click", "on_value", "on_change", "on_long_press",
    "on_long_press_repeat", "on_release", "on_focus",
    "on_scroll", "on_scroll_begin", "on_scroll_end", "on_boot",
}

LAYOUT_SHORTHAND = {
    "horizontal": {"type": "flex", "flex_flow": "ROW"},
    "vertical": {"type": "flex", "flex_flow": "COLUMN"},
}


def parse_config(path: Union[str, Path]) -> Dashboard:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    lvgl_config = raw.get("lvgl", {})
    if not lvgl_config:
        raise ValueError("No 'lvgl:' section found in config")

    dashboard = Dashboard()

    display = raw.get("display")
    if display and isinstance(display, list) and len(display) > 0:
        dims = display[0].get("dimensions", {})
        dashboard.display_width = dims.get("width", dashboard.display_width)
        dashboard.display_height = dims.get("height", dashboard.display_height)

    pages_data = lvgl_config.get("pages", [])
    flat_widgets = lvgl_config.get("widgets", [])

    if pages_data:
        for page_data in pages_data:
            if not isinstance(page_data, dict):
                continue
            page = Page(
                id=page_data.get("id", f"page_{len(dashboard.pages)}") or f"page_{len(dashboard.pages)}",
                title=page_data.get("title", page_data.get("id", "")),
                layout=_parse_layout(page_data.get("layout")),
                bg_color=_parse_color(page_data.get("bg_color")),
            )
            for w in page_data.get("widgets", []):
                parsed = _parse_widget(w)
                if parsed:
                    page.widgets.append(parsed)
            dashboard.pages.append(page)
    elif flat_widgets:
        page = Page(id="main", title="Main")
        for w in flat_widgets:
            parsed = _parse_widget(w)
            if parsed:
                page.widgets.append(parsed)
        dashboard.pages.append(page)

    if not dashboard.pages:
        dashboard.pages.append(Page(id="empty", title="Empty"))

    bg_color = lvgl_config.get("bg_color")
    if bg_color:
        dashboard.bg_color = _parse_color(bg_color)

    return dashboard


def _parse_widget(data: Any) -> Optional[Widget]:
    if not isinstance(data, dict):
        return None

    type_name = next(iter(data.keys()))
    raw = data[type_name]
    if not isinstance(raw, dict):
        raw = {}

    widget_id = raw.pop("id", "") or ""
    text = raw.pop("text", "") or ""
    children_raw = raw.pop("widgets", [])

    events: Dict[str, Any] = {}
    other_props: Dict[str, Any] = {}

    for k, v in raw.items():
        if k in EVENT_KEYS and isinstance(v, (dict, list)):
            events[k] = v
        elif k == "layout":
            other_props[k] = _parse_layout(v)
        else:
            other_props[k] = v

    children: List[Widget] = []
    if isinstance(children_raw, list):
        for c in children_raw:
            parsed = _parse_widget(c)
            if parsed:
                children.append(parsed)

    return Widget(
        type=type_name,
        widget_id=widget_id,
        text=text,
        props=other_props,
        events=events,
        children=children,
    )


def _parse_layout(data: Any) -> Optional[LayoutConfig]:
    if data is None:
        return None
    if isinstance(data, str):
        shorthand = data.strip().lower()
        if shorthand in LAYOUT_SHORTHAND:
            return LayoutConfig(**LAYOUT_SHORTHAND[shorthand])
        if "x" in shorthand:
            parts = shorthand.split("x")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return LayoutConfig(
                    type="grid",
                    grid_rows=[_grid_fr(1)] * int(parts[0]),
                    grid_columns=[_grid_fr(1)] * int(parts[1]),
                )
        return None
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if v is not None}
        if "type" not in data:
            data["type"] = "flex"
        data["type"] = str(data["type"]).lower()
        return LayoutConfig(**data)
    return None


def _grid_fr(n: int) -> str:
    return f"{n}fr"


def _parse_color(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, int):
        return _hex_color(value)
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("0x") or value.startswith("0X"):
            return _hex_color(int(value, 16))
        return value
    return str(value)


def _hex_color(value: int) -> str:
    return f"#{value:06x}"
