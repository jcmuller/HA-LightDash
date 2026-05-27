from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.compat import scan_dashboard
from app.config import AppConfig
from app.ha_client import HAClient
from app.renderer import render_error, render_view, render_view_index
from app.sse_manager import SSEManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent


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
    logger.info("Loaded %d dashboard(s): %s", len(dashboards), list(dashboards.keys()))
    for name, d in dashboards.items():
        scan_dashboard(d)

    app.state.config = config
    app.state.dashboards = dashboards
    app.state.ha_client = ha_client
    app.state.sse = sse
    app.state.base_path = config.base_path

    import app.renderer as r
    r._base_path = config.base_path

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


@app.get("/", response_class=HTMLResponse)
async def root():
    bp = getattr(app.state, "base_path", "")
    css = bp + "/static/style.css" if bp else "/static/style.css"
    return HTMLResponse(
        '<!DOCTYPE html>'
        '<html lang="en">'
        '<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>LightDash</title>'
        '<link rel="stylesheet" href="' + css + '">'
        '</head>'
        '<body>'
        '<div class="view-index">'
        '<h1>LightDash</h1>'
        '<p>Go to <code>/d/{dashboard_name}</code> to load a dashboard.</p>'
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
    bp = getattr(app.state, "base_path", "")
    url = f"{bp}/d/{name}/view/{first.path}" if bp else f"/d/{name}/view/{first.path}"
    return RedirectResponse(url=url, status_code=302)


@app.get("/d/{name}/view/{view_path:path}", response_class=HTMLResponse)
async def dashboard_view(name: str, view_path: str):
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
    return {
        "status": "ok",
        "ha_connected": ha_ok,
        "dashboards_loaded": len(dashboards),
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