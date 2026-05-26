from typing import Dict, List, Optional, Tuple, Union

_NAMED_COLORS = {
    "tomato": "#ff6347", "springgreen": "#00ff7f", "light_blue": "#add8e6",
    "darkgray": "#a9a9a9", "gray200": "#c8c8c8", "black": "#000000",
    "white": "#ffffff", "red": "#ff0000", "green": "#00ff00", "blue": "#0000ff",
    "yellow": "#ffff00", "cyan": "#00ffff", "magenta": "#ff00ff",
    "silver": "#c0c0c0", "gray": "#808080", "maroon": "#800000",
    "olive": "#808000", "purple": "#800080", "teal": "#008080",
    "navy": "#000080", "orange": "#ffa500", "pink": "#ffc0cb",
    "brown": "#a52a2a", "gold": "#ffd700", "coral": "#ff7f50",
    "indigo": "#4b0082", "violet": "#ee82ee", "lime": "#00ff00",
}

_GRADIENT_DIR = {
    "VER": "to bottom",
    "HOR": "to right",
    "DIAG": "to bottom right",
    "DIAG_REV": "to top left",
}


def props_to_css(props: Dict) -> str:
    pairs = props_to_css_list(props)
    return "; ".join(f"{k}: {v}" for k, v in pairs)


def props_to_css_list(props: Dict) -> List[Tuple[str, str]]:
    styles: List[Tuple[str, str]] = []

    _add_size(styles, props, "width")
    _add_size(styles, props, "height")
    _add_size(styles, props, "min_width", "min-width")
    _add_size(styles, props, "max_width", "max-width")
    _add_size(styles, props, "min_height", "min-height")
    _add_size(styles, props, "max_height", "max-height")

    _add_bg(styles, props)
    _add_border(styles, props)
    _add_radius(styles, props)
    _add_padding(styles, props)
    _add_text(styles, props)
    _add_outline(styles, props)
    _add_shadow(styles, props)
    _add_opa(styles, props)

    if props.get("hidden"):
        styles.append(("display", "none"))

    scrollable = props.get("scrollable")
    if scrollable is False:
        styles.append(("overflow", "hidden"))
    elif scrollable is True or props.get("scrollbar_mode") in ("ON", "AUTO", "ACTIVE"):
        pass

    flex_grow = props.get("flex_grow")
    if flex_grow is not None:
        styles.append(("flex", str(flex_grow)))

    return styles


def _add_size(styles: List, props: Dict, lv_key: str, css_key: Optional[str] = None) -> None:
    val = props.get(lv_key)
    if val is None:
        return
    key = css_key or lv_key.replace("_", "-")
    styles.append((key, _size_to_css(val)))


def _size_to_css(value: Union[int, str]) -> str:
    if isinstance(value, int):
        return f"{value}px"
    s = str(value).strip()
    if s.upper() == "SIZE_CONTENT":
        return "fit-content"
    if s == "100%":
        return "100%"
    if s.endswith("%"):
        return s
    try:
        int_val = int(s)
        return f"{int_val}px"
    except ValueError:
        return s


def _add_bg(styles: List, props: Dict) -> None:
    bg_color = props.get("bg_color")
    if bg_color is None:
        return

    color_css = _color_to_css(bg_color)
    bg_grad_color = props.get("bg_grad_color")
    bg_grad_dir = props.get("bg_grad_dir")

    if bg_grad_color and bg_grad_dir:
        grad_dir = _GRADIENT_DIR.get(str(bg_grad_dir).upper(), "to bottom")
        styles.append(("background", f"linear-gradient({grad_dir}, {color_css}, {_color_to_css(bg_grad_color)})"))
    else:
        styles.append(("background-color", color_css))

    bg_opa = props.get("bg_opa")
    if bg_opa is not None:
        opa = _opa_value(bg_opa)
        if opa is not None and opa < 1.0:
            styles.append(("background-opacity", str(opa)))


