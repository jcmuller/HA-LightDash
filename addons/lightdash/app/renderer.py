from __future__ import annotations

import contextvars
import html
import httpx
import json
import logging
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from app.compat import JINJA_RE
from app.models import Action, Card, Dashboard, Section, View

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
_icon_svg_cache: Dict[str, str] = OrderedDict()
_ICON_CACHE_MAX = 200

_SW_SCRIPT = (
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


def render_view(view: View, dashboard: Dashboard, ha_url: str = "", entity_icons: Optional[dict] = None, entity_states: Optional[dict] = None, dashboard_name: str = "") -> str:
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

    if view.sections:
        cards_html = "\n".join(_render_section(s, 2) for s in view.sections)
    else:
        cards_html = "\n".join(_render_card(c, 2) for c in view.cards)

    title = html.escape(view.title or dashboard.title)
    path = html.escape(view.path)

    head_extra = ""
    if needs_uplot:
        head_extra += (
            '<script src="https://cdn.jsdelivr.net/npm/uplot@1.6.31/dist/uPlot.iife.min.js"></script>\n'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uplot@1.6.31/dist/uPlot.min.css">\n'
        )
    if _view_needs_toggle_sync(view):
        head_extra += (
            '<script>\n'
            'function st(){'
            'document.querySelectorAll(".tile-card").forEach(function(e){'
            'var s=e.querySelector(".entity-state"),t=e.querySelector(".toggle-input");'
            'if(s&&t){var o=s.textContent.trim()==="on";t.checked=o;e.classList.toggle("entity-on",o);e.classList.toggle("entity-off",!o);}'
            '});'
            'document.querySelectorAll(".entities-card .entity-row").forEach(function(e){'
            'var s=e.querySelector(".entity-state"),t=e.querySelector(".toggle-input");'
            'if(s&&t){var o=s.textContent.trim()==="on";t.checked=o;e.classList.toggle("entity-on",o);e.classList.toggle("entity-off",!o);}'
            '});}\n'
             'document.addEventListener("htmx:afterSwap",st);\n'
             'document.addEventListener("htmx:sseMessage",st);\n'
             'document.addEventListener("change",function(e){'
             'var i=e.target;'
             'if(!i.classList.contains("toggle-input"))return;'
             'var on=i.checked;'
             'var c=i.closest(".tile-card,.entity-row");'
             'if(c){c.classList.toggle("entity-on",on);c.classList.toggle("entity-off",!on);}'
             'var s=c&&c.querySelector(".entity-state");'
             'if(s){var t=s.textContent.trim().toLowerCase();if(t==="on"||t==="off")s.textContent=on?"on":"off";}'
             '});\n'
             '</script>\n'
        )
    if _view_needs_slider_sync(view):
        state_api_url = _url("/api/state/")
        head_extra += (
            '<script>\n'
            'function ss(e){'
            'var s=e.detail.elt;'
            'if(!s||!s.classList.contains("entity-state"))return;'
            'var c=s.closest(".tile-card");'
            'if(!c)return;'
            'var r=c.querySelector(".feature-slider");'
            'if(!r)return;'
            'var eid=s.getAttribute("data-entity");'
            'if(!eid)return;'
            "fetch('" + state_api_url + "'+eid).then(function(resp){return resp.json()}).then(function(d){"
            'if(d&&d.attributes&&d.attributes.brightness){r.value=Math.round(d.attributes.brightness/255*100);}'
            '});'
            '}\n'
            'document.addEventListener("htmx:sseMessage",ss);\n'
            '</script>\n'
        )
    if _view_needs_clock(view):
        head_extra += (
            '<script>\n'
            'function uc(){document.querySelectorAll(".clock-digital").forEach('
            'function(e){var o={hour:"2-digit",minute:"2-digit",'
            'timeZone:e.getAttribute("data-tz")||"Europe/London",'
            'hour12:e.getAttribute("data-fmt")!=="24"};'
            'if(e.getAttribute("data-sec"))o.second="2-digit";'
            'e.textContent=(new Intl.DateTimeFormat("en-GB",o)).format(new Date())})}\n'
             'setInterval(uc,30000);\n'
             'document.addEventListener("DOMContentLoaded",uc);\n'
             'document.addEventListener("htmx:afterSwap",uc);\n'
             '</script>\n'
        )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">\n'
        '<title>' + title + '</title>\n'
        '<link rel="stylesheet" href="' + _url("/static/style.css") + '">\n'
        '<script src="https://unpkg.com/htmx.org@2.0.4"></script>\n'
        '<script src="https://unpkg.com/htmx-ext-sse@2.2.4/dist/sse.js"></script>\n'
        + _SW_SCRIPT
        + head_extra +
        '</head>\n'
        '<body>\n'
        '<div class="lv-view" id="view-' + path + '" hx-ext="sse" sse-connect="' + _url("/_sse") + '" style="' + bg + '">\n'
        + cards_html + '\n'
        '</div>\n'
        '</body>\n'
        '</html>'
    )


