from __future__ import annotations

import contextvars
import html
import httpx
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from markupsafe import Markup

from app.compat import JINJA_RE
from app.models import Action, Card, Dashboard, Section, View
from app.template_env import register_helpers, render_template

logger = logging.getLogger(__name__)

_SP = "  "
_DEFAULT_SECTION_COLUMNS = 1

RENDERERS: Dict[str, Any] = {}

_DEFAULT_ICONS: Dict[str, str] = {
    "light": "mdi:lightbulb",
    "switch": "mdi:light-switch",
    "fan": "mdi:fan",
    "input_boolean": "mdi:toggle-switch-variant",
    "cover": "mdi:blinds",
    "lock": "mdi:lock",
    "scene": "mdi:palette",
    "script": "mdi:script-text-play",
    "automation": "mdi:robot",
    "sensor": "mdi:thermometer",
    "binary_sensor": "mdi:motion-sensor",
    "climate": "mdi:thermostat",
    "media_player": "mdi:speaker",
    "person": "mdi:account",
    "sun": "mdi:white-balance-sunny",
    "weather": "mdi:weather-partly-cloudy",
    "button": "mdi:button-pointer",
    "input_number": "mdi:numeric",
    "input_select": "mdi:form-dropdown",
    "number": "mdi:numeric",
    "select": "mdi:form-dropdown",
    "timer": "mdi:timer",
    "vacuum": "mdi:robot-vacuum",
    "camera": "mdi:camera",
    "device_tracker": "mdi:cellphone",
    "alarm_control_panel": "mdi:shield-alert",
    "valve": "mdi:valve",
    "water_heater": "mdi:water-boiler",
    "update": "mdi:package-up",
    "siren": "mdi:alarm-light",
    "humidifier": "mdi:water-percent",
}

_entity_icons: Dict[str, str] = {}
_entity_states: Dict[str, Any] = {}
_ha_url: str = ""
_dashboard_name: str = ""
_base_path: str = ""
_via_ingress = contextvars.ContextVar("renderer_via_ingress", default=False)
_icon_svg_cache: Dict[str, str] = {}

_SW_SCRIPT = Markup(
    '<script>'
    'if(navigator.serviceWorker){navigator.serviceWorker.getRegistrations().then(function(r){'
    'for(var i=0;i<r.length;i++){r[i].unregister()}})}'
    '</script>\n'
)


def _url(path: str) -> str:
    if _base_path and _via_ingress.get():
        return _base_path + path
    return path


def register(type_name: str):
    def decorator(fn):
        RENDERERS[type_name] = fn
        return fn
    return decorator


# ── View rendering ───────────────────────────────────────────────────────


def render_view(
    view: View,
    dashboard: Dashboard,
    ha_url: str = "",
    entity_icons: Optional[dict] = None,
    entity_states: Optional[dict] = None,
    dashboard_name: str = "",
) -> str:
    global _entity_icons, _entity_states, _ha_url, _dashboard_name
    _entity_icons = entity_icons or {}
    _entity_states = entity_states or {}
    _ha_url = ha_url or ""
    _dashboard_name = dashboard_name or ""

    _prefetch_icons(view)

    bg = ""
    if view.bg_color:
        bg += f"background-color: {view.bg_color};"
    if view.bg_image:
        img = view.bg_image
        if img.startswith("/api/image/serve/"):
            img = _url("/ha/image/serve/" + img[len("/api/image/serve/"):])
        bg += f"background-image: url('{html.escape(img)}');background-size: cover;background-position: center;"
    if dashboard.lightdash.container_width:
        bg += f"width: {dashboard.lightdash.container_width};"
    if dashboard.lightdash.container_height:
        bg += f"height: {dashboard.lightdash.container_height};overflow-y: auto;"

    needs_uplot = _view_needs_charts(view)
    needs_toggle_sync = _view_needs_toggle_sync(view)
    needs_slider_sync = _view_needs_slider_sync(view)
    needs_clock = _view_needs_clock(view)

    if view.sections:
        cards_html = "\n".join(_render_section(s) for s in view.sections)
    else:
        cards_html = "\n".join(_render_card(c) for c in view.cards)

    ctx = {
        "css_url": _url("/static/style.css"),
        "sw_script": _SW_SCRIPT,
        "title": html.escape(view.title or dashboard.title),
        "path": html.escape(view.path),
        "bg_style": bg,
        "sse_url": _url("/_sse"),
        "cards_html": Markup(cards_html),
        "needs_uplot": needs_uplot,
        "needs_toggle_sync": needs_toggle_sync,
        "needs_slider_sync": needs_slider_sync,
        "needs_clock": needs_clock,
        "state_api_url": _url("/api/state/"),
    }
    return render_template("dashboard_view.html.j2", **ctx)


def _render_section(section: Section) -> str:
    cols = _section_col_count(section)
    cells = []
    for c in section.cards:
        go = c.get("grid_options")
        span_col = 0
        span_row = 0
        if isinstance(go, dict):
            span_col = go.get("columns", 0)
            span_row = go.get("rows", 0)
        if not isinstance(span_col, int):
            span_col = 0
        if not isinstance(span_row, int):
            span_row = 0
        cell_style = ""
        if span_col:
            cell_style += f"grid-column: span {min(span_col, cols)};"
        if span_row and isinstance(span_row, int) and span_row > 1:
            cell_style += f"grid-row: span {span_row};"
        cell_attrs = {"class": "grid-cell"}
        if cell_style:
            cell_attrs["style"] = cell_style
        cells.append({
            "attrs": Markup(_build_attrs(cell_attrs)),
            "content": Markup(_render_card(c)),
        })
    return render_template("section.html.j2", cols=cols, cells=cells)


def _section_col_count(section: Section) -> int:
    max_col = section.columns if section.columns > 0 else 0
    for c in section.cards:
        go = c.get("grid_options")
        if isinstance(go, dict):
            span = go.get("columns", 0)
            if isinstance(span, int) and span > max_col:
                max_col = span
    return max(max_col, _DEFAULT_SECTION_COLUMNS)


def render_view_index(views: List[View], dashboard_name: str = "") -> str:
    links = []
    for v in views:
        href = _url(f"/d/{html.escape(dashboard_name)}/view/{html.escape(v.path)}") if dashboard_name else _url("/view/" + html.escape(v.path))
        links.append({
            "href": href,
            "icon": html.escape(v.icon) if v.icon else "",
            "title": html.escape(v.title or v.path),
        })
    return render_template("view_index.html.j2",
        css_url=_url("/static/style.css"),
        sw_script=_SW_SCRIPT,
        links=links,
    )


def render_dashboard_index(dashboards: List[Dict[str, str]]) -> str:
    links = []
    for d in dashboards:
        name = d.get("url_path", d.get("title", "?"))
        title = d.get("title", name)
        links.append({
            "href": _url("/d/" + html.escape(name)),
            "title": html.escape(title),
            "name": html.escape(name),
        })
    return render_template("dashboard_index.html.j2",
        css_url=_url("/static/style.css"),
        sw_script=_SW_SCRIPT,
        links=links,
    )


def render_error(message: str) -> str:
    return render_template("error.html.j2",
        css_url=_url("/static/style.css"),
        sw_script=_SW_SCRIPT,
        message=html.escape(message),
        home_url=_url("/"),
    )


def _view_needs_charts(view: View) -> bool:
    check_cards = view.cards
    if view.sections:
        check_cards = [c for s in view.sections for c in s.cards]
    for c in check_cards:
        if c.type in ("sensor", "history-graph", "statistics-graph"):
            return True
    return False


def _view_needs_toggle_sync(view: View) -> bool:
    check_cards = view.cards
    if view.sections:
        check_cards = [c for s in view.sections for c in s.cards]
    for c in check_cards:
        if c.type == "tile" and not c.get("hide_state"):
            eid = c.get("entity", "")
            if _is_binary_domain(eid):
                return True
        if c.type == "entities":
            for ent in (c.get("entities") or []):
                eid = ent if isinstance(ent, str) else (ent.get("entity", "") if isinstance(ent, dict) else "")
                if _is_binary_domain(eid) and eid.split(".")[0] != "cover":
                    return True
    return False


def _view_needs_slider_sync(view: View) -> bool:
    check_cards = view.cards
    if view.sections:
        check_cards = [c for s in view.sections for c in s.cards]
    for c in check_cards:
        if c.type == "tile":
            for f in (c.get("features") or []):
                if isinstance(f, dict) and f.get("type") in ("light-brightness", "light-color-temp"):
                    return True
    return False


def _view_needs_clock(view: View) -> bool:
    check_cards = view.cards
    if view.sections:
        check_cards = [c for s in view.sections for c in s.cards]
    for c in check_cards:
        if c.type == "clock":
            return True
    return False


