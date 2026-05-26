from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import AppConfig
from app.ha_client import HAClient
from app.parser import parse_dashboard_from_api, parse_dashboard_from_file
from app.renderer import render_view, render_view_index
from app.sse_manager import SSEManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = AppConfig.from_env()

    ha_client = HAClient(config.ha_url, config.ha_token)
    connected = await ha_client.connect()

    dashboard = None

    if connected:
        try:
            raw = await ha_client.get_dashboard_config(config.dashboard_path)
            if raw:
                dashboard = parse_dashboard_from_api(raw)
                logger.info("Fetched dashboard '%s' from HA (%d views)", config.dashboard_path, len(dashboard.views))
        except Exception as e:
            logger.warning("Failed to fetch dashboard from HA: %s", e)

    if dashboard is None and config.config_path and config.config_path.exists():
        try:
            dashboard = parse_dashboard_from_file(str(config.config_path))
            logger.info("Loaded config from %s (development fallback)", config.config_path)
        except Exception as e:
            logger.warning("Failed to load development config: %s", e)

    if dashboard is None:
        logger.warning("No dashboard loaded — no views available")

    if not connected:
        logger.info("Running in offline mode — HA features disabled")

    sse = SSEManager()
    task = asyncio.create_task(sse.run_ha_websocket(config.ha_url, config.ha_token))

    app.state.config = config
    app.state.dashboard = dashboard
    app.state.ha_client = ha_client
    app.state.sse = sse

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


_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/", response_class=HTMLResponse)
async def root():
    dashboard = getattr(app.state, "dashboard", None)
    if dashboard and dashboard.views:
        return HTMLResponse(render_view_index(dashboard.views), headers=_NO_CACHE)
    return HTMLResponse(
        '<html><body style="background:#111;color:#eee;padding:20px;font-family:sans-serif">'
        "<h1>LightDash</h1><p>No dashboard config loaded.</p></body></html>",
        headers=_NO_CACHE,
    )


@app.get("/health")
async def health():
    ha_ok = getattr(app.state, "ha_client", None) and app.state.ha_client.is_connected
    return {"status": "ok", "ha_connected": ha_ok}


@app.get("/view/{view_path:path}", response_class=HTMLResponse)
async def view(view_path: str):
    dashboard = getattr(app.state, "dashboard", None)
    if not dashboard:
        return HTMLResponse("<html><body><h1>No config loaded</h1></body></html>", status_code=503, headers=_NO_CACHE)

    cfg = getattr(app.state, "config", None)
    ha_url = cfg.ha_url if cfg else ""

    ha = getattr(app.state, "ha_client", None)
    entity_icons = {}
    if ha and ha.is_connected:
        states = await ha.get_states()
        if states:
            entity_icons = {
                s["entity_id"]: s["attributes"].get("icon", "")
                for s in states if s["attributes"].get("icon")
            }

    for v in dashboard.views:
        if v.path == view_path:
            return HTMLResponse(
                render_view(v, dashboard, ha_url=ha_url, entity_icons=entity_icons),
                headers=_NO_CACHE,
            )

    return RedirectResponse(url="/", status_code=302, headers=_NO_CACHE)


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
        return PlainTextResponse("--", status_code=503)
    state = await ha.get_state(entity_id)
    if not state or "state" not in state:
        return PlainTextResponse("?", status_code=404)
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


@app.get("/api/dashboard")
async def api_dashboard():
    dashboard = getattr(app.state, "dashboard", None)
    if not dashboard:
        return {"error": "No dashboard loaded"}
    return JSONResponse(_dashboard_to_dict(dashboard))


def _dashboard_to_dict(dashboard) -> Dict:
    views_data = []
    for v in dashboard.views:
        cards_data = []
        for c in v.cards:
            cards_data.append({"type": c.type, **c.config})
        views_data.append({"title": v.title, "path": v.path, "icon": v.icon, "badges": v.badges, "cards": cards_data, "type": v.type, "bg_color": v.bg_color})
    return {"title": dashboard.title, "views": views_data}