def _render_section(section: Section, indent: int = 2) -> str:
    cols = _section_col_count(section)
    style = f"--section-cols: {cols}"
    cards_html = ""
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
        card_content = _render_card(c, indent + 1)
        cards_html += "\n" + _SP * (indent + 1) + f'<div{_build_attrs(cell_attrs)}>\n'
        cards_html += card_content
        cards_html += '\n' + _SP * (indent + 1) + '</div>'
    if cards_html:
        cards_html += "\n" + _SP * indent
    return _h("div", {"class": "section-grid", "style": style}, cards_html, indent)


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
    links = ""
    for v in views:
        href = _url(f"/d/{html.escape(dashboard_name)}/view/{html.escape(v.path)}") if dashboard_name else _url("/view/" + html.escape(v.path))
        links += '    <li><a href="' + href + '">'
        if v.icon:
            links += '<span class="vi">' + html.escape(v.icon) + "</span> "
        links += html.escape(v.title or v.path) + "</a></li>\n"
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        '<title>LightDash</title>\n'
        '<link rel="stylesheet" href="' + _url("/static/style.css") + '">\n'
        + _SW_SCRIPT +
        '</head>\n'
        '<body>\n'
        '<div class="view-index">\n'
        '<h1>LightDash</h1>\n'
        '<ul>\n'
        + links +
        '</ul>\n'
        '</div>\n'
        '</body>\n'
        '</html>'
    )


def render_dashboard_index(dashboards: List[Dict[str, str]]) -> str:
    links = ""
    for d in dashboards:
        name = d.get("url_path", d.get("title", "?"))
        title = d.get("title", name)
        href = _url("/d/" + html.escape(name))
        links += '    <li><a href="' + href + '">' + html.escape(title) + " (" + html.escape(name) + ")</a></li>\n"
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        '<title>LightDash</title>\n'
        '<link rel="stylesheet" href="' + _url("/static/style.css") + '">\n'
        + _SW_SCRIPT +
        '</head>\n'
        '<body>\n'
        '<div class="view-index">\n'
        '<h1>LightDash</h1>\n'
        '<p>Select a dashboard:</p>\n'
        '<ul>\n'
        + links +
        '</ul>\n'
        '</div>\n'
        '</body>\n'
        '</html>'
    )


def render_error(message: str) -> str:
    msg = html.escape(message)
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        '<title>LightDash - Error</title>\n'
        '<link rel="stylesheet" href="' + _url("/static/style.css") + '">\n'
        + _SW_SCRIPT +
        '</head>\n'
        '<body>\n'
        '<div class="view-index">\n'
        '<h1>LightDash</h1>\n'
        '<div class="error-card" style="background:#3a1a1a;border:1px solid #c44;padding:20px;border-radius:8px;color:#f88">'
        + msg +
        '</div>\n'
        '<p><a href="' + _url("/") + '" style="color:#88f">Back to dashboards</a></p>\n'
        '</div>\n'
        '</body>\n'
        '</html>'
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


def _render_card(card: Card, indent: int = 2) -> str:
    renderer = RENDERERS.get(card.type)
    if renderer is None:
        return _render_placeholder(card, indent)
    out = renderer(card, indent)
    if out is None:
        return _render_placeholder(card, indent)
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


def _format_entity_state(entity_id: str) -> Optional[str]:
    state = _entity_states.get(entity_id)
    if not state:
        return None
    val = state.get("state", "")
    unit = state.get("attributes", {}).get("unit_of_measurement", "")
    return f"{val} {unit}" if unit else str(val)


def _entity_span(entity_id: str, card_id: str = "", indent: int = 0) -> str:
    sid = html.escape(entity_id)
    display = _format_entity_state(entity_id)
    attrs: Dict[str, str] = {
        "class": "entity-state",
        "id": f"state-{sid}",
        "data-entity": entity_id,
    }
    if display is None:
        attrs["hx-get"] = _url(f"/api/value/{sid}")
        attrs["hx-trigger"] = "load"
        attrs["hx-swap"] = "innerHTML"
    sse_event = "entity_" + entity_id.replace(".", "_")
    attrs["sse-swap"] = sse_event
    return _h("span", attrs, html.escape(display) if display is not None else "", indent)


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
    while len(_icon_svg_cache) > _ICON_CACHE_MAX:
        _icon_svg_cache.pop(next(iter(_icon_svg_cache)), None)


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


# ---- Card Renderers -------------------------------------------------------


@register("placeholder")
def _render_placeholder(card: Card, indent: int = 2) -> str:
    return _h("div", {"class": "ha-card placeholder-card"}, "?", indent)


@register("heading")
def _render_heading(card: Card, indent: int = 2) -> str:
    text = html.escape(card.get("heading", ""))
    icon = _icon_html(card.get("icon", ""), 20)
    content = icon + '<h2 class="heading-text">' + text + "</h2>" if icon else '<h2 class="heading-text">' + text + "</h2>"
    return _h("div", {"class": "heading-card"}, content, indent)


@register("markdown")
def _render_markdown(card: Card, indent: int = 2) -> str:
    content = card.get("content", "")
    if JINJA_RE.search(content):
        return _render_placeholder(card, indent)
    rendered = _render_markdown_text(content)
    return _h("div", {"class": "ha-card markdown-card"}, rendered, indent)


@register("entity")
def _render_entity(card: Card, indent: int = 2) -> str:
    eid = card.get("entity", "")
    name = html.escape(card.get("name", _friendly_name(eid)))
    icon = _icon_html(_entity_icon(eid, card.get("icon", "")), 20)
    state_span = _entity_span(eid, indent=indent + 2)
    icon_cell = '<div class="entity-icon">' + icon + "</div>" if icon else ""
    attrs = {"class": "ha-card entity-card"}
    ta = _tap_action_attrs(card)
    attrs.update(ta)
    content = (
        '\n' + _SP * (indent + 1) + '<div class="entity-row">\n'
        + _SP * (indent + 2) + icon_cell + '\n'
        + _SP * (indent + 2) + '<div class="entity-info">\n'
        + _SP * (indent + 3) + '<div class="entity-name">' + name + '</div>\n'
        + _SP * (indent + 3) + state_span + '\n'
        + _SP * (indent + 2) + '</div>\n'
        + _SP * (indent + 1) + '</div>\n'
        + _SP * indent
    )
    return _h("div", attrs, content, indent)


@register("entities")
def _render_entities(card: Card, indent: int = 2) -> str:
    title = html.escape(card.get("title", ""))
    raw_entities = card.get("entities", [])
    rows = ""
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
        icon = _icon_html(_entity_icon(eid, eicon), 18)
        state_span = _entity_span(eid, indent=indent + 3)
        type_attr = ent.get("type", "") if isinstance(ent, dict) else ""
        divider = ""
        if type_attr == "divider":
            rows += _SP * (indent + 1) + '<hr class="entities-divider">\n'
            continue
        if type_attr == "section":
            section = html.escape(ent.get("name", "") if isinstance(ent, dict) else "")
            rows += _SP * (indent + 1) + '<div class="entities-section-header">' + section + '</div>\n'
            continue
        row_controls = _render_cover_controls(eid, indent + 2) or _render_entity_toggle(eid, indent + 2)
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
        rows += (
            _SP * (indent + 1) + '<div' + _build_attrs(row_attrs) + '>\n'
            + _SP * (indent + 2) + '<div class="entity-icon">' + icon + '</div>\n'
            + _SP * (indent + 2) + '<div class="entity-info">\n'
            + _SP * (indent + 3) + '<div class="entity-name">' + html.escape(ename) + '</div>\n'
            + _SP * (indent + 3) + state_span + '\n'
            + _SP * (indent + 2) + '</div>\n'
            + row_controls
            + _SP * (indent + 1) + '</div>\n'
        )

    header = ""
    if title:
        header = _SP * (indent + 1) + '<div class="entities-header">' + title + '</div>\n'

    content = "\n" + header + rows + _SP * indent
    return _h("div", {"class": "ha-card entities-card"}, content, indent)


