from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LayoutConfig:
    type: str = "flex"
    flex_flow: Optional[str] = None
    flex_align_main: Optional[str] = None
    flex_align_cross: Optional[str] = None
    flex_align_track: Optional[str] = None
    flex_grow: Optional[int] = None
    grid_rows: Optional[List[Any]] = None
    grid_columns: Optional[List[Any]] = None


@dataclass
class GridCell:
    row_pos: Optional[int] = None
    column_pos: Optional[int] = None
    row_span: Optional[int] = None
    column_span: Optional[int] = None
    x_align: Optional[str] = None
    y_align: Optional[str] = None


@dataclass
class Widget:
    type: str
    widget_id: str = ""
    text: str = ""
    props: Dict[str, Any] = field(default_factory=dict)
    events: Dict[str, Any] = field(default_factory=dict)
    children: List[Widget] = field(default_factory=list)

    def get(self, key: str, default=None):
        return self.props.get(key, default)


@dataclass
class Page:
    id: str = ""
    title: str = ""
    widgets: List[Widget] = field(default_factory=list)
    layout: Optional[LayoutConfig] = None
    bg_color: Optional[str] = None


@dataclass
class Dashboard:
    pages: List[Page] = field(default_factory=list)
    display_width: int = 800
    display_height: int = 480
    bg_color: Optional[str] = None
