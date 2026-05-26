from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional, Tuple

from app.layout_engine import grid_cell_to_css, layout_to_css
from app.models import Dashboard, GridCell, LayoutConfig, Page, Widget
from app.style_engine import _color_to_css, _size_to_css, props_to_css_list

_SP = "  "

EVENT_TRIGGER_MAP = {
    "on_click": "click",
    "on_value": "change",
    "on_change": "change",
    "on_long_press": "keydown[key=='Enter']",
    "on_release": "mouseup",
    "on_focus": "focus",
    "on_scroll": "scroll",
}

RENDERERS: Dict[str, Any] = {}


def register(type_name: str):
    def decorator(fn):
        RENDERERS[type_name] = fn
        return fn
    return decorator


def render_page(page: Page, dashboard: Dashboard) -> str:
    bg = ""
    if page.bg_color:
        bg = " background-color: " + _color_to_css(page.bg_color) + ";"
    elif dashboard.bg_color:
        bg = " background-color: " + _color_to_css(dashboard.bg_color) + ";"

    page_style = "width: " + str(dashboard.display_width) + "px; height: " + str(dashboard.display_height) + "px;" + bg

    children_lines = [_render_widget(w, 2) for w in page.widgets]
    children = "\n".join(children_lines)

    page_layout = layout_to_css(page.layout)
    if page_layout:
        page_style += " " + "; ".join(f"{k}: {v}" for k, v in page_layout)

    title = html.escape(page.title or page.id or "Dashboard")
    page_id = html.escape(page.id)

    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">\n'
        '<title>' + title + '</title>\n'
        '<link rel="stylesheet" href="/static/style.css">\n'
        '<script src="https://unpkg.com/htmx.org@2.0.4"></script>\n'
        '</head>\n'
        '<body>\n'
        '<div class="lv-page" id="page-' + page_id + '" hx-ext="sse" sse-connect="/_sse" style="' + page_style + '">\n'
        + children + '\n'
        '</div>\n'
        '</body>\n'
        '</html>'
    )


def render_page_list(pages: List[Page]) -> str:
    links = ""
    for p in pages:
        links += '    <li><a href="/page/' + html.escape(p.id) + '">' + html.escape(p.title or p.id) + '</a></li>\n'
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        '<title>LightDash</title>\n'
        '<style>\n'
        'body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }\n'
        'h1 { font-size: 1.5rem; margin-bottom: 16px; }\n'
        'ul { list-style: none; padding: 0; }\n'
        'li { margin: 8px 0; }\n'
        'a { color: #4fc3f7; text-decoration: none; font-size: 1.1rem; }\n'
        'a:hover { text-decoration: underline; }\n'
        '</style>\n'
        '</head>\n'
        '<body>\n'
        '<h1>LightDash</h1>\n'
        '<ul>\n'
        + links +
        '</ul>\n'
        '</body>\n'
        '</html>'
    )


def _render_widget(w: Widget, indent: int = 2) -> str:
    renderer = RENDERERS.get(w.type)
    if renderer is None:
        return _SP * indent + '<!-- unknown widget: ' + html.escape(w.type) + ' -->'
    html_out = renderer(w, indent)
    if html_out is None:
        return _SP * indent + '<!-- renderer returned None for: ' + html.escape(w.type) + ' -->'
    return html_out


def _common_attrs(w: Widget) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    if w.widget_id:
        attrs["id"] = w.widget_id
    classes = ["lv-" + w.type]
    if w.props.get("checkable"):
        classes.append("lv-checkable")
    attrs["class"] = " ".join(classes)

    css_pairs: List[Tuple[str, str]] = []

    layout = w.props.get("layout")
    if layout and isinstance(layout, LayoutConfig):
        css_pairs.extend(layout_to_css(layout))

    css_pairs.extend(props_to_css_list(w.props))

    gc = _extract_grid_cell(w.props)
    if gc:
        css_pairs.extend(grid_cell_to_css(gc))

    if css_pairs:
        attrs["style"] = "; ".join(f"{k}: {v}" for k, v in css_pairs)

    htmx = _events_to_htmx(w)
    attrs.update(htmx)

    return attrs