@register("glance")
def _render_glance(card: Card, indent: int = 2) -> str:
    title = html.escape(card.get("title", ""))
    columns = card.get("columns", 3)
    raw_entities = card.get("entities", [])
    items = ""
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
        icon = _icon_html(_entity_icon(eid, eicon), 20)
        state_span = _entity_span(eid, indent=indent + 3)
        ta_attrs = ""
        if isinstance(ent, dict) and ent.get("tap_action"):
            e_card = Card(type="glance_item", config=ent)
            ta = _tap_action_attrs(e_card)
            ta_attrs = _build_attrs(ta)
        items += (
            _SP * (indent + 1) + '<div class="glance-item"' + ta_attrs + '>\n'
            + _SP * (indent + 2) + '<div class="glance-icon">' + icon + '</div>\n'
            + _SP * (indent + 2) + '<div class="glance-name">' + html.escape(ename) + '</div>\n'
            + _SP * (indent + 2) + state_span + '\n'
            + _SP * (indent + 1) + '</div>\n'
        )

    header = ""
    if title:
        header = _SP * (indent + 1) + '<div class="glance-header">' + title + '</div>\n'

    content = "\n" + header + items + _SP * indent
    return _h("div", {"class": "ha-card glance-card", "style": "--cols: " + str(columns)}, content, indent)


@register("button")
def _render_button(card: Card, indent: int = 2) -> str:
    name = html.escape(card.get("name", card.get("entity", "Action")))
    eid = card.get("entity", "")
    icon = _icon_html(_entity_icon(eid, card.get("icon", "")), 28)
    ta_attrs = _tap_action_attrs(card)

    if not ta_attrs and card.get("entity"):
        ta_attrs = _action_attrs(card.get("entity", ""), "toggle")

    content = (
        '\n' + _SP * (indent + 1) + '<button class="button-content"' + _build_attrs(ta_attrs) + '>\n'
        + _SP * (indent + 2) + '<div class="button-icon">' + icon + '</div>\n'
        + _SP * (indent + 2) + '<div class="button-name">' + name + '</div>\n'
        + _SP * (indent + 1) + '</button>\n'
        + _SP * indent
    )
    return _h("div", {"class": "ha-card button-card"}, content, indent)


