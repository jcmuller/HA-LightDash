from __future__ import annotations

import asyncio
import html
import json
import logging
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.compat import collect_entities, scan_dashboard
from app.config import AppConfig
from app.ha_client import HAClient
from app.parser import parse_dashboard
from app.renderer import render_error, render_view, render_view_index
from app.sse_manager import SSEManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent

_SW_SCRIPT = '<script>if(navigator.serviceWorker){navigator.serviceWorker.getRegistrations().then(function(r){for(var i=0;i<r.length;i++){r[i].unregister()}})}</script>'


def _rebuild_entity_filter(dashboards: dict, sse: SSEManager) -> None:
    entities: set = set()
    for d in dashboards.values():
        entities.update(collect_entities(d))
    sse.allowed_entities = entities
    logger.info(
        "Entity filter: %d entities across %d dashboard(s)",
        len(entities),
        len(dashboards),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = AppConfig.from_env()

    ha_client = HAClient(config.ha_url, config.ha_token)
    connected = await ha_client.connect()

    if not connected:
        logger.info("Running in offline mode — HA features disabled")

    sse = SSEManager()
    task = asyncio.create_task(sse.run_ha_websocket(config.ha_url, config.ha_token))

    dashboards = AppConfig.load_dashboards(config.config_dir, config.is_addon)
    logger.info("Loaded %d dashboard(s)", len(dashboards))
    for name, d in dashboards.items():
        scan_dashboard(d)
        url = f"{config.base_path}/d/{name}"
        logger.info('  "%s" → %s', d.title, url)

    app.state.config = config
    app.state.dashboards = dashboards
    app.state.ha_client = ha_client
    app.state.sse = sse
    app.state.base_path = config.base_path
    app.state.public_port = config.public_port

    logger.info("base_path=%r is_addon=%s", config.base_path, config.is_addon)

    import app.renderer as r
    r._base_path = config.base_path

    _rebuild_entity_filter(dashboards, sse)

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    await ha_client.disconnect()


app = FastAPI(lifespan=lifespan, title="LightDash", version="0.1.0")

static_dir = APP_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

_no_cache = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _bp() -> str:
    bp = getattr(app.state, "base_path", "")
    if bp:
        import app.renderer as r
        if not r._via_ingress.get():
            return ""
    return bp


@app.middleware("http")
async def detect_ingress(request: Request, call_next):
    import app.renderer as r
    public_port = getattr(app.state, "public_port", "")
    via_ingress = True
    if public_port:
        host = request.headers.get("host", "")
        via_ingress = not host.endswith(f":{public_port}")
    r._via_ingress.set(via_ingress)
    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def root():
    bp = _bp()
    dashboards = getattr(app.state, "dashboards", {})
    css = bp + "/static/style.css" if bp else "/static/style.css"

    items = ""
    if dashboards:
        for name, d in sorted(dashboards.items()):
            title = html.escape(d.title or name)
            url = html.escape(f"{bp}/d/{name}")
            items += f'<li><a href="{url}">{title}</a></li>\n'
    else:
        items = '<li class="empty">No dashboards yet. <a href="' + html.escape(f"{bp}/_config") + '">Add one</a>.</li>'

    return HTMLResponse(
        '<!DOCTYPE html>'
        '<html lang="en">'
        '<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>LightDash</title>'
        '<link rel="stylesheet" href="' + css + '">'
        + _SW_SCRIPT +
        '</head>'
        '<body>'
        '<div class="view-index">'
        '<h1>LightDash</h1>'
        '<ul class="dashboard-list">'
        + items +
        '</ul>'
        '<p class="config-link"><a href="' + html.escape(f"{bp}/_config") + '">&#x2699; Config</a></p>'
        '</div>'
        '</body>'
        '</html>',
        headers=_no_cache,
    )


@app.get("/d/{name}")
async def dashboard_index(name: str):
    dashboard = app.state.dashboards.get(name)
    if not dashboard:
        return HTMLResponse(
            render_error(f"Dashboard '{name}' not found."),
            status_code=404,
            headers=_no_cache,
        )
    if not dashboard.views:
        return HTMLResponse("No views", status_code=404)
    first = dashboard.views[0]
    bp = _bp()
    url = f"{bp}/d/{name}/view/{first.path}" if bp else f"/d/{name}/view/{first.path}"
    return RedirectResponse(url=url, status_code=302)


@app.get("/d/{name}/view/{view_path:path}", response_class=HTMLResponse)
async def dashboard_view(name: str, view_path: str):
    if name == "_preview":
        preview = getattr(app.state, "preview_data", None)
        if not preview:
            return HTMLResponse(render_error("No preview available"), status_code=404, headers=_no_cache)
        dashboard = preview["dashboard"]
        cfg = getattr(app.state, "config", None)
        ha_url = preview.get("ha_url") or (cfg.ha_url if cfg else "")
        entity_icons = preview.get("entity_icons", {})
        entity_states = preview.get("entity_states", {})
        for v in dashboard.views:
            if v.path == view_path:
                return HTMLResponse(
                    render_view(v, dashboard, ha_url=ha_url, entity_icons=entity_icons, entity_states=entity_states, dashboard_name="_preview"),
                    headers=_no_cache,
                )
        return HTMLResponse(render_error(f"View '{view_path}' not found"), status_code=404, headers=_no_cache)

    dashboard = app.state.dashboards.get(name)
    if not dashboard:
        return HTMLResponse(
            render_error(f"Dashboard '{name}' not found."),
            status_code=404,
            headers=_no_cache,
        )

    cfg = getattr(app.state, "config", None)
    ha_url = cfg.ha_url if cfg else ""

    ha = getattr(app.state, "ha_client", None)
    entity_icons = {}
    entity_states = {}
    if ha and ha.is_connected:
        states = await ha.get_states()
        if states:
            entity_icons = {
                s["entity_id"]: s["attributes"].get("icon", "")
                for s in states if s["attributes"].get("icon")
            }
            entity_states = {s["entity_id"]: s for s in states}

    for v in dashboard.views:
        if v.path == view_path:
            return HTMLResponse(
                render_view(v, dashboard, ha_url=ha_url, entity_icons=entity_icons, entity_states=entity_states, dashboard_name=name),
                headers=_no_cache,
            )

    return HTMLResponse(
        render_error(f"View '{view_path}' not found in dashboard '{name}'."),
        status_code=404,
        headers=_no_cache,
    )


@app.get("/health")
async def health():
    ha = getattr(app.state, "ha_client", None)
    ha_ok = ha and ha.is_connected
    dashboards = getattr(app.state, "dashboards", {})
    bp = _bp()
    return {
        "status": "ok",
        "ha_connected": ha_ok,
        "dashboards_loaded": len(dashboards),
        "dashboards": {
            name: f"{bp}/d/{name}"
            for name in dashboards
        },
    }


@app.post("/action")
async def handle_action(request: Request):
    raw = await request.body()
    logger.debug("Raw POST body: %s", raw)
    raw_str = raw.decode("utf-8", errors="replace")
    if raw_str.startswith("{"):
        data: Dict[str, Any] = json.loads(raw_str) if raw_str else {}
    elif raw_str:
        data = dict(urllib.parse.parse_qsl(raw_str))
    else:
        data = {}

    entity_id = data.get("entity_id", "")
    action_type = data.get("action", "toggle")
    service = data.get("service", "")
    target = data.get("target", {})
    action_data = data.get("data", {})

    logger.info("Action: entity=%s action=%s service=%s", entity_id, action_type, service)

    ha = getattr(app.state, "ha_client", None)

    if ha and ha.is_connected:
        if action_type == "toggle":
            if service:
                parts = service.split(".")
                if len(parts) == 2:
                    payload: Dict[str, Any] = {"entity_id": entity_id}
                    result = await ha.call_service(parts[0], parts[1], payload)
                    logger.info("Toggle result: %s", "success" if result is not None else "failed")

        elif action_type == "call-service":
            if service:
                parts = service.split(".")
                if len(parts) == 2:
                    payload = dict(target)
                    if entity_id and "entity_id" not in payload:
                        payload["entity_id"] = entity_id
                    payload.update(action_data)
                    result = await ha.call_service(parts[0], parts[1], payload)
                    logger.info("Service call result: %s", "success" if result is not None else "failed")
    else:
        logger.warning("HA not connected — cannot forward action")

    return HTMLResponse("<!-- action received -->")


@app.get("/_sse")
async def sse_stream(request: Request):
    sse = getattr(app.state, "sse", None)
    if not sse:
        return PlainTextResponse("SSE not available", status_code=503)

    q = sse.subscribe()

    async def event_generator():
        try:
            while True:
                msg = await q.get()
                yield msg
        except Exception:
            pass
        finally:
            sse.unsubscribe(q)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/states")
async def api_states():
    ha = getattr(app.state, "ha_client", None)
    if not ha or not ha.is_connected:
        return {"error": "HA not connected"}
    states = await ha.get_states()
    return states or []


@app.get("/api/state/{entity_id:path}")
async def api_state(entity_id: str):
    ha = getattr(app.state, "ha_client", None)
    if not ha or not ha.is_connected:
        return {"error": "HA not connected"}
    state = await ha.get_state(entity_id)
    return state or {"error": "not found"}


@app.get("/api/value/{entity_id:path}")
async def api_entity_value(entity_id: str):
    ha = getattr(app.state, "ha_client", None)
    if not ha or not ha.is_connected:
        return PlainTextResponse("--")
    try:
        state = await ha.get_state(entity_id)
    except Exception:
        state = None
    if not state or "state" not in state:
        return PlainTextResponse("?")
    val = state["state"]
    unit = state.get("attributes", {}).get("unit_of_measurement", "")
    display = f"{val} {unit}" if unit else str(val)
    return PlainTextResponse(display)


@app.get("/api/history/{entity_id:path}")
async def api_history(entity_id: str, hours: int = 24):
    ha = getattr(app.state, "ha_client", None)
    if not ha or not ha.is_connected:
        return {"error": "HA not connected"}
    history = await ha.get_history(entity_id, hours)
    return history or []


@app.get("/ha/image/serve/{path:path}")
async def proxy_ha_image(path: str):
    config = getattr(app.state, "config", None)
    if not config or not config.ha_url:
        return PlainTextResponse("HA not configured", status_code=502)
    url = f"{config.ha_url.rstrip('/')}/api/image/serve/{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, headers={"Authorization": f"Bearer {config.ha_token}"})
            return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/png"))
        except Exception as e:
            logger.warning("Image proxy error: %s", e)
            return PlainTextResponse("Image fetch failed", status_code=502)


# ── Config editor ──────────────────────────────────────────────────────────

_NEW_DASHBOARD_TEMPLATE = """\
title: {name}
views:
  - title: Home
    path: home
    icon: mdi:home
    sections:
      - cards:
          - type: tile
            entity: ""
"""


@app.get("/_config", response_class=HTMLResponse)
async def config_page():
    bp = _bp()
    css = bp + "/static/style.css" if bp else "/static/style.css"
    cfg = getattr(app.state, "config", None)
    public_base = cfg.public_base if cfg and cfg.public_base else ""

    return HTMLResponse(f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LightDash Config</title>
<link rel="stylesheet" href="{css}">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/codemirror@5/lib/codemirror.css">
<style>
  #config-layout {{
    display: grid;
    grid-template-columns: 200px 1fr 1fr;
    height: 100vh;
    overflow: hidden;
  }}
  #sidebar {{
    background: #181818;
    border-right: 1px solid #2a2a2a;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    overflow-y: auto;
  }}
  #sidebar h2 {{
    font-size: 0.95rem;
    color: #eee;
    margin: 0;
  }}
  #sidebar ul {{
    list-style: none;
    padding: 0;
    margin: 0;
    flex: 1;
  }}
  #sidebar li {{
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85rem;
    color: #ccc;
  }}
  #sidebar li:hover {{
    background: #2a2a2a;
  }}
  #sidebar li.active {{
    background: #1e3a5f;
    color: #fff;
  }}
  #sidebar .btn {{
    display: block;
    width: 100%;
    padding: 6px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85rem;
    font-family: inherit;
    text-align: center;
  }}
  #sidebar .btn-add {{
    background: #1e3a5f;
    color: #fff;
  }}
  #sidebar .btn-add:hover {{
    background: #2a4a7f;
  }}
  #sidebar .btn-del {{
    background: #3a1a1a;
    color: #f88;
    margin-top: 4px;
  }}
  #sidebar .btn-del:hover {{
    background: #5a2a2a;
  }}
  #editor-pane {{
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  #editor-container {{
    flex: 1;
    overflow: hidden;
    position: relative;
  }}
  #editor-container .CodeMirror {{
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    height: 100%;
  }}
  #editor-container .CodeMirror-scroll {{
    overflow-y: auto;
    overflow-x: auto;
  }}
  #fallback-editor {{
    width: 100%;
    height: 100%;
    background: #1e1e1e;
    color: #ddd;
    border: none;
    font-family: monospace;
    padding: 8px;
    resize: none;
    display: none;
  }}
  #status-bar {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: #1a1a1a;
    border-top: 1px solid #2a2a2a;
    font-size: 0.8rem;
  }}
  #status-msg {{
    flex: 1;
    color: #888;
  }}
  #status-msg.error {{
    color: #f88;
  }}
  #status-msg.ok {{
    color: #8f8;
  }}
  #status-bar button {{
    padding: 4px 12px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    font-family: inherit;
  }}
  #save-btn {{
    background: #1e3a5f;
    color: #fff;
  }}
  #save-btn:hover {{
    background: #2a4a7f;
  }}
  #preview-btn {{
    background: #2a2a2a;
    color: #ccc;
  }}
  #preview-btn:hover {{
    background: #3a3a3a;
  }}
  #rename-btn {{
    background: #2a2a2a;
    color: #ccc;
    margin-top: 4px;
  }}
  #rename-btn:hover {{
    background: #3a3a3a;
  }}
  #url-btn {{
    background: #2a3a2a;
    color: #8c8;
  }}
  #url-btn:hover {{
    background: #3a4a3a;
  }}
  #preview-pane {{
    border-left: 1px solid #2a2a2a;
    background: #111;
  }}
  #preview-frame {{
    width: 100%;
    height: 100%;
    border: none;
  }}
