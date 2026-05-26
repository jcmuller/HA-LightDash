from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.config import AppConfig
from app.ha_client import HAClient
from app.parser import parse_config
from app.renderer import render_page, render_page_list
from app.sse_manager import SSEManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = AppConfig.from_env()
    cfg_path = config.config_path

    if cfg_path.exists():
        try:
            dashboard = parse_config(str(cfg_path))
            logger.info("Loaded config from %s (%d pages)", cfg_path, len(dashboard.pages))
        except Exception as e:
            logger.error("Failed to parse config: %s", e)
            dashboard = None
    else:
        logger.warning("Config not found at %s — no pages available", cfg_path)
        dashboard = None

    ha_client = HAClient(config.ha_url, config.ha_token)
    connected = await ha_client.connect()
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


@app.get("/", response_class=HTMLResponse)
async def root():
    dashboard = getattr(app.state, "dashboard", None)
    if dashboard and dashboard.pages:
        return render_page_list(dashboard.pages)
    return HTMLResponse(
        "<html><body><h1>LightDash</h1><p>No dashboard config loaded.</p></body></html>"
    )


@app.get("/health")
async def health():
    ha_ok = getattr(app.state, "ha_client", None) and app.state.ha_client.is_connected
    return {"status": "ok", "ha_connected": ha_ok}


@app.get("/page/{page_id}", response_class=HTMLResponse)
async def page(page_id: str):
    dashboard = getattr(app.state, "dashboard", None)
    if not dashboard:
        return HTMLResponse("<html><body><h1>No config loaded</h1></body></html>", status_code=503)

    for p in dashboard.pages:
        if p.id == page_id:
            return render_page(p, dashboard)

    return PlainTextResponse("Page not found: " + page_id, status_code=404)


@app.post("/action")
async def handle_action(request: Request):
    try:
        data: Dict[str, Any] = await request.json()
    except Exception:
        data = {}

    widget_id = data.get("widget_id", "")
    event = data.get("event", "")
    widget_type = data.get("type", "")

    logger.info("Action: widget=%s event=%s type=%s", widget_id, event, widget_type)

    ha = getattr(app.state, "ha_client", None)
    if ha and ha.is_connected and widget_id:
        entity_id = widget_id
        domain = entity_id.split(".")[0] if "." in entity_id else ""
        if event in ("on_click",) and widget_type in ("switch", "button"):
            domain_service_map = {
                "switch": ("switch", "toggle"),
                "light": ("light", "toggle"),
                "fan": ("fan", "toggle"),
                "climate": ("climate", "toggle"),
                "cover": ("cover", "toggle"),
                "media_player": ("media_player", "media_play_pause"),
                "lock": ("lock", "lock"),
                "input_boolean": ("input_boolean", "toggle"),
            }
            if domain in domain_service_map:
                svc_domain, svc_name = domain_service_map[domain]
                await ha.call_service(svc_domain, svc_name, {"entity_id": entity_id})
                logger.info("Called %s.%s on %s", svc_domain, svc_name, entity_id)
        elif event in ("on_value", "on_change") and widget_type == "slider":
            value = data.get("value")
            if value is not None and domain == "light":
                await ha.call_service("light", "turn_on", {
                    "entity_id": entity_id,
                    "brightness_pct": int(value),
                })

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
