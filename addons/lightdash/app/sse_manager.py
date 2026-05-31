from __future__ import annotations

import asyncio
import html
import json
import logging
import random
from typing import Any, Set

logger = logging.getLogger(__name__)


class SSEManager:
    def __init__(self):
        self._clients: Set[asyncio.Queue] = set()
        self.allowed_entities: Set[str] = set()
        self.connected = False

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._clients.discard(q)

    def broadcast(self, event: str, data: Any):
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        dead: list[asyncio.Queue] = []
        for q in self._clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    def notify_entity(self, entity_id: str, state: dict):
        value = state.get("state", "")
        unit = state.get("attributes", {}).get("unit_of_measurement", "")
        display = f"{value} {unit}" if unit else str(value)
        event_name = f"entity_{entity_id.replace('.', '_')}"
        payload = f"event: {event_name}\ndata: {html.escape(str(display))}\n\n"
        logger.debug("SSE notify: event=%s data=%s", event_name, display)
        dead: list[asyncio.Queue] = []
        for q in self._clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)


async def run_ha_websocket(ha_url: str, ha_token: str, sse: SSEManager):
    """Connect to HA WebSocket and relay entity updates to SSE clients."""
    if not ha_url or not ha_token:
        logger.info("HA not configured — skipping WebSocket listener")
        return

    import ssl
    import websockets
    import time

    logger.info("HA WebSocket listener started")

    ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://").strip("/")
    ws_url = f"{ws_url}/api/websocket"
    logger.info("WebSocket target: %s", ws_url)

    use_ssl = ha_url.startswith("https://")
    ctx = None
    if use_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    msg_id = 0
    delay = 5.0
    max_delay = 120.0

    while True:
        try:
            async with websockets.connect(ws_url, ssl=ctx if use_ssl else None) as ws:
                msg = json.loads(await ws.recv())
                auth_msg = {"type": "auth", "access_token": ha_token}
                await ws.send(json.dumps(auth_msg))
                auth_resp = json.loads(await ws.recv())
                if auth_resp.get("type") != "auth_ok":
                    logger.error(
                        "HA WebSocket auth failed: %s — giving up",
                        auth_resp,
                    )
                    return

                logger.info("HA WebSocket connected")
                sse.connected = True
                delay = 5.0

                msg_id += 1
                await ws.send(json.dumps({
                    "id": msg_id,
                    "type": "subscribe_events",
                    "event_type": "state_changed",
                }))
                sub_resp = json.loads(await ws.recv())
                if sub_resp.get("success"):
                    logger.info("Subscribed to HA state changes")
                else:
                    logger.warning("HA state subscription failed: %s", sub_resp)
                    return

                last_msg = time.monotonic()
                async for message in ws:
                    last_msg = time.monotonic()
                    data = json.loads(message)
                    if data.get("type") != "event":
                        continue
                    event = data.get("event", {})
                    if event.get("event_type") != "state_changed":
                        continue
                    event_data = event.get("data", {})
                    entity_id = event_data.get("entity_id", "")
                    new_state = event_data.get("new_state", {})
                    if entity_id and new_state:
                        if (
                            sse.allowed_entities
                            and entity_id not in sse.allowed_entities
                        ):
                            continue
                        sse.notify_entity(entity_id, new_state)

        except asyncio.CancelledError:
            logger.info("HA WebSocket listener cancelled")
            sse.connected = False
            return
        except websockets.exceptions.InvalidStatus as e:
            sse.connected = False
            logger.warning(
                "HA WebSocket rejected: %s (reconnecting in %ds)",
                e,
                round(delay),
            )
        except Exception as e:
            sse.connected = False
            logger.warning(
                "HA WebSocket error: %s (reconnecting in %ds)",
                e,
                round(delay),
            )

        await asyncio.sleep(delay)
        delay = min(delay * 1.5 + random.uniform(0, delay * 0.25), max_delay)