def _render_card(card: Card) -> str:
    renderer = RENDERERS.get(card.type)
    if renderer is None:
        return _render_placeholder(card)
    out = renderer(card)
    if out is None:
        return _render_placeholder(card)
    return out


# ── HTML generation helpers ──────────────────────────────────────────────


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


def _entity_span(entity_id: str, card_id: str = "", indent: int = 0) -> str:
    sid = html.escape(entity_id)
    attrs: Dict[str, str] = {
        "class": "entity-state",
        "id": f"state-{sid}",
        "data-entity": entity_id,
        "hx-get": _url(f"/api/value/{sid}"),
        "hx-trigger": "load",
        "hx-swap": "innerHTML",
    }
    sse_event = "entity_" + entity_id.replace(".", "_")
    attrs["sse-swap"] = sse_event
    return _h("span", attrs, "", indent)


def _prefetch_icons(view: View) -> None:
    needed = set()
    check_cards = view.cards
    if view.sections:
        check_cards = [c for s in view.sections for c in s.cards]
    for c in check_cards:
        eid = c.get("entity", "")
        icon = _entity_icon(eid, c.get("icon", ""))
        if icon:
            needed.add(icon.removeprefix("mdi:"))
        if c.type in ("entities", "glance"):
            for ent in (c.get("entities") or []):
                if isinstance(ent, str):
                    eeid = ent
                    eicon = ""
                elif isinstance(ent, dict):
                    eeid = ent.get("entity", "")
                    eicon = ent.get("icon", "")
                else:
                    continue
                resolved = _entity_icon(eeid, eicon)
                if resolved:
                    needed.add(resolved.removeprefix("mdi:"))
    uncached = [n for n in needed if n not in _icon_svg_cache]
    if not uncached or not _ha_url:
        return
    logger.info("Prefetching %d uncached icons", len(uncached))
    base = "https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/"
    with httpx.Client(timeout=10) as hx:
        for name in uncached:
            try:
                r = hx.get(base + name + ".svg")
                if r.status_code == 200:
                    _icon_svg_cache[name] = r.text
                else:
                    logger.warning("Icon fetch failed %s: HTTP %d", name, r.status_code)
            except Exception as e:
                logger.warning("Icon fetch error %s: %s", name, e)


def _icon_html(icon: str, size: int = 24) -> str:
    if not icon:
        return ""
    name = icon.removeprefix("mdi:")
    svg = _icon_svg_cache.get(name)
    if not svg:
        return ""
    extra = 'class="icon" width="' + str(size) + '" height="' + str(size) + '"'
    if 'fill="currentColor"' not in svg and 'fill="none"' not in svg:
        extra += ' fill="currentColor"'
    svg = svg.replace("<svg", "<svg " + extra, 1)
    return svg


def _entity_icon(entity_id: str, config_icon: str) -> str:
    if config_icon:
        return config_icon
    if entity_id in _entity_icons:
        return _entity_icons[entity_id]
    domain = entity_id.split(".")[0] if "." in entity_id else ""
    return _DEFAULT_ICONS.get(domain, "")


def _js_obj(**kwargs) -> str:
    items = []
    for k, v in kwargs.items():
        if isinstance(v, str):
            items.append(f"{k}: '{v}'")
        elif isinstance(v, (int, float)):
            items.append(f"{k}: {v}")
        elif v is None:
            items.append(f"{k}: null")
        elif isinstance(v, bool):
            items.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (dict, list)):
            items.append(f"{k}: {json.dumps(v)}")
    return "js:{" + ", ".join(items) + "}"


def _tap_action_attrs(card: Card) -> Dict[str, str]:
    raw = card.get("tap_action")
    if not raw or not isinstance(raw, dict):
        return {}
    a = Action(**{k: v for k, v in raw.items() if k in Action.__dataclass_fields__})
    if a.action == "toggle":
        eid = card.get("entity", "")
        domain = eid.split(".")[0] if "." in eid else ""
        svc = _domain_toggle_service(domain)
        return {
            "hx-post": _url("/action"),
            "hx-trigger": "click",
            "hx-vals": _js_obj(entity_id=eid, action="toggle", service=svc),
            "hx-swap": "none",
        }
    if a.action == "call-service":
        target = a.target or {}
        return {
            "hx-post": _url("/action"),
            "hx-trigger": "click",
            "hx-vals": _js_obj(action="call-service", service=a.service, target=target, data=a.data or {}),
            "hx-swap": "none",
        }
    if a.action == "navigate":
        path = _url("/d/" + html.escape(_dashboard_name) + "/view/" + html.escape(a.navigation_path))
        return {"hx-get": path, "hx-target": "body", "hx-push-url": "true", "hx-trigger": "click"}
    if a.action == "url":
        return {"onclick": "window.open('" + html.escape(a.url_path) + "','_blank')"}
    return {}


def _action_attrs(entity_id: str, action: str) -> Dict[str, str]:
    service = ""
    if action == "toggle" and entity_id:
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        service = _domain_toggle_service(domain)
    return {
        "hx-post": _url("/action"),
        "hx-trigger": "click",
        "hx-vals": _js_obj(entity_id=entity_id, action=action, service=service),
        "hx-swap": "none",
    }


def _domain_toggle_service(domain: str) -> str:
    mapping = {
        "light": "light.toggle",
        "switch": "switch.toggle",
        "fan": "fan.toggle",
        "cover": "cover.toggle",
        "lock": "lock.lock",
        "input_boolean": "input_boolean.toggle",
        "scene": "scene.turn_on",
        "script": "script.turn_on",
        "automation": "automation.toggle",
        "climate": "climate.toggle",
        "media_player": "media_player.media_play_pause",
    }
    return mapping.get(domain, domain + ".toggle")


_BINARY_DOMAINS = frozenset({
    "light", "switch", "fan", "input_boolean", "cover",
    "lock", "scene", "script", "automation",
})


def _is_binary_domain(entity_id: str) -> bool:
    domain = entity_id.split(".")[0] if "." in entity_id else ""
    return domain in _BINARY_DOMAINS


def _color_icon(color: str) -> str:
    if not color:
        return ""
    color_map = {
        "yellow": "#FFB300",
        "orange": "#FF6D00",
        "red": "#D32F2F",
        "pink": "#E91E63",
        "purple": "#9C27B0",
        "blue": "#2196F3",
        "green": "#4CAF50",
        "teal": "#009688",
    }
    return color_map.get(color.lower(), color)


# ── Card renderers ───────────────────────────────────────────────────────


@register("placeholder")
def _render_placeholder(card: Card) -> str:
    return render_template("cards/placeholder.html.j2")


@register("heading")
def _render_heading(card: Card) -> str:
    text = html.escape(card.get("heading", ""))
    icon = _icon_html(card.get("icon", ""), 20)
    if icon:
        content = Markup(icon) + '<h2 class="heading-text">' + text + "</h2>"
    else:
        content = '<h2 class="heading-text">' + text + "</h2>"
    return render_template("cards/heading.html.j2",
        icon=Markup(icon),
        text=text,
    )


@register("markdown")
def _render_markdown(card: Card) -> str:
    content = card.get("content", "")
    if JINJA_RE.search(content):
        return _render_placeholder(card)
    rendered = _render_markdown_text(content)
    return render_template("cards/markdown.html.j2",
        content=Markup(rendered),
    )


@register("entity")
def _render_entity(card: Card) -> str:
    eid = card.get("entity", "")
    ctx = {
        "name": html.escape(card.get("name", _friendly_name(eid))),
        "icon": Markup(_icon_html(_entity_icon(eid, card.get("icon", "")), 20)),
        "state_span": Markup(_entity_span(eid)),
        "ta_attrs": Markup(_build_attrs(_tap_action_attrs(card))),
    }
    return render_template("cards/entity.html.j2", **ctx)


@register("entities")
def _render_entities(card: Card) -> str:
    title = html.escape(card.get("title", ""))
    raw_entities = card.get("entities", [])
    rows = []
    for i, ent in enumerate(raw_entities):
        if isinstance(ent, str):
            eid = ent
            ename = _friendly_name(eid)
            eicon = ""
        elif isinstance(ent, dict):
            eid = ent.get("entity", "")
            ename = ent.get("name", _friendly_name(eid))
            eicon = ent.get("icon", "")
        else:
            continue
        type_attr = ent.get("type", "") if isinstance(ent, dict) else ""
        if type_attr == "divider":
            rows.append({"type": "divider"})
            continue
        if type_attr == "section":
            section = html.escape(ent.get("name", "") if isinstance(ent, dict) else "")
            rows.append({"type": "section", "name": section})
            continue
        icon = Markup(_icon_html(_entity_icon(eid, eicon), 18))
        state_span = Markup(_entity_span(eid))
        controls = Markup(_render_cover_controls(eid) or _render_entity_toggle(eid) or "")
        row_attrs: Dict[str, str] = {"class": "entity-row"}
        if _is_binary_domain(eid) and eid.split(".")[0] != "cover":
            dom = eid.split(".")[0]
            svc = _domain_toggle_service(dom)
            row_attrs.update({
                "hx-post": _url("/action"),
                "hx-trigger": "click",
                "hx-vals": _js_obj(entity_id=eid, action="toggle", service=svc),
                "hx-swap": "none",
            })
        rows.append({
            "type": "entity",
            "icon": icon,
            "name": html.escape(ename),
            "state_span": state_span,
            "controls": controls,
            "attrs": Markup(_build_attrs(row_attrs)),
        })
    return render_template("cards/entities.html.j2",
        title=title,
        rows=rows,
    )


@register("glance")
def _render_glance(card: Card) -> str:
    title = html.escape(card.get("title", ""))
    columns = card.get("columns", 3)
    raw_entities = card.get("entities", [])
    items = []
    for ent in raw_entities:
        if isinstance(ent, str):
            eid = ent
            ename = _friendly_name(eid)
            eicon = ""
        elif isinstance(ent, dict):
            eid = ent.get("entity", "")
            ename = ent.get("name", _friendly_name(eid))
            eicon = ent.get("icon", "")
        else:
            continue
        icon = Markup(_icon_html(_entity_icon(eid, eicon), 20))
        state_span = Markup(_entity_span(eid))
        ta_attrs = ""
        if isinstance(ent, dict) and ent.get("tap_action"):
            e_card = Card(type="glance_item", config=ent)
            ta = _tap_action_attrs(e_card)
            ta_attrs = Markup(_build_attrs(ta))
        items.append({
            "icon": icon,
            "name": html.escape(ename),
            "state_span": state_span,
            "attrs": ta_attrs,
        })
    return render_template("cards/glance.html.j2",
        title=title,
        columns=columns,
        items=items,
    )


@register("button")
def _render_button(card: Card) -> str:
    name = html.escape(card.get("name", card.get("entity", "Action")))
    eid = card.get("entity", "")
    icon = Markup(_icon_html(_entity_icon(eid, card.get("icon", "")), 28))
    ta_attrs = _tap_action_attrs(card)
    if not ta_attrs and card.get("entity"):
        ta_attrs = _action_attrs(card.get("entity", ""), "toggle")
    return render_template("cards/button.html.j2",
        name=name,
        icon=icon,
        btn_attrs=Markup(_build_attrs(ta_attrs)),
    )


@register("tile")
def _render_tile(card: Card) -> str:
    eid = card.get("entity", "")
    has_features = bool(card.get("features"))
    features_inline = card.get("features_position", "") == "inline"
    hide_state = card.get("hide_state", False)
    is_binary = _is_binary_domain(eid)
    is_cover = eid.split(".")[0] == "cover" if "." in eid else False

    state_html = ""
    toggle_attrs = {}
    if is_binary and not hide_state and not is_cover:
        dom = eid.split(".")[0] if "." in eid else ""
        svc = _domain_toggle_service(dom)
        toggle_attrs = {
            "hx-post": _url("/action"),
            "hx-trigger": "change",
            "hx-vals": _js_obj(entity_id=eid, action="toggle", service=svc),
            "hx-swap": "none",
        }
        state_html = Markup(
            '<label class="toggle-switch" onclick="event.stopPropagation()">'
            '<input type="checkbox" class="toggle-input" ' + _build_attrs(toggle_attrs) + '>'
            '<span class="toggle-slider"></span>'
            '</label>'
            + _entity_span(eid)
        )
    elif not hide_state:
        state_html = Markup(_entity_span(eid))

    features_html = ""
    inline_features_html = ""
    if has_features:
        features_data = _build_features_data(card)
        features_html = Markup(render_template("partials/features.html.j2", features=features_data, inline=False))
        if features_inline:
            inline_features_html = Markup(render_template("partials/features.html.j2", features=features_data, inline=True))

    cover_html = ""
    if is_cover and not hide_state:
        cover_html = Markup(_render_cover_controls(eid))

    ta_attrs = _tap_action_attrs(card)
    if not ta_attrs and eid and not is_cover:
        ta_attrs = _action_attrs(eid, "toggle")

    ctx = {
        "name": html.escape(card.get("name", _friendly_name(eid))),
        "icon": Markup(_icon_html(_entity_icon(eid, card.get("icon", "")), 24)),
        "color": _color_icon(card.get("color", "")),
        "vertical": card.get("vertical", False),
        "hide_state": hide_state,
        "features_inline": features_inline,
        "is_binary": is_binary,
        "is_cover": is_cover,
        "ta_attrs": Markup(_build_attrs(ta_attrs)),
        "tc_class": "tile-content" + (" vertical" if card.get("vertical") else ""),
        "has_features": has_features,
        "state_html": state_html,
        "features_html": features_html,
        "inline_features": inline_features_html,
        "cover_html": cover_html,
    }
    return render_template("cards/tile.html.j2", **ctx)