</style>
{_SW_SCRIPT}
</head>
<body>
<div id="config-layout">
  <aside id="sidebar">
    <h2>Dashboards</h2>
    <ul id="dashboard-list"></ul>
    <button class="btn btn-add" id="add-btn">+ Add Dashboard</button>
    <button class="btn btn-del" id="del-btn" style="display:none">Delete</button>
    <button class="btn btn-add" id="rename-btn" style="display:none">Rename</button>
  </aside>
  <main id="editor-pane">
    <div id="editor-container"><textarea id="yaml-editor"></textarea></div>
    <div id="status-bar">
      <span id="status-msg">Select a dashboard to edit</span>
      <button id="preview-btn">Preview</button>
      <button id="url-btn">Public URL</button>
      <button id="save-btn">Save</button>
    </div>
  </main>
  <aside id="preview-pane">
    <iframe id="preview-frame" srcdoc="<html><body style='background:#111;color:#555;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:1.2rem'>Preview</body></html>"></iframe>
  </aside>
</div>

<script>
const BASE="{bp}";
const LIST_URL = BASE + "/_config/dashboards";
const PREVIEW_URL = BASE + "/_config/preview";
const PUBLIC_BASE="{public_base}";
</script>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/lib/codemirror.js"></script>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/mode/yaml/yaml.js"></script>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/addon/edit/closebrackets.js"></script>
<script>
(function() {{
  let currentName = null;
  let cm = null;
  const ta = document.getElementById("yaml-editor");
  const listEl = document.getElementById("dashboard-list");
  const statusMsg = document.getElementById("status-msg");
  const previewFrame = document.getElementById("preview-frame");
  const delBtn = document.getElementById("del-btn");
  const renameBtn = document.getElementById("rename-btn");

  function setStatus(msg, type) {{
    statusMsg.textContent = msg;
    statusMsg.className = type || "";
  }}

  async function loadList() {{
    try {{
      const res = await fetch(LIST_URL);
      const list = await res.json();
      listEl.innerHTML = "";
      for (const d of list) {{
        const li = document.createElement("li");
        li.textContent = d.name + (d.title ? " \\u2014 " + d.title : "");
        li.dataset.name = d.name;
        li.addEventListener("click", () => selectDashboard(d.name));
        if (d.name === currentName) li.classList.add("active");
        listEl.appendChild(li);
      }}
      if (list.length === 0) {{
        delBtn.style.display = "none";
        renameBtn.style.display = "none";
      }}
    }} catch(e) {{
      setStatus("Failed to load dashboard list", "error");
    }}
  }}

  async function selectDashboard(name) {{
    currentName = name;
    document.querySelectorAll("#dashboard-list li").forEach(li => li.classList.toggle("active", li.dataset.name === name));
    delBtn.style.display = "";
    renameBtn.style.display = "";
    try {{
      const res = await fetch(LIST_URL + "/" + encodeURIComponent(name) + ".yaml");
      const text = await res.text();
      if (cm) {{
        cm.setValue(text);
      }} else {{
        ta.value = text;
      }}
      setStatus("Editing: " + name, "");
      refreshPreview();
    }} catch(e) {{
      setStatus("Failed to load YAML", "error");
    }}
  }}

  function getYaml() {{
    return cm ? cm.getValue() : ta.value;
  }}

  async function saveDashboard() {{
    if (!currentName) return;
    const yaml = getYaml();
    try {{
      const res = await fetch(LIST_URL + "/" + encodeURIComponent(currentName), {{
        method: "PUT",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{yaml}})
      }});
      if (res.ok) {{
        setStatus("Saved", "ok");
        refreshPreview();
        loadList();
      }} else {{
        const err = await res.json();
        setStatus(err.error || "Save failed", "error");
      }}
    }} catch(e) {{
      setStatus("Save error: " + e.message, "error");
    }}
  }}

  async function refreshPreview() {{
    if (!currentName) return;
    const yaml = getYaml();
    try {{
      const res = await fetch(PREVIEW_URL, {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{yaml}})
      }});
      if (res.ok) {{
        const html = await res.text();
        previewFrame.srcdoc = html;
      }} else {{
        const err = await res.json();
        previewFrame.srcdoc = "<html><body style='background:#111;color:#f88;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:1.2rem'>" + (err.error || "Preview failed") + "</body></html>";
      }}
    }} catch(e) {{
      previewFrame.srcdoc = "<html><body style='background:#111;color:#f88;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:1.2rem'>Preview error</body></html>";
    }}
  }}

  async function addDashboard() {{
    const name = prompt("Dashboard name (URL-safe, e.g. living-room):");
    if (!name || !name.match(/^[a-zA-Z0-9_-]+$/)) {{
      if (name) setStatus("Invalid name. Use letters, numbers, hyphens, underscores.", "error");
      return;
    }}
    try {{
      const res = await fetch(LIST_URL, {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{name}})
      }});
      if (res.ok) {{
        await loadList();
        await selectDashboard(name);
        setStatus("Created: " + name, "ok");
      }} else {{
        const err = await res.json();
        setStatus(err.error || "Create failed", "error");
      }}
    }} catch(e) {{
      setStatus("Create error: " + e.message, "error");
    }}
  }}

  async function deleteDashboard() {{
    if (!currentName || !confirm('Delete "' + currentName + '"?')) return;
    try {{
      const res = await fetch(LIST_URL + "/" + encodeURIComponent(currentName), {{
        method: "DELETE"
      }});
      if (res.ok) {{
        currentName = null;
        if (cm) cm.setValue(""); else ta.value = "";
        previewFrame.srcdoc = "<html><body style='background:#111;color:#555;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;font-size:1.2rem'>Preview</body></html>";
        delBtn.style.display = "none";
        renameBtn.style.display = "none";
        setStatus("Deleted", "ok");
        await loadList();
      }} else {{
        const err = await res.json();
        setStatus(err.error || "Delete failed", "error");
      }}
    }} catch(e) {{
      setStatus("Delete error: " + e.message, "error");
    }}
  }}

  async function renameDashboard() {{
    if (!currentName) return;
    const newName = prompt('New name for "' + currentName + '" (URL-safe):', currentName);
    if (!newName || newName === currentName) return;
    if (!newName.match(/^[a-zA-Z0-9_-]+$/)) {{
      setStatus("Invalid name. Use letters, numbers, hyphens, underscores.", "error");
      return;
    }}
    try {{
      const res = await fetch(LIST_URL + "/" + encodeURIComponent(currentName) + "/rename", {{
        method: "PUT",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{new_name: newName}})
      }});
      if (res.ok) {{
        currentName = newName;
        await loadList();
        setStatus("Renamed to: " + newName, "ok");
      }} else {{
        const err = await res.json();
        setStatus(err.error || "Rename failed", "error");
      }}
    }} catch(e) {{
      setStatus("Rename error: " + e.message, "error");
    }}
  }}

  try {{
    cm = CodeMirror.fromTextArea(ta, {{
      mode: "yaml",
      theme: "default",
      lineNumbers: true,
      indentUnit: 2,
      tabSize: 2,
      lineWrapping: true,
      autoCloseBrackets: true,
      extraKeys: {{"Ctrl-S": () => saveDashboard()}}
    }});
  }} catch(e) {{
    cm = null;
    ta.style.display = "";
  }}

  document.getElementById("add-btn").addEventListener("click", addDashboard);
  document.getElementById("del-btn").addEventListener("click", deleteDashboard);
  document.getElementById("rename-btn").addEventListener("click", renameDashboard);
  document.getElementById("save-btn").addEventListener("click", saveDashboard);
  document.getElementById("preview-btn").addEventListener("click", refreshPreview);
  document.getElementById("url-btn").addEventListener("click", function(){{
    if(!currentName){{setStatus("Select a dashboard first","error");return}}
    var url = (PUBLIC_BASE || window.location.origin + BASE) + "/d/" + encodeURIComponent(currentName);
    navigator.clipboard.writeText(url).then(function(){{
      setStatus("Copied: " + url, "ok");
    }}).catch(function(){{
      setStatus("Failed to copy URL", "error");
    }});
  }});

  loadList();
}})();
</script>
</body>
</html>""", headers=_no_cache)


@app.get("/_config/dashboards")
async def config_list():
    bp = _bp()
    dashboards = getattr(app.state, "dashboards", {})
    return [
        {
            "name": name,
            "title": d.title,
            "url": f"{bp}/d/{name}",
        }
        for name, d in sorted(dashboards.items())
    ]


@app.get("/_config/dashboards/{name}.yaml")
async def config_yaml(name: str):
    config = getattr(app.state, "config", None)
    is_addon = config.is_addon if config else False
    config_dir = config.config_dir if config else "config"
    data_dir = AppConfig._get_data_dir(is_addon, config_dir)
    file_path = data_dir / f"{name}.yaml"
    if not file_path.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return PlainTextResponse(file_path.read_text())


@app.post("/_config/dashboards")
async def config_create(req: Request):
    data = await req.json()
    name = data.get("name", "").strip()
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        return JSONResponse({"error": "Invalid name"}, status_code=400)

    config = getattr(app.state, "config", None)
    is_addon = config.is_addon if config else False
    config_dir = config.config_dir if config else "config"

    data_dir = AppConfig._get_data_dir(is_addon, config_dir)
    file_path = data_dir / f"{name}.yaml"
    if file_path.exists():
        return JSONResponse({"error": f"Dashboard '{name}' already exists"}, status_code=409)

    yaml_text = _NEW_DASHBOARD_TEMPLATE.format(name=name)
    try:
        AppConfig.flush_dashboard_to_disk(name, yaml_text, is_addon, config_dir)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    dashboards = getattr(app.state, "dashboards", {})
    parsed = parse_dashboard(yaml.safe_load(yaml_text))
    dashboards[name] = parsed
    sse = getattr(app.state, "sse", None)
    if sse:
        _rebuild_entity_filter(dashboards, sse)

    bp = _bp()
    return {
        "name": name,
        "title": parsed.title,
        "url": f"{bp}/d/{name}",
    }


@app.put("/_config/dashboards/{name}")
async def config_save(name: str, req: Request):
    data = await req.json()
    yaml_text = data.get("yaml", "").strip()
    if not yaml_text:
        return JSONResponse({"error": "Empty YAML content"}, status_code=400)

    config = getattr(app.state, "config", None)
    is_addon = config.is_addon if config else False
    config_dir = config.config_dir if config else "config"

    data_dir = AppConfig._get_data_dir(is_addon, config_dir)
    file_path = data_dir / f"{name}.yaml"
    if not file_path.exists():
        return JSONResponse({"error": f"Dashboard '{name}' not found"}, status_code=404)

    try:
        AppConfig.flush_dashboard_to_disk(name, yaml_text, is_addon, config_dir)
    except yaml.YAMLError as e:
        return JSONResponse({"error": f"YAML parse error: {e}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    dashboards = getattr(app.state, "dashboards", {})
    raw = yaml.safe_load(yaml_text)
    parsed = parse_dashboard(raw)
    dashboards[name] = parsed
    scan_dashboard(parsed)
    sse = getattr(app.state, "sse", None)
    if sse:
        _rebuild_entity_filter(dashboards, sse)

    return {"ok": True, "title": parsed.title}


@app.delete("/_config/dashboards/{name}")
async def config_delete(name: str):
    config = getattr(app.state, "config", None)
    is_addon = config.is_addon if config else False
    config_dir = config.config_dir if config else "config"

    AppConfig.delete_dashboard_from_disk(name, is_addon, config_dir)

    dashboards = getattr(app.state, "dashboards", {})
    dashboards.pop(name, None)

    return {"ok": True}


@app.put("/_config/dashboards/{name}/rename")
async def config_rename(name: str, req: Request):
    data = await req.json()
    new_name = data.get("new_name", "").strip()
    if not new_name or not new_name.replace("-", "").replace("_", "").isalnum():
        return JSONResponse({"error": "Invalid name"}, status_code=400)

    config = getattr(app.state, "config", None)
    is_addon = config.is_addon if config else False
    config_dir = config.config_dir if config else "config"

    data_dir = AppConfig._get_data_dir(is_addon, config_dir)
    old_path = data_dir / f"{name}.yaml"
    new_path = data_dir / f"{new_name}.yaml"

    if not old_path.exists():
        return JSONResponse({"error": f"Dashboard '{name}' not found"}, status_code=404)
    if new_path.exists():
        return JSONResponse({"error": f"Dashboard '{new_name}' already exists"}, status_code=409)

    old_path.rename(new_path)

    dashboards = getattr(app.state, "dashboards", {})
    if name in dashboards:
        dashboards[new_name] = dashboards.pop(name)

    return {"ok": True, "name": new_name}


@app.post("/_config/preview", response_class=HTMLResponse)
async def config_preview(req: Request):
    data = await req.json()
    yaml_text = data.get("yaml", "").strip()
    if not yaml_text:
        return JSONResponse({"error": "Empty YAML"}, status_code=400)

    try:
        raw = yaml.safe_load(yaml_text)
        if raw is None:
            return JSONResponse({"error": "Empty YAML content"}, status_code=400)
        dashboard = parse_dashboard(raw)
    except yaml.YAMLError as e:
        return JSONResponse({"error": f"YAML parse error: {e}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if not dashboard.views:
        return JSONResponse({"error": "No views in dashboard"}, status_code=400)

    ha = getattr(app.state, "ha_client", None)
    entity_states = {}
    entity_icons = {}
    if ha and ha.is_connected:
        try:
            states = await ha.get_states()
            if states:
                entity_icons = {
                    s["entity_id"]: s["attributes"].get("icon", "")
                    for s in states if s["attributes"].get("icon")
                }
                entity_states = {s["entity_id"]: s for s in states}
        except Exception:
            pass

    cfg = getattr(app.state, "config", None)
    ha_url = cfg.ha_url if cfg else ""
    bp = _bp()

    app.state.preview_data = {
        "dashboard": dashboard,
        "entity_icons": entity_icons,
        "entity_states": entity_states,
        "ha_url": ha_url,
    }

    view = dashboard.views[0]
    html_out = render_view(view, dashboard, ha_url=ha_url, entity_icons=entity_icons, entity_states=entity_states, dashboard_name="_preview")

    pages = ''.join(
        f'<a href="{bp}/d/_preview/view/{html.escape(v.path)}" class="{"active" if v is view else ""}">{html.escape(v.title or v.path)}</a>'
        for v in dashboard.views
    )
    top_bar = f'<div style="display:flex;gap:8px;padding:6px 12px;background:#1a1a1a;border-bottom:1px solid #2a2a2a;font-size:0.85rem">{pages}</div>'

    return HTMLResponse(
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1.0">\n<title>Preview</title>\n'
        '<link rel="stylesheet" href="' + (bp + "/static/style.css" if bp else "/static/style.css") + '">\n'
        + _SW_SCRIPT + '\n'
        + '</head>\n<body>\n'
        + top_bar +
        html_out +
        '</body>\n</html>',
        headers=_no_cache,
    )