@register("tile")
def _render_tile(card: Card, indent: int = 2) -> str:
    eid = card.get("entity", "")
    name = html.escape(card.get("name", _friendly_name(eid)))
    icon = _icon_html(_entity_icon(eid, card.get("icon", "")), 24)
    color = _color_icon(card.get("color", ""))
    vertical = card.get("vertical", False)
    hide_state = card.get("hide_state", False)
    features_inline = card.get("features_position", "") == "inline"

    attrs: Dict[str, str] = {"class": "ha-card tile-card"}
    if color:
        attrs["style"] = "--tile-color: " + color

    is_binary = _is_binary_domain(eid)
    is_cover = eid.split(".")[0] == "cover" if "." in eid else False
    state_html = ""
    if is_binary and not hide_state and not is_cover:
        dom = eid.split(".")[0] if "." in eid else ""
        svc = _domain_toggle_service(dom)
        toggle_attrs = {
            "hx-post": _url("/action"),
            "hx-trigger": "change",
            "hx-vals": _js_obj(entity_id=eid, action="toggle", service=svc),
            "hx-swap": "none",
        }
        state_html = (
            '<label class="toggle-switch" onclick="event.stopPropagation()">'
            '<input type="checkbox" class="toggle-input" ' + _build_attrs(toggle_attrs) + '>'
            '<span class="toggle-slider"></span>'
            '</label>'
            + _entity_span(eid, indent=indent + 2)
        )
    elif is_cover and not hide_state:
        state_html = _entity_span(eid, indent=indent + 2)
    elif not hide_state:
        state_html = _entity_span(eid, indent=indent + 2)

    ta_attrs = _tap_action_attrs(card)

    if not ta_attrs and eid and not is_cover:
        ta_attrs = _action_attrs(eid, "toggle")

    tc_class = "tile-content" + (" vertical" if vertical else "")

    has_features = bool(card.get("features"))
    features_html = ""
    if has_features:
        features_html = "\n" + _render_features(card, indent + 1) + "\n" + _SP * indent

    if features_inline and has_features:
        inline_html = _render_features(card, indent + 3, inline=True)
        content = (
            '\n'
            + _SP * (indent + 1) + '<div class="' + tc_class + '"' + _build_attrs(ta_attrs) + '>\n'
            + _SP * (indent + 2) + '<div class="tile-icon">' + icon + '</div>\n'
            + _SP * (indent + 2) + '<div class="tile-info tile-info-inline">\n'
            + _SP * (indent + 3) + '<div class="tile-name">' + name + '</div>\n'
            + inline_html + '\n'
            + _SP * (indent + 2) + '</div>\n'
            + _SP * (indent + 1) + '</div>\n'
            + _SP * indent
        )
    elif is_cover and not hide_state:
        cover_html = _render_cover_controls(eid, indent + 3)
        content = (
            '\n'
            + _SP * (indent + 1) + '<div class="' + tc_class + '"' + _build_attrs(ta_attrs) + '>\n'
            + _SP * (indent + 2) + '<div class="tile-icon">' + icon + '</div>\n'
            + _SP * (indent + 2) + '<div class="tile-info tile-info-inline">\n'
            + _SP * (indent + 3) + '<div class="tile-name">' + name + '</div>\n'
            + _SP * (indent + 3) + state_html + '\n'
            + cover_html + '\n'
            + _SP * (indent + 2) + '</div>\n'
            + _SP * (indent + 1) + '</div>\n'
            + _SP * indent
        )
    else:
        content = (
            '\n'
            + _SP * (indent + 1) + '<div class="' + tc_class + '"' + _build_attrs(ta_attrs) + '>\n'
            + _SP * (indent + 2) + '<div class="tile-icon">' + icon + '</div>\n'
            + _SP * (indent + 2) + '<div class="tile-info">\n'
            + _SP * (indent + 3) + '<div class="tile-name">' + name + '</div>\n'
            + _SP * (indent + 3) + state_html + '\n'
            + _SP * (indent + 2) + '</div>\n'
            + _SP * (indent + 1) + '</div>\n'
            + features_html
            + _SP * indent
        )
    return _h("div", attrs, content, indent)