def _build_features_data(card: Card) -> list:
    features = card.get("features", [])
    if not features or not isinstance(features, list):
        return []
    result = []
    eid = card.get("entity", "")
    state = _entity_states.get(eid, {})
    for f in features:
        ftype = f.get("type", "") if isinstance(f, dict) else ""
        if ftype == "light-brightness":
            brightness = state.get("attributes", {}).get("brightness", 0) if state.get("state") == "on" else 0
            pct = round(brightness / 255 * 100) if brightness else 0
            result.append({
                "type": "light-brightness",
                "pct": pct,
                "slider_attrs": Markup(_build_attrs({
                    "hx-post": _url("/action"),
                    "hx-trigger": "change",
                    "hx-vals": _js_obj(entity_id=eid, action="call-service", service="light.turn_on", data={}),
                    "hx-vals-js": '{"data": {"brightness_pct": parseInt(event.target.value)}}',
                    "hx-swap": "none",
                })),
            })
        elif ftype == "light-color-temp":
            result.append({
                "type": "light-color-temp",
                "slider_attrs": Markup(_build_attrs({
                    "hx-post": _url("/action"),
                    "hx-trigger": "change",
                    "hx-vals": _js_obj(entity_id=eid, action="call-service", service="light.turn_on", data={}),
                    "hx-vals-js": '{"data": {"color_temp": parseInt(event.target.value)}}',
                    "hx-swap": "none",
                })),
            })
        elif ftype == "numeric-input":
            dec_attrs = {
                "hx-post": _url("/action"),
                "hx-trigger": "click",
                "hx-vals": _js_obj(entity_id=eid, action="call-service", service="input_number.decrement"),
                "hx-swap": "none",
            }
            inc_attrs = {
                "hx-post": _url("/action"),
                "hx-trigger": "click",
                "hx-vals": _js_obj(entity_id=eid, action="call-service", service="input_number.increment"),
                "hx-swap": "none",
            }
            result.append({
                "type": "numeric-input",
                "eid": eid,
                "state_span": Markup(_entity_span(eid)),
                "dec_attrs": Markup(_build_attrs(dec_attrs)),
                "inc_attrs": Markup(_build_attrs(inc_attrs)),
            })
    return result


def _render_cover_controls(entity_id: str) -> str:
    if not entity_id or "." not in entity_id:
        return ""
    dom = entity_id.split(".")[0]
    if dom != "cover":
        return ""
    buttons = []
    for label, svc, aria in [("▲", "cover.open_cover", "Open"), ("⏹", "cover.stop_cover", "Stop"), ("▼", "cover.close_cover", "Close")]:
        buttons.append({
            "label": label,
            "aria": aria,
            "vals": Markup(_js_obj(entity_id=entity_id, action="call-service", service=svc)),
        })
    return render_template("partials/cover_controls.html.j2", buttons=buttons)


def _render_entity_toggle(entity_id: str) -> str:
    if not entity_id or "." not in entity_id:
        return ""
    if not _is_binary_domain(entity_id):
        return ""
    dom = entity_id.split(".")[0]
    if dom == "cover":
        return ""
    svc = _domain_toggle_service(dom)
    toggle_attrs = {
        "hx-post": _url("/action"),
        "hx-trigger": "change",
        "hx-vals": _js_obj(entity_id=entity_id, action="toggle", service=svc),
        "hx-swap": "none",
    }
    return render_template("partials/entity_toggle.html.j2",
        entity_id=entity_id,
        toggle_attrs=Markup(_build_attrs(toggle_attrs)),
    )