def _events_to_htmx(w: Widget) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for event_key, trigger in EVENT_TRIGGER_MAP.items():
        if event_key in w.events:
            attrs["hx-post"] = "/action"
            attrs["hx-trigger"] = trigger
            vals = {"widget_id": w.widget_id, "type": w.type, "event": event_key}
            attrs["hx-vals"] = json.dumps(vals)
            attrs["hx-swap"] = "none"
            break
    return attrs


def _extract_grid_cell(props: Dict) -> Optional[GridCell]:
    rp = props.get("grid_cell_row_pos")
    cp = props.get("grid_cell_column_pos")
    if rp is None and cp is None:
        return None
    return GridCell(
        row_pos=rp,
        column_pos=cp,
        row_span=props.get("grid_cell_row_span"),
        column_span=props.get("grid_cell_column_span"),
        x_align=props.get("grid_cell_x_align"),
        y_align=props.get("grid_cell_y_align"),
    )


def _render_children(children: List[Widget], indent: int) -> str:
    if not children:
        return ""
    out = "\n"
    for c in children:
        out += _render_widget(c, indent + 1) + "\n"
    out += _SP * (indent - 1)
    return out


def _h(tag: str, attrs: Dict[str, str], content: str = "", indent: int = 0) -> str:
    indent_str = _SP * indent
    attr_str = _build_attrs(attrs)
    self_closing = {"input", "br", "hr", "img", "meta", "link"}
    if tag in self_closing and not content:
        return indent_str + "<" + tag + attr_str + ">"
    return indent_str + "<" + tag + attr_str + ">" + content + "</" + tag + ">"


def _build_attrs(attrs: Dict[str, str]) -> str:
    if not attrs:
        return ""
    parts = []
    for k, v in attrs.items():
        if v is None or v is False:
            continue
        if v is True:
            parts.append(k)
        else:
            sv = str(v)
            escaped = sv.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append(k + '="' + escaped + '"')
    return " " + " ".join(parts) if parts else ""


@register("obj")
def _render_obj(w: Widget, indent: int) -> str:
    children = _render_children(w.children, indent + 1)
    attrs = _common_attrs(w)
    return _h("div", attrs, children, indent)


@register("container")
def _render_container(w: Widget, indent: int) -> str:
    return _render_obj(w, indent)


@register("label")
def _render_label(w: Widget, indent: int) -> str:
    text = html.escape(w.text) if w.text else ""
    attrs = _common_attrs(w)

    eid = w.widget_id
    if eid and "." in eid and "hx-swap" not in attrs:
        attrs["hx-get"] = "/api/value/" + eid
        attrs["hx-trigger"] = "load"
        attrs["hx-target"] = "this"
        attrs["hx-swap"] = "innerHTML"
        sse_event = "entity_" + eid.replace(".", "_")
        attrs["sse-swap"] = sse_event

    return _h("span", attrs, text, indent)


@register("button")
def _render_button(w: Widget, indent: int) -> str:
    text = html.escape(w.text) if w.text else ""
    attrs = _common_attrs(w)
    return _h("button", attrs, text, indent)


@register("slider")
def _render_slider(w: Widget, indent: int) -> str:
    val = w.get("value") or w.get("val") or 50
    min_val = w.get("min") or 0
    max_val = w.get("max") or 100

    wrapper_attrs: Dict[str, str] = {"class": "lv-slider-wrapper"}
    width = w.get("width")
    if width:
        wrapper_attrs["style"] = "width: " + _size_to_css(width) + ";"

    input_attrs = _common_attrs(w)
    input_attrs["type"] = "range"
    input_attrs["min"] = str(min_val)
    input_attrs["max"] = str(max_val)
    input_attrs["value"] = str(val)

    s_style = input_attrs.get("style", "")
    s_parts = [p.strip() for p in s_style.split(";") if p.strip() and not p.strip().startswith("width")]
    s_parts.append("width: 100%")
    input_attrs["style"] = "; ".join(s_parts)

    for attr in list(input_attrs.keys()):
        if attr.startswith("hx-"):
            del input_attrs[attr]
    eid = w.widget_id or ""
    input_attrs["hx-post"] = "/action"
    input_attrs["hx-trigger"] = "change"
    input_attrs["hx-vals"] = 'js:{widget_id:"' + eid + '",type:"slider",event:"on_value",value:this.value}'
    input_attrs["hx-swap"] = "none"
    input_attrs["hx-target"] = "this"

    s1 = _SP * (indent + 1)
    input_html = _h("input", input_attrs, "", indent + 1)
    val_span = s1 + '<span class="lv-slider-value">' + str(val) + "</span>"

    content = "\n" + input_html + "\n" + val_span + "\n" + _SP * indent
    return _h("div", wrapper_attrs, content, indent)