def _render_features(card: Card, indent: int, inline: bool = False) -> str:
    features = card.get("features", [])
    if not features or not isinstance(features, list):
        return ""
    if inline:
        html_out = ""
    else:
        html_out = _SP * indent + '<div class="tile-features">\n'
    for f in features:
        ftype = f.get("type", "")
        if ftype == "light-brightness":
            eid = card.get("entity", "")
            state = _entity_states.get(eid, {})
            brightness = state.get("attributes", {}).get("brightness", 0) if state.get("state") == "on" else 0
            pct = round(brightness / 255 * 100) if brightness else 0
            slider_attrs = {
                "type": "range",
                "class": "feature-slider",
                "min": "0",
                "max": "100",
                "value": str(pct),
                "hx-post": _url("/action"),
                "hx-trigger": "change",
                "hx-vals": _js_obj(entity_id=eid, action="call-service", service="light.turn_on", data={}),
                "hx-vals-js": '{"data": {"brightness_pct": parseInt(event.target.value)}}',
                "hx-swap": "none",
            }
            label = ""
            if not inline:
                label = _SP * (indent + 2) + '<span class="feature-label">Brightness</span>\n'
            html_out += (
                _SP * (indent + 1) + '<div class="feature-row">\n'
                + label
                + _SP * (indent + 2) + '<input ' + _build_attrs(slider_attrs) + '>\n'
                + _SP * (indent + 1) + '</div>\n'
            )
        elif ftype == "light-color-temp":
            eid = card.get("entity", "")
            html_out += (
                _SP * (indent + 1) + '<div class="feature-row">\n'
                + _SP * (indent + 2) + '<span class="feature-label">Color Temp</span>\n'
                + _SP * (indent + 2) + '<input type="range" class="feature-slider" min="153" max="500" '
                + _build_attrs({
                    "hx-post": _url("/action"),
                    "hx-trigger": "change",
                    "hx-vals": _js_obj(entity_id=eid, action="call-service", service="light.turn_on", data={}),
                    "hx-vals-js": '{"data": {"color_temp": parseInt(event.target.value)}}',
                    "hx-swap": "none",
                }) + '>\n'
                + _SP * (indent + 1) + '</div>\n'
            )
        elif ftype == "numeric-input":
            eid = card.get("entity", "")
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
            html_out += (
                _SP * (indent + 1) + '<div class="feature-row">\n'
                + _SP * (indent + 2) + '<div class="numeric-input">\n'
                + _SP * (indent + 3) + _h("button", {"class": "num-btn", "aria-label": "Decrement", **dec_attrs}, "−") + '\n'
                + _SP * (indent + 3) + _entity_span(eid, indent=indent + 3) + '\n'
                + _SP * (indent + 3) + _h("button", {"class": "num-btn", "aria-label": "Increment", **inc_attrs}, "+") + '\n'
                + _SP * (indent + 2) + '</div>\n'
                + _SP * (indent + 1) + '</div>\n'
            )
    if not inline:
        html_out += _SP * indent + "</div>\n"
    return html_out


def _render_cover_controls(entity_id: str, indent: int) -> str:
    if not entity_id or "." not in entity_id:
        return ""
    dom = entity_id.split(".")[0]
    if dom != "cover":
        return ""
    eid = html.escape(entity_id)
    html_out = _SP * indent + '<div class="cover-controls">\n'
    for label, svc, aria in [("▲", "cover.open_cover", "Open"), ("⏹", "cover.stop_cover", "Stop"), ("▼", "cover.close_cover", "Close")]:
        attrs = {
            "hx-post": _url("/action"),
            "hx-trigger": "click",
            "hx-vals": _js_obj(entity_id=entity_id, action="call-service", service=svc),
            "hx-swap": "none",
            "class": "cover-btn",
            "aria-label": aria,
        }
        html_out += _SP * (indent + 1) + _h("button", attrs, label, 0) + "\n"
    html_out += _SP * indent + "</div>\n"
    return html_out


def _render_entity_toggle(entity_id: str, indent: int) -> str:
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
    html_out = _SP * indent + '<div class="entity-toggle" onclick="event.stopPropagation()">\n'
    html_out += _SP * (indent + 1) + '<label class="toggle-switch">\n'
    html_out += _SP * (indent + 2) + '<input type="checkbox" class="toggle-input" ' + _build_attrs(toggle_attrs) + '>\n'
    html_out += _SP * (indent + 2) + '<span class="toggle-slider"></span>\n'
    html_out += _SP * (indent + 1) + '</label>\n'
    html_out += _SP * indent + '</div>\n'
    return html_out


@register("grid")
def _render_grid(card: Card, indent: int = 2) -> str:
    columns = card.get("columns", 2)
    raw_cards = card.get("cards", [])
    children = ""
    for c in raw_cards:
        if isinstance(c, dict):
            children += "\n" + _render_card(Card(type=c.get("type", ""), config={k: v for k, v in c.items() if k != "type"}), indent + 1)
    if children:
        children += "\n" + _SP * indent
    return _h("div", {"class": "ha-card grid-card", "style": "--cols: " + str(columns)}, children, indent)


