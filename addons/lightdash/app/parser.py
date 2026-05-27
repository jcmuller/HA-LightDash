from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from app.models import Card, Dashboard, LightdashConfig, Section, View


def parse_dashboard(raw: Dict[str, Any]) -> Dashboard:
    if "data" in raw and isinstance(raw["data"], dict):
        raw = raw["data"]

    raw_views: List[Dict[str, Any]]
    if "views" in raw:
        raw_views = raw["views"]
    elif isinstance(raw, list):
        raw_views = raw
    else:
        raw_views = []

    dashboard = Dashboard(title=raw.get("title", "LightDash"))
    ld = raw.get("lightdash", {})
    if isinstance(ld, dict):
        dashboard.lightdash = LightdashConfig(
            container_width=ld.get("container_width", ""),
            container_height=ld.get("container_height", ""),
        )
    for vd in raw_views:
        if not isinstance(vd, dict):
            continue
        dashboard.views.append(_parse_view(vd))
    return dashboard


def parse_dashboard_from_file(path: Union[str, Path]) -> Dashboard:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raise ValueError("Empty config file")
    return parse_dashboard(raw)


def parse_dashboard_from_api(data: Dict[str, Any]) -> Dashboard:
    return parse_dashboard(data)


def _extract_bg_image(raw: Any) -> str:
    if isinstance(raw, dict):
        img = raw.get("image", "")
        if img:
            return img
    elif isinstance(raw, str):
        m = re.search(r'url\("([^"]+)"\)', raw)
        if m:
            return m.group(1)
    return ""


def _parse_view(data: Dict[str, Any]) -> View:
    raw_cards: List[Dict[str, Any]] = data.get("cards") or []
    view_type = data.get("type", "sections")

    bg_image = _extract_bg_image(data.get("background", ""))

    if view_type == "custom:layout-card":
        return _parse_layout_view(data, raw_cards, bg_image)

    parsed_cards = [_parse_card(c) for c in raw_cards if isinstance(c, dict)]

    parsed_sections: List[Section] = []
    raw_sections = data.get("sections")
    if raw_sections and isinstance(raw_sections, list):
        for sec in raw_sections:
            section = _parse_section(sec)
            if section is not None:
                parsed_sections.append(section)

    return View(
        title=data.get("title", ""),
        path=data.get("path", _slug(data.get("title", "untitled"))),
        icon=data.get("icon", ""),
        badges=data.get("badges", []),
        cards=parsed_cards,
        sections=parsed_sections,
        type=view_type,
        bg_color=data.get("bg_color", ""),
        bg_image=bg_image,
        max_columns=data.get("max_columns", 1),
    )


def _parse_layout_view(data: Dict[str, Any], raw_cards: List[Dict[str, Any]], bg_image: str) -> View:
    layout = data.get("layout", {})
    max_cols = layout.get("max_cols", 2)
    col_count = max_cols if isinstance(max_cols, int) and max_cols >= 2 else 3

    sections: List[Section] = []
    current_cards: List[Dict[str, Any]] = []
    for c in raw_cards:
        if isinstance(c, dict) and c.get("type") == "custom:layout-break":
            if current_cards:
                sections.append(Section(
                    type="grid",
                    columns=col_count,
                    cards=[_parse_card(x) for x in current_cards if isinstance(x, dict)],
                ))
                current_cards = []
            continue
        current_cards.append(c)
    if current_cards:
        sections.append(Section(
            type="grid",
            columns=col_count,
            cards=[_parse_card(x) for x in current_cards if isinstance(x, dict)],
        ))

    return View(
        title=data.get("title", ""),
        path=data.get("path", _slug(data.get("title", "untitled"))),
        icon=data.get("icon", ""),
        badges=data.get("badges", []),
        cards=[],
        sections=sections,
        type="sections",
        bg_color=data.get("bg_color", ""),
        bg_image=bg_image,
        max_columns=layout.get("max_cols", 2),
    )


def _parse_section(data: Dict[str, Any]) -> Optional[Section]:
    if not isinstance(data, dict):
        return None
    raw_cards = data.get("cards") or []
    if not isinstance(raw_cards, list):
        return None
    if not raw_cards:
        entities = data.get("entities")
        if isinstance(entities, list):
            raw_cards = [{"type": "entities", "entities": entities}]
    cards = [_parse_card(c) for c in raw_cards if isinstance(c, dict)]
    columns = data.get("columns", 0)
    return Section(
        type=data.get("type", "grid"),
        columns=columns,
        cards=cards,
    )


def _parse_card(data: Dict[str, Any]) -> Card:
    card_type = data.get("type", "")
    config = {k: v for k, v in data.items() if k != "type"}

    mapper = _CUSTOM_CARD_MAP.get(card_type)
    if mapper:
        new_type, new_config = mapper(config)
        new_config["_original_type"] = card_type
        return Card(type=new_type, config=new_config)

    return Card(type=card_type, config=config)


def _slug(text: str) -> str:
    return text.lower().replace(" ", "_").replace("-", "_")


# --- Custom card mapping ---------------------------------------------------


def _map_mushroom_light(config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    new: Dict[str, Any] = {}
    new["entity"] = config.get("entity", "")
    new["name"] = config.get("name", "")
    features: list = []
    if config.get("show_brightness_control"):
        features.append({"type": "light-brightness"})
    if config.get("show_color_control"):
        features.append({"type": "light-color-temp"})
    if features:
        new["features"] = features
    if config.get("layout") == "horizontal":
        new["features_position"] = "inline"
    return "tile", new


def _map_mushroom_cover(config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    entity: Dict[str, Any] = {"entity": config.get("entity", "")}
    name = config.get("name", "")
    if name:
        entity["name"] = name
    if config.get("icon"):
        entity["icon"] = config["icon"]
    return "entities", {"entities": [entity]}


def _map_mushroom_number(config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    new: Dict[str, Any] = {}
    new["entity"] = config.get("entity", "")
    new["name"] = config.get("name", "")
    mode = config.get("display_mode", "buttons")
    if mode == "buttons":
        new["features"] = [{"type": "numeric-input"}]
    return "tile", new


_CUSTOM_CARD_MAP: Dict[str, Any] = {
    "custom:mushroom-light-card": _map_mushroom_light,
    "custom:mushroom-cover-card": _map_mushroom_cover,
    "custom:mushroom-number-card": _map_mushroom_number,
}