def _add_border(styles: List, props: Dict) -> None:
    bw = props.get("border_width")
    if bw is None:
        return

    if bw == 0:
        styles.append(("border", "none"))
        return

    bc = _color_to_css(props.get("border_color", "0x808080"))
    side = props.get("border_side", "ALL")

    if side == "NONE":
        styles.append(("border", "none"))
        return

    bs = side
    if isinstance(bs, str):
        bs_val = str(bs).upper()
        if bs_val in ("ALL", "FULL", ""):
            styles.append(("border", f"{bw}px solid {bc}"))
            return
        bs = [bs]

    side_map = {"LEFT": "left", "RIGHT": "right", "TOP": "top", "BOTTOM": "bottom"}
    for s in (bs if isinstance(bs, list) else [bs]):
        css_side = side_map.get(str(s).upper())
        if css_side:
            styles.append((f"border-{css_side}", f"{bw}px solid {bc}"))


def _add_radius(styles: List, props: Dict) -> None:
    r = props.get("radius")
    if r is not None:
        styles.append(("border-radius", f"{r}px"))


def _add_padding(styles: List, props: Dict) -> None:
    pad_all = props.get("pad_all")
    if pad_all is not None:
        styles.append(("padding", f"{pad_all}px"))
    else:
        for lv_key, css_key in [
            ("pad_top", "padding-top"), ("pad_bottom", "padding-bottom"),
            ("pad_left", "padding-left"), ("pad_right", "padding-right"),
            ("pad_row", "padding-row"), ("pad_column", "padding-column"),
        ]:
            v = props.get(lv_key)
            if v is not None:
                styles.append((css_key, f"{v}px"))


def _add_text(styles: List, props: Dict) -> None:
    tc = props.get("text_color")
    if tc is not None:
        styles.append(("color", _color_to_css(tc)))

    ta = props.get("text_align")
    if ta is not None:
        styles.append(("text-align", str(ta).lower()))

    tf = props.get("text_font")
    if tf is not None:
        fs = _parse_font_size(str(tf))
        if fs:
            styles.append(("font-size", f"{fs}px"))


def _add_outline(styles: List, props: Dict) -> None:
    ow = props.get("outline_width")
    if ow is not None and ow > 0:
        oc = _color_to_css(props.get("outline_color", "0xFFFFFF"))
        styles.append(("outline", f"{ow}px solid {oc}"))


def _add_shadow(styles: List, props: Dict) -> None:
    sw = props.get("shadow_width")
    if sw is not None and sw > 0:
        sx = props.get("shadow_offset_x", 0) or 0
        sy = props.get("shadow_offset_y", 0) or 0
        sc = _color_to_css(props.get("shadow_color", "#000000"))
        styles.append(("box-shadow", f"{sx}px {sy}px {sw}px {sc}"))


def _add_opa(styles: List, props: Dict) -> None:
    opa = props.get("opa")
    if opa is not None:
        v = _opa_value(opa)
        if v is not None:
            styles.append(("opacity", str(v)))


def _color_to_css(value: Union[int, str]) -> str:
    if isinstance(value, int):
        return f"#{value:06x}"
    s = str(value).strip().lower()
    if s in _NAMED_COLORS:
        return _NAMED_COLORS[s]
    if s.startswith("0x"):
        return f"#{int(s, 16):06x}"
    if s.startswith("#"):
        return s
    if s.replace(" ", "").startswith("rgb"):
        return s
    named = _NAMED_COLORS.get(s)
    if named:
        return named
    return s


def _opa_value(value: Union[int, str]) -> Optional[float]:
    if isinstance(value, (int, float)):
        if value <= 1:
            return float(value)
        return None
    s = str(value).strip().upper()
    if s == "COVER":
        return 1.0
    if s == "TRANSP":
        return 0.0
    if s.endswith("%"):
        try:
            return float(s.rstrip("%")) / 100.0
        except ValueError:
            return None
    return None


def _parse_font_size(font_str: str) -> Optional[int]:
    import re
    match = re.search(r"_(\d+)$", font_str)
    if match:
        return int(match.group(1))
    return None