@register("horizontal-stack")
def _render_hstack(card: Card, indent: int = 2) -> str:
    raw_cards = card.get("cards", [])
    children = ""
    for c in raw_cards:
        if isinstance(c, dict):
            children += "\n" + _render_card(Card(type=c.get("type", ""), config={k: v for k, v in c.items() if k != "type"}), indent + 1)
    if children:
        children += "\n" + _SP * indent
    return _h("div", {"class": "ha-card hstack-card"}, children, indent)


@register("vertical-stack")
def _render_vstack(card: Card, indent: int = 2) -> str:
    raw_cards = card.get("cards", [])
    children = ""
    for c in raw_cards:
        if isinstance(c, dict):
            children += "\n" + _render_card(Card(type=c.get("type", ""), config={k: v for k, v in c.items() if k != "type"}), indent + 1)
    if children:
        children += "\n" + _SP * indent
    return _h("div", {"class": "ha-card vstack-card"}, children, indent)


@register("conditional")
def _render_conditional(card: Card, indent: int = 2) -> str:
    conditions = card.get("conditions", [])
    raw_card = card.get("card", {})
    if not isinstance(raw_card, dict):
        return _render_placeholder(card, indent)

    child = _render_card(Card(type=raw_card.get("type", ""), config={k: v for k, v in raw_card.items() if k != "type"}), indent + 1)

    cond_json = html.escape(json.dumps(conditions))
    cond_id = "cond-" + str(hash(json.dumps(conditions, sort_keys=True)) & 0xFFFFFFFF)

    attrs = {
        "class": "conditional-card",
        "id": cond_id,
        "data-conditions": cond_json,
    }

    content = "\n" + _SP * (indent + 1) + child + "\n" + _SP * indent
    return _h("div", attrs, content, indent)


@register("light")
def _render_light(card: Card, indent: int = 2) -> str:
    eid = card.get("entity", "")
    name = html.escape(card.get("name", _friendly_name(eid)))
    icon = _icon_html(_entity_icon(eid, card.get("icon", "")), 24)
    state_span = _entity_span(eid, indent=indent + 2)

    toggle_attrs = _action_attrs(eid, "toggle")

    content = (
        '\n'
        + _SP * (indent + 1) + '<div class="light-content">\n'
        + _SP * (indent + 2) + '<div class="light-icon"' + _build_attrs(toggle_attrs) + '>' + icon + '</div>\n'
        + _SP * (indent + 2) + '<div class="light-info">\n'
        + _SP * (indent + 3) + '<div class="light-name">' + name + '</div>\n'
        + _SP * (indent + 3) + state_span + '\n'
        + _SP * (indent + 2) + '</div>\n'
        + _SP * (indent + 2) + '<input type="range" class="light-slider" min="0" max="100" value="0" '
        + _build_attrs({
            "hx-post": _url("/action"),
            "hx-trigger": "change",
            "hx-vals": _js_obj(entity_id=eid, action="call-service", service="light.turn_on", data={}),
            "hx-vals-js": '{"data": {"brightness_pct": parseInt(event.target.value)}}',
            "hx-swap": "none",
        }) + '>\n'
        + _SP * (indent + 1) + '</div>\n'
        + _SP * indent
    )
    return _h("div", {"class": "ha-card light-card"}, content, indent)


@register("sensor")
def _render_sensor(card: Card, indent: int = 2) -> str:
    eid = card.get("entity", "")
    name = html.escape(card.get("name", _friendly_name(eid)))
    icon = _icon_html(_entity_icon(eid, card.get("icon", "")), 20)
    state_span = _entity_span(eid, indent=indent + 2)
    graph_type = card.get("graph", "")

    content = (
        '\n'
        + _SP * (indent + 1) + '<div class="sensor-content">\n'
        + _SP * (indent + 2) + '<div class="sensor-icon">' + icon + '</div>\n'
        + _SP * (indent + 2) + '<div class="sensor-info">\n'
        + _SP * (indent + 3) + '<div class="sensor-name">' + name + '</div>\n'
        + _SP * (indent + 3) + state_span + '\n'
        + _SP * (indent + 2) + '</div>\n'
        + _SP * (indent + 1) + '</div>\n'
        + _SP * indent
    )

    graph_html = ""
    if graph_type:
        hours = card.get("hours_to_show", 24)
        graph_html = '\n' + _SP * (indent + 1) + '<div class="sensor-graph" data-entity="' + html.escape(eid) + '" data-hours="' + str(hours) + '"></div>\n' + _SP * indent

    return _h("div", {"class": "ha-card sensor-card"}, "\n" + content + graph_html, indent)