@register("switch")
def _render_switch(w: Widget, indent: int) -> str:
    checked = w.get("state")
    if checked is None:
        checked = w.get("checked", False)
    checked = bool(checked)

    input_attrs = _common_attrs(w)
    input_attrs["type"] = "checkbox"
    input_attrs["role"] = "switch"
    if checked:
        input_attrs["checked"] = "checked"

    s1 = _SP * (indent + 1)
    input_html = _h("input", input_attrs, "", indent + 1)
    label_html = ""
    if w.text:
        label_html = "\n" + s1 + '<span class="lv-switch-label">' + html.escape(w.text) + "</span>"

    content = "\n" + input_html + label_html + "\n" + _SP * indent
    return _h("label", {"class": "lv-switch-wrapper"}, content, indent)


@register("checkbox")
def _render_checkbox(w: Widget, indent: int) -> str:
    checked = w.get("checked", False)

    input_attrs = _common_attrs(w)
    input_attrs["type"] = "checkbox"
    if checked:
        input_attrs["checked"] = "checked"

    s1 = _SP * (indent + 1)
    input_html = _h("input", input_attrs, "", indent + 1)
    label_html = ""
    if w.text:
        label_html = "\n" + s1 + '<span class="lv-checkbox-label">' + html.escape(w.text) + "</span>"

    content = "\n" + input_html + label_html + "\n" + _SP * indent
    return _h("label", {"class": "lv-checkbox-wrapper"}, content, indent)


@register("bar")
def _render_bar(w: Widget, indent: int) -> str:
    min_val = int(w.get("min") or 0)
    max_val = int(w.get("max") or 100)
    val = int(w.get("value") or w.get("val") or 0)
    pct = ((val - min_val) / (max_val - min_val)) * 100 if max_val > min_val else 0
    pct = max(0, min(100, pct))

    bar_attrs = _common_attrs(w)
    bar_style = bar_attrs.get("style", "")
    if "height" not in bar_style:
        bar_style += ("; " if bar_style else "") + "display: flex; align-items: flex-end;"
    bar_attrs["style"] = bar_style

    s1 = _SP * (indent + 1)
    indicator = s1 + '<div class="lv-bar-indicator" style="width:' + str(pct) + '%;background:currentColor;height:100%"></div>\n' + _SP * indent

    content = "\n" + indicator
    return _h("div", bar_attrs, content, indent)


