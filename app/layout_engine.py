from typing import Dict, List, Optional, Tuple, Union

from app.models import GridCell, LayoutConfig


def layout_to_css(layout: Optional[LayoutConfig]) -> List[Tuple[str, str]]:
    if layout is None:
        return []
    return _layout_to_css_list(layout)


def _layout_to_css_list(layout: LayoutConfig) -> List[Tuple[str, str]]:
    styles: List[Tuple[str, str]] = []

    if layout.type == "flex":
        styles.append(("display", "flex"))

        flex_flow = layout.flex_flow or "ROW"
        styles.append(("flex-flow", _flex_flow_to_css(flex_flow)))

        main_map = {
            "START": "flex-start", "END": "flex-end", "CENTER": "center",
            "SPACE_EVENLY": "space-evenly", "SPACE_AROUND": "space-around",
            "SPACE_BETWEEN": "space-between",
        }
        if layout.flex_align_main:
            styles.append(("justify-content", main_map.get(str(layout.flex_align_main).upper(), str(layout.flex_align_main).lower())))
        if layout.flex_align_cross:
            cross_map = {**main_map, "STRETCH": "stretch"}
            styles.append(("align-items", cross_map.get(str(layout.flex_align_cross).upper(), str(layout.flex_align_cross).lower())))
        if layout.flex_align_track:
            track_map = {**main_map, "STRETCH": "stretch"}
            styles.append(("align-content", track_map.get(str(layout.flex_align_track).upper(), str(layout.flex_align_track).lower())))
        if layout.flex_grow is not None:
            styles.append(("flex", str(layout.flex_grow)))

    elif layout.type == "grid":
        styles.append(("display", "grid"))
        if layout.grid_columns:
            styles.append(("grid-template-columns", _grid_track_to_css(layout.grid_columns)))
        if layout.grid_rows:
            styles.append(("grid-template-rows", _grid_track_to_css(layout.grid_rows)))

    return styles


def grid_cell_to_css(cell: Optional[GridCell]) -> List[Tuple[str, str]]:
    if cell is None:
        return []
    styles: List[Tuple[str, str]] = []
    if cell.column_pos is not None:
        styles.append(("grid-column", str(cell.column_pos + 1)))
    if cell.row_pos is not None:
        styles.append(("grid-row", str(cell.row_pos + 1)))
    if cell.column_span is not None and cell.column_span > 1:
        col_start = (cell.column_pos or 0) + 1
        styles.append(("grid-column", f"{col_start} / span {cell.column_span}"))
    if cell.row_span is not None and cell.row_span > 1:
        row_start = (cell.row_pos or 0) + 1
        styles.append(("grid-row", f"{row_start} / span {cell.row_span}"))
    align_map = {"START": "start", "END": "end", "CENTER": "center", "STRETCH": "stretch"}
    if cell.x_align:
        styles.append(("justify-self", align_map.get(str(cell.x_align).upper(), str(cell.x_align).lower())))
    if cell.y_align:
        styles.append(("align-self", align_map.get(str(cell.y_align).upper(), str(cell.y_align).lower())))
    return styles


def _flex_flow_to_css(flow: str) -> str:
    mapping = {
        "ROW": "row nowrap",
        "COLUMN": "column nowrap",
        "ROW_WRAP": "row wrap",
        "COLUMN_WRAP": "column wrap",
        "ROW_REVERSE": "row-reverse nowrap",
        "COLUMN_REVERSE": "column-reverse nowrap",
        "ROW_WRAP_REVERSE": "row-reverse wrap",
        "COLUMN_WRAP_REVERSE": "column-reverse wrap",
    }
    return mapping.get(str(flow).upper(), str(flow).lower().replace("_", "-"))


def _grid_track_to_css(tracks: List) -> str:
    return " ".join(_grid_size_to_css(t) for t in tracks)


def _grid_size_to_css(size: Union[str, int]) -> str:
    if isinstance(size, int):
        return f"{size}px"
    s = str(size).strip().upper()
    if s == "CONTENT" or s == "SIZE_CONTENT":
        return "min-content"
    if s.startswith("FR") or s.startswith("FLEX"):
        num = s[2:] or "1"
        return f"{num}fr"
    if s.endswith("PX"):
        return s
    if s.endswith("%"):
        return s
    try:
        return f"{int(s)}px"
    except ValueError:
        return s