@register("history-graph")
def _render_history_graph(card: Card, indent: int = 2) -> str:
    title = html.escape(card.get("title", ""))
    raw_entities = card.get("entities", [])
    hours = card.get("hours_to_show", 24)

    eids = []
    for ent in raw_entities:
        if isinstance(ent, str):
            eids.append(ent)
        elif isinstance(ent, dict):
            eids.append(ent.get("entity", ""))

    header = ""
    if title:
        header = '\n' + _SP * (indent + 1) + '<div class="graph-header">' + title + '</div>'

    chart_data = html.escape(json.dumps({"entities": eids, "hours": hours}))
    chart_div = '\n' + _SP * (indent + 1) + '<div class="history-graph" data-chart=\'' + chart_data + '\'></div>\n' + _SP * indent

    content = header + chart_div
    return _h("div", {"class": "ha-card graph-card"}, content, indent)


@register("gauge")
def _render_gauge(card: Card, indent: int = 2) -> str:
    eid = card.get("entity", "")
    name = html.escape(card.get("name", _friendly_name(eid)))
    min_v = card.get("min", 0)
    max_v = card.get("max", 100)
    severity = card.get("severity", {})

    state_span = _entity_span(eid, indent=indent + 2)
    attrs = {
        "class": "ha-card gauge-card",
        "data-min": str(min_v),
        "data-max": str(max_v),
    }
    if severity:
        attrs["data-severity"] = html.escape(json.dumps(severity))

    content = (
        '\n'
        + _SP * (indent + 1) + '<div class="gauge-content">\n'
        + _SP * (indent + 2) + '<div class="gauge-value">\n'
        + _SP * (indent + 3) + state_span + '\n'
        + _SP * (indent + 2) + '</div>\n'
        + _SP * (indent + 2) + '<div class="gauge-name">' + name + '</div>\n'
        + _SP * (indent + 1) + '</div>\n'
        + _SP * indent
    )
    return _h("div", attrs, content, indent)


@register("iframe")
def _render_iframe(card: Card, indent: int = 2) -> str:
    url = html.escape(card.get("url", ""))
    aspect = card.get("aspect_ratio", "50%")
    style = "aspect-ratio: " + html.escape(str(aspect))
    content = '\n' + _SP * (indent + 1) + '<iframe src="' + url + '" style="' + style + ';width:100%;border:none"></iframe>\n' + _SP * indent
    return _h("div", {"class": "ha-card iframe-card"}, content, indent)


@register("clock")
def _render_clock(card: Card, indent: int = 2) -> str:
    tz = card.get("time_zone", "Europe/London")
    fmt = card.get("time_format", "24")
    sec = card.get("show_seconds", False)
    size = card.get("clock_size", "medium")
    no_bg = card.get("no_background", False)

    size_class = f"clock-size-{size}"
    attrs = {"class": f"ha-card clock-card {size_class}"}
    if no_bg:
        attrs["class"] += " clock-no-bg"

    clock_id = f"c{abs(hash(tz+fmt+str(sec)))%99999999}"

    content = (
        '\n'
        + _SP * (indent + 1)
        + f'<div class="clock-digital" id="{clock_id}"'
        + f' data-tz="{html.escape(tz)}"'
        + f' data-fmt="{html.escape(fmt)}"'
        + (' data-sec="1"' if sec else '')
        + '>--:--</div>\n'
        + _SP * indent
    )
    return _h("div", attrs, content, indent)


# ---- Helpers --------------------------------------------------------------


def _friendly_name(entity_id: str) -> str:
    parts = entity_id.split(".")
    if len(parts) < 2:
        return entity_id
    raw = parts[1].replace("_", " ").replace("-", " ")
    return raw.title()


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