@register("arc")
def _render_arc(w: Widget, indent: int) -> str:
    min_val = int(w.get("min") or 0)
    max_val = int(w.get("max") or 100)
    val = int(w.get("value") or w.get("val") or 0)
    pct = ((val - min_val) / (max_val - min_val)) if max_val > min_val else 0
    pct = max(0, min(1, pct))

    size = w.get("width") or w.get("height") or 120
    if isinstance(size, str):
        try:
            size = int(size.replace("px", ""))
        except (ValueError, AttributeError):
            size = 120

    stroke_width = 8
    radius = size // 2 - stroke_width
    circumference = 2 * 3.14159 * radius
    dash = circumference * pct
    gap = circumference - dash

    svg = (
        '<svg width="' + str(size) + '" height="' + str(size) + '" viewBox="0 0 ' + str(size) + " " + str(size) + '">\n'
        + _SP * (indent + 2) + '<circle cx="' + str(size // 2) + '" cy="' + str(size // 2) + '" r="' + str(radius) + '" fill="none" stroke="#555" stroke-width="' + str(stroke_width) + '"/>\n'
        + _SP * (indent + 2) + '<circle cx="' + str(size // 2) + '" cy="' + str(size // 2) + '" r="' + str(radius) + '" fill="none" stroke="currentColor" stroke-width="' + str(stroke_width) + '" stroke-dasharray="'
        + f"{dash:.1f}" + " " + f"{gap:.1f}" + '" stroke-linecap="round"/>\n'
        + _SP * (indent + 1) + '</svg>'
    )

    attrs = _common_attrs(w)
    htmx_only = {k: v for k, v in attrs.items() if k.startswith("hx-")}
    arc_attrs: Dict[str, str] = {"class": "lv-arc"}
    if htmx_only:
        arc_attrs.update(htmx_only)
    style_attr = attrs.get("style", "")
    if style_attr:
        arc_attrs.setdefault("style", style_attr)

    val_text = '<span style="position:absolute;font-size:' + str(size // 4) + 'px;font-weight:bold">' + str(val) + '</span>'
    s1 = _SP * (indent + 1)
    content = "\n" + s1 + svg + "\n" + s1 + val_text + "\n" + _SP * indent
    return _h("div", arc_attrs, content, indent)


@register("textarea")
def _render_textarea(w: Widget, indent: int) -> str:
    placeholder = w.get("placeholder", "Enter text...")
    text = w.text or ""
    one_line = w.get("one_line", False)
    max_length = w.get("max_length")

    attrs = _common_attrs(w)
    wrapper_attrs: Dict[str, str] = {"class": "lv-textarea"}
    wrapper_style = attrs.get("style", "")
    if wrapper_style:
        wrapper_attrs["style"] = wrapper_style

    textarea_attrs: Dict[str, str] = {"placeholder": placeholder}
    if max_length:
        textarea_attrs["maxlength"] = str(max_length)
    if w.widget_id:
        textarea_attrs["id"] = w.widget_id
    textarea_attrs["class"] = "lv-textarea-input"

    if one_line:
        textarea_attrs["rows"] = "1"

    events = _events_to_htmx(w)
    textarea_attrs.update(events)

    ta = _h("textarea", textarea_attrs, html.escape(text), indent + 1)
    content = "\n" + ta + "\n" + _SP * indent
    return _h("div", wrapper_attrs, content, indent)


@register("dropdown")
def _render_dropdown(w: Widget, indent: int) -> str:
    options_raw = w.get("options", w.get("items", ""))
    selected = int(w.get("selected", 0))

    if isinstance(options_raw, str):
        options = [o.strip() for o in options_raw.split("\n") if o.strip()]
    elif isinstance(options_raw, list):
        options = [str(o) for o in options_raw]
    else:
        options = ["Option 1", "Option 2"]

    attrs = _common_attrs(w)
    wrapper_attrs: Dict[str, str] = {"class": "lv-dropdown"}
    wrapper_style = attrs.get("style", "")
    if wrapper_style:
        wrapper_attrs["style"] = wrapper_style

    select_attrs: Dict[str, str] = {}
    if w.widget_id:
        select_attrs["id"] = w.widget_id
    events = _events_to_htmx(w)
    select_attrs.update(events)

    options_html = ""
    for i, opt in enumerate(options):
        sel = " selected" if i == selected else ""
        options_html += "\n" + _SP * (indent + 2) + '<option value="' + str(i) + '"' + sel + ">" + html.escape(opt) + "</option>"

    select = _SP * (indent + 1) + "<select" + _build_attrs(select_attrs) + ">" + options_html + "\n" + _SP * (indent + 1) + "</select>"
    content = "\n" + select + "\n" + _SP * indent
    return _h("div", wrapper_attrs, content, indent)


@register("roller")
def _render_roller(w: Widget, indent: int) -> str:
    options_raw = w.get("options", w.get("items", ""))
    selected = int(w.get("selected", 0))
    visible = int(w.get("visible_row_count", 3))

    if isinstance(options_raw, str):
        options = [o.strip() for o in options_raw.split("\n") if o.strip()]
    elif isinstance(options_raw, list):
        options = [str(o) for o in options_raw]
    else:
        options = ["Option 1", "Option 2", "Option 3"]

    middle = visible // 2
    start = max(0, selected - middle)
    end = min(len(options), selected + middle + 1)
    visible_opts = options[start:end]

    items_html = ""
    for i, opt in enumerate(visible_opts):
        actual_idx = start + i
        cls = "lv-roller-item" + (" selected" if actual_idx == selected else "")
        items_html += "\n" + _SP * (indent + 1) + '<li class="' + cls + '" data-index="' + str(actual_idx) + '">' + html.escape(opt) + "</li>"

    attrs = _common_attrs(w)
    wrapper_attrs: Dict[str, str] = {"class": "lv-roller"}
    wrapper_style = attrs.get("style", "")
    if wrapper_style:
        wrapper_attrs["style"] = wrapper_style
    if w.widget_id:
        wrapper_attrs["data-roller-id"] = w.widget_id

    list_html = _SP * (indent + 1) + '<ul class="lv-roller-list">' + items_html + "\n" + _SP * (indent + 1) + "</ul>"
    content = "\n" + list_html + "\n" + _SP * indent
    return _h("div", wrapper_attrs, content, indent)


@register("led")
def _render_led(w: Widget, indent: int) -> str:
    color = w.get("color", "0x00FF00")
    brightness = int(w.get("brightness", 255))
    opa_val = brightness / 255.0

    attrs = _common_attrs(w)
    style = attrs.get("style", "")
    led_style = style + "; background-color: " + _color_to_css(color) + "; opacity: " + f"{opa_val:.2f}"
    if "width:" not in style and "height:" not in style:
        led_style += "; width: 20px; height: 20px; border-radius: 50%"
    attrs["style"] = led_style
    attrs["class"] = attrs.get("class", "") + " lv-led"

    return _h("span", attrs, "", indent)


@register("spinner")
def _render_spinner(w: Widget, indent: int) -> str:
    size = w.get("width") or w.get("height") or 40
    if isinstance(size, str):
        try:
            size = int(size.replace("px", ""))
        except (ValueError, AttributeError):
            size = 40

    attrs = _common_attrs(w)
    style = attrs.get("style", "")
    attrs["style"] = style + "; width: " + str(size) + "px; height: " + str(size) + "px"
    attrs["class"] = attrs.get("class", "") + " lv-spinner"

    return _h("div", attrs, "", indent)


@register("line")
def _render_line(w: Widget, indent: int) -> str:
    points = w.get("points", [])
    if not points or not isinstance(points, list):
        points = [0, 0, 100, 0]

    color = _color_to_css(w.get("line_color", "0xFFFFFF"))
    width_val = int(w.get("line_width", 2))

    pts = []
    for i in range(0, len(points) - 1, 2):
        pts.append(str(points[i]) + "," + str(points[i + 1]))
    points_str = " ".join(pts) if pts else "0,0 100,0"

    linecap = ' stroke-linecap="round" stroke-linejoin="round"' if w.get("line_rounded", False) else ""

    max_x, max_y = 200, 50
    nums = [p for p in points if isinstance(p, (int, float))]
    if len(nums) >= 2:
        max_x = max(nums[::2]) + 20 if len(nums[::2]) > 0 else 200
        max_y = max(nums[1::2]) + 20 if len(nums[1::2]) > 0 else 50

    svg = (
        '<svg width="' + str(max_x) + '" height="' + str(max_y) + '" viewBox="0 0 ' + str(max_x) + " " + str(max_y) + '">'
        + '<polyline stroke="' + html.escape(color) + '" stroke-width="' + str(width_val) + '" fill="none"' + linecap
        + ' points="' + html.escape(points_str) + '"/>'
        + '</svg>'
    )

    attrs = _common_attrs(w)
    wrapper_attrs: Dict[str, str] = {"class": "lv-line"}
    style_attr = attrs.get("style", "")
    if style_attr:
        wrapper_attrs["style"] = style_attr

    s1 = _SP * (indent + 1)
    content = "\n" + s1 + svg + "\n" + _SP * indent
    return _h("div", wrapper_attrs, content, indent)