@register("grid")
def _render_grid(card: Card) -> str:
    columns = card.get("columns", 2)
    raw_cards = card.get("cards", [])
    children = []
    for c in raw_cards:
        if isinstance(c, dict):
            children.append(Markup(_render_card(Card(type=c.get("type", ""), config={k: v for k, v in c.items() if k != "type"}))))
    return render_template("cards/grid.html.j2",
        columns=columns,
        children=children,
    )


@register("horizontal-stack")
def _render_hstack(card: Card) -> str:
    raw_cards = card.get("cards", [])
    children = []
    for c in raw_cards:
        if isinstance(c, dict):
            children.append(Markup(_render_card(Card(type=c.get("type", ""), config={k: v for k, v in c.items() if k != "type"}))))
    return render_template("cards/hstack.html.j2",
        children=children,
    )


@register("vertical-stack")
def _render_vstack(card: Card) -> str:
    raw_cards = card.get("cards", [])
    children = []
    for c in raw_cards:
        if isinstance(c, dict):
            children.append(Markup(_render_card(Card(type=c.get("type", ""), config={k: v for k, v in c.items() if k != "type"}))))
    return render_template("cards/vstack.html.j2",
        children=children,
    )


@register("conditional")
def _render_conditional(card: Card) -> str:
    conditions = card.get("conditions", [])
    raw_card = card.get("card", {})
    if not isinstance(raw_card, dict):
        return _render_placeholder(card)
    child = Markup(_render_card(Card(type=raw_card.get("type", ""), config={k: v for k, v in raw_card.items() if k != "type"})))
    cond_json = html.escape(json.dumps(conditions))
    cond_id = "cond-" + str(hash(json.dumps(conditions, sort_keys=True)) & 0xFFFFFFFF)
    return render_template("cards/conditional.html.j2",
        cond_id=cond_id,
        conditions_json=cond_json,
        child=child,
    )


@register("light")
def _render_light(card: Card) -> str:
    eid = card.get("entity", "")
    ctx = {
        "name": html.escape(card.get("name", _friendly_name(eid))),
        "icon": Markup(_icon_html(_entity_icon(eid, card.get("icon", "")), 24)),
        "state_span": Markup(_entity_span(eid)),
        "toggle_attrs": Markup(_build_attrs(_action_attrs(eid, "toggle"))),
        "slider_attrs": Markup(_build_attrs({
            "hx-post": _url("/action"),
            "hx-trigger": "change",
            "hx-vals": _js_obj(entity_id=eid, action="call-service", service="light.turn_on", data={}),
            "hx-vals-js": '{"data": {"brightness_pct": parseInt(event.target.value)}}',
            "hx-swap": "none",
        })),
    }
    return render_template("cards/light.html.j2", **ctx)


@register("sensor")
def _render_sensor(card: Card) -> str:
    eid = card.get("entity", "")
    graph_type = card.get("graph", "")
    hours = card.get("hours_to_show", 24)
    ctx = {
        "eid": eid,
        "name": html.escape(card.get("name", _friendly_name(eid))),
        "icon": Markup(_icon_html(_entity_icon(eid, card.get("icon", "")), 20)),
        "state_span": Markup(_entity_span(eid)),
        "graph": {"type": graph_type, "hours": hours} if graph_type else None,
    }
    return render_template("cards/sensor.html.j2", **ctx)


@register("history-graph")
def _render_history_graph(card: Card) -> str:
    title = html.escape(card.get("title", ""))
    raw_entities = card.get("entities", [])
    hours = card.get("hours_to_show", 24)
    eids = []
    for ent in raw_entities:
        if isinstance(ent, str):
            eids.append(ent)
        elif isinstance(ent, dict):
            eids.append(ent.get("entity", ""))
    chart_data = html.escape(json.dumps({"entities": eids, "hours": hours}))
    return render_template("cards/history_graph.html.j2",
        title=title,
        chart_data=chart_data,
    )


@register("gauge")
def _render_gauge(card: Card) -> str:
    eid = card.get("entity", "")
    name = html.escape(card.get("name", _friendly_name(eid)))
    min_v = card.get("min", 0)
    max_v = card.get("max", 100)
    severity = card.get("severity", {})
    severity_json = html.escape(json.dumps(severity)) if severity else ""
    ctx = {
        "name": name,
        "state_span": Markup(_entity_span(eid)),
        "min": str(min_v),
        "max": str(max_v),
        "severity": severity_json,
    }
    return render_template("cards/gauge.html.j2", **ctx)


