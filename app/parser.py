from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from app.models import Card, Dashboard, Section, View


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


def _parse_view(data: Dict[str, Any]) -> View:
    raw_cards: List[Dict[str, Any]] = data.get("cards") or []
    parsed_cards = [_parse_card(c) for c in raw_cards if isinstance(c, dict)]

    parsed_sections: List[Section] = []
    raw_sections = data.get("sections")
    if raw_sections and isinstance(raw_sections, list):
        for sec in raw_sections:
            section = _parse_section(sec)
            if section is not None:
                parsed_sections.append(section)

    bg_image = ""
    bg = data.get("background")
    if isinstance(bg, dict):
        img = bg.get("image", "")
        if img:
            bg_image = img

    return View(
        title=data.get("title", ""),
        path=data.get("path", _slug(data.get("title", "untitled"))),
        icon=data.get("icon", ""),
        badges=data.get("badges", []),
        cards=parsed_cards,
        sections=parsed_sections,
        type=data.get("type", "sections"),
        bg_color=data.get("bg_color", ""),
        bg_image=bg_image,
        max_columns=data.get("max_columns", 1),
    )


def _parse_section(data: Dict[str, Any]) -> Optional[Section]:
    if not isinstance(data, dict):
        return None
    raw_cards = data.get("cards") or []
    if not isinstance(raw_cards, list):
        return None
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
    return Card(type=card_type, config=config)


def _slug(text: str) -> str:
    return text.lower().replace(" ", "_").replace("-", "_")
