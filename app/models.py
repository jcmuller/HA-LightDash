from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Action:
    action: str = "none"
    service: str = ""
    target: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    navigation_path: str = ""
    url_path: str = ""


@dataclass
class Card:
    type: str
    config: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)


@dataclass
class Section:
    type: str = "grid"
    columns: int = 3
    cards: List[Card] = field(default_factory=list)


@dataclass
class View:
    title: str
    path: str
    icon: str = ""
    badges: List[Dict[str, Any]] = field(default_factory=list)
    cards: List[Card] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    type: str = "sections"
    bg_color: str = ""
    bg_image: str = ""
    max_columns: int = 1


@dataclass
class LightdashConfig:
    container_width: str = ""
    container_height: str = ""


@dataclass
class Dashboard:
    title: str = "LightDash"
    views: List[View] = field(default_factory=list)
    lightdash: LightdashConfig = field(default_factory=LightdashConfig)
