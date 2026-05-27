from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class HAClient:
    def __init__(self, ha_url: str, ha_token: str):
        self.ha_url = ha_url.rstrip("/")
        self.ha_token = ha_token
        self._http = httpx.AsyncClient(
            base_url=self.ha_url,
            headers={
                "Authorization": f"Bearer {ha_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        self._connected = False

    async def connect(self) -> bool:
        if not self.ha_url or not self.ha_token:
            logger.warning("HA_URL or HA_TOKEN not set — running in offline mode")
            return False
        try:
            r = await self._http.get("/api/")
            self._connected = r.is_success
            if self._connected:
                logger.info("Connected to Home Assistant at %s", self.ha_url)
            else:
                logger.warning("HA connection failed: %s %s", r.status_code, r.text)
            return self._connected
        except Exception as e:
            logger.warning("HA connection error: %s", e)
            self._connected = False
            return False

    async def disconnect(self):
        await self._http.aclose()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def call_service(self, domain: str, service: str, data: Dict[str, Any]) -> Optional[Dict]:
        if not self._connected:
            logger.debug("HA not connected — skipping service call")
            return None
        try:
            r = await self._http.post(f"/api/services/{domain}/{service}", json=data)
            if r.is_success:
                return r.json()
            logger.warning("Service call failed: %s %s", r.status_code, r.text)
            return None
        except Exception as e:
            logger.warning("Service call error: %s", e)
            return None

    async def get_state(self, entity_id: str) -> Optional[Dict]:
        if not self._connected:
            return None
        try:
            r = await self._http.get(f"/api/states/{entity_id}")
            if r.is_success:
                return r.json()
            return None
        except Exception as e:
            logger.warning("State fetch error: %s", e)
            return None

    async def get_states(self) -> Optional[List[Dict]]:
        if not self._connected:
            return None
        try:
            r = await self._http.get("/api/states")
            if r.is_success:
                return r.json()
            return None
        except Exception as e:
            logger.warning("States fetch error: %s", e)
            return None

    async def get_dashboard_config(self, url_path: str = "lovelace") -> Optional[Dict]:
        if not self._connected:
            logger.warning("HA not connected — cannot fetch dashboard config")
            return None
        try:
            r = await self._http.get(f"/api/lovelace/config/{url_path}")
            if r.is_success:
                data = r.json()
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                return data
            logger.warning("Fetch dashboard config failed: %s %s", r.status_code, r.text)
            return None
        except Exception as e:
            logger.warning("Fetch dashboard config error: %s", e)
            return None

    async def get_history(self, entity_id: str, hours: int = 24) -> Optional[List]:
        if not self._connected:
            return None
        try:
            from datetime import datetime, timedelta, timezone
            start = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            params = {"filter_entity_id": entity_id, "minimal_response": "true"}
            r = await self._http.get(f"/api/history/period/{start}", params=params)
            if r.is_success:
                return r.json()
            return None
        except Exception as e:
            logger.warning("History fetch error: %s", e)
            return None