@register("iframe")
def _render_iframe(card: Card) -> str:
    url = html.escape(card.get("url", ""))
    aspect = card.get("aspect_ratio", "50%")
    return render_template("cards/iframe.html.j2",
        url=url,
        aspect_ratio=html.escape(str(aspect)),
    )


@register("clock")
def _render_clock(card: Card) -> str:
    tz = card.get("time_zone", "Europe/London")
    fmt = card.get("time_format", "24")
    sec = card.get("show_seconds", False)
    size = card.get("clock_size", "medium")
    no_bg = card.get("no_background", False)
    size_class = f"clock-size-{size}"
    clock_id = f"c{abs(hash(tz+fmt+str(sec)))%99999999}"
    return render_template("cards/clock.html.j2",
        tz=tz,
        fmt=fmt,
        sec=sec,
        size_class=size_class,
        no_bg=no_bg,
        clock_id=clock_id,
    )


# ── Markdown renderer ────────────────────────────────────────────────────


def _render_markdown_text(text: str) -> str:
    lines = text.split("\n")
    html_out = ""
    in_list = False
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            html_out += f"<h{level}>{_inline_md(m.group(2))}</h{level}>\n"
            continue
        m = re.match(r"^[\-\*]\s+(.+)$", line)
        if m:
            if not in_list:
                html_out += "<ul>\n"
                in_list = True
            html_out += "<li>" + _inline_md(m.group(1)) + "</li>\n"
            continue
        if in_list:
            html_out += "</ul>\n"
            in_list = False
        if not line.strip():
            continue
        m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if m:
            html_out += "<p>" + _inline_md(m.group(2)) + "</p>\n"
            continue
        html_out += "<p>" + _inline_md(line) + "</p>\n"
    if in_list:
        html_out += "</ul>\n"

    html_out = html_out.replace("&", "&amp;")
    html_out = html_out.replace("<strong>", "\x00strong\x00")
    html_out = html_out.replace("</strong>", "\x01strong\x01")
    html_out = html_out.replace("<em>", "\x00em\x00")
    html_out = html_out.replace("</em>", "\x01em\x01")
    html_out = html_out.replace("<code>", "\x00code\x00")
    html_out = html_out.replace("</code>", "\x01code\x01")
    html_out = html_out.replace("<a ", "\x00a\x00")
    html_out = html_out.replace("</a>", "\x01a\x01")
    html_out = html_out.replace("<", "&lt;").replace(">", "&gt;")
    html_out = html_out.replace("\x00strong\x00", "<strong>")
    html_out = html_out.replace("\x01strong\x01", "</strong>")
    html_out = html_out.replace("\x00em\x00", "<em>")
    html_out = html_out.replace("\x01em\x01", "</em>")
    html_out = html_out.replace("\x00code\x00", "<code>")
    html_out = html_out.replace("\x01code\x01", "</code>")
    html_out = html_out.replace("\x00a\x00", "<a ")
    html_out = html_out.replace("\x01a\x01", "</a>")

    return html_out


def _inline_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" target="_blank">\1</a>', text)
    return text


def _friendly_name(entity_id: str) -> str:
    parts = entity_id.split(".")
    if len(parts) < 2:
        return entity_id
    raw = parts[1].replace("_", " ").replace("-", " ")
    return raw.title()


# ── Register Jinja2 globals ─────────────────────────────────────────────


register_helpers({
    "url": _url,
    "build_attrs": lambda d: Markup(_build_attrs(d)),
    "entity_span": lambda e, c="", i=0: Markup(_entity_span(e, c, i)),
    "icon_html": lambda i, s=24: Markup(_icon_html(i, s)),
    "entity_icon": _entity_icon,
    "friendly_name": _friendly_name,
    "is_binary": _is_binary_domain,
    "toggle_service": _domain_toggle_service,
    "color_icon": _color_icon,
    "js_obj": lambda **kw: Markup(_js_obj(**kw)),
    "tap_action_attrs": _tap_action_attrs,
    "action_attrs": _action_attrs,
    "sw_script": _SW_SCRIPT,
    "html_escape": html.escape,
    "_DEFAULT_ICONS": _DEFAULT_ICONS,
})
