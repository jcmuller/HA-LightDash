from __future__ import annotations

import asyncio
import html
import json
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SSEManager:
    def __init__(self):
        self._clients: Set[asyncio.Queue] = set()
        self._entity_subscriptions: Dict[str, Set[asyncio.Queue]] = {}
        self.allowed_entities: Set[str] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._clients.discard(q)
        for subs in self._entity_subscriptions.values():
            subs.discard(q)

    def broadcast(self, event: str, data: Any):
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        dead: List[asyncio.Queue] = []
        for q in self._clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    def notify_entity(self, entity_id: str, state: Dict):
        value = state.get("state", "")
        unit = state.get("attributes", {}).get("unit_of_measurement", "")
        display = f"{value} {unit}" if unit else str(value)
        event_name = f"entity_{entity_id.replace('.', '_')}"
        payload = f"event: {event_name}\ndata: {html.escape(str(display))}\n\n"
        logger.info("SSE notify: event=%s data=%s", event_name, display)
        dead: List[asyncio.Queue] = []
        for q in self._clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    async def run_ha_websocket(self, ha_url: str, ha_token: str):
        """Connect to HA WebSocket and relay entity updates to SSE clients."""
        if not ha_url or not ha_token:
            logger.info("HA not configured — skipping WebSocket listener")
            return

        import ssl
        import websockets

        ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://").strip("/")
        ws_url = f"{ws_url}/api/websocket"

        use_ssl = ha_url.startswith("https://")
        if use_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        msg_id = 0

        while True:
            try:
                kw = {"ssl": ctx} if use_ssl else {}
                async with websockets.connect(ws_url, **kw) as ws:
                    msg = json.loads(await ws.recv())
                    auth_msg = {"type": "auth", "access_token": ha_token}
                    await ws.send(json.dumps(auth_msg))
                    auth_resp = json.loads(await ws.recv())
                    if auth_resp.get("type") != "auth_ok":
                        logger.error("HA WebSocket auth failed: %s", auth_resp)
                        return

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

                    async for message in ws:
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
                                self.allowed_entities
                                and entity_id not in self.allowed_entities
                            ):
                                continue
                            self.notify_entity(entity_id, new_state)

            except asyncio.CancelledError:
                logger.info("HA WebSocket listener cancelled")
                return
            except Exception as e:
                logger.warning("HA WebSocket error: %s (reconnecting in 30s)", e)
                await asyncio.sleep(30)
