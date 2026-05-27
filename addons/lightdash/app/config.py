import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    ha_url: str = ""
    ha_token: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    config_dir: str = "config"
    is_addon: bool = False
    base_path: str = ""

    @classmethod
    def from_env(cls) -> "AppConfig":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        is_addon = Path("/data/options.json").exists()

        if is_addon:
            ha_url = "http://supervisor/core"
            ha_token = os.getenv("SUPERVISOR_TOKEN", "")
            base_path = cls._resolve_ingress_path(ha_token)
            config_dir = ""
        else:
            ha_url = os.getenv("HA_URL", "")
            ha_token = os.getenv("HA_TOKEN", "")
            base_path = os.getenv("BASE_PATH", "")
            if base_path:
                base_path = base_path.rstrip("/")
            config_dir = os.getenv("CONFIG_DIR", "config")

        return cls(
            ha_url=ha_url,
            ha_token=ha_token,
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            reload=os.getenv("RELOAD", "true").lower() == "true",
            config_dir=config_dir,
            is_addon=is_addon,
            base_path=base_path,
        )

    @classmethod
    def _resolve_ingress_path(cls, ha_token: str) -> str:
        base_path = os.getenv("SUPERVISOR_INGRESS_PATH", "")
        base_path = os.getenv("BASE_PATH", base_path)
        if base_path:
            return base_path.rstrip("/")

        logger.info("SUPERVISOR_INGRESS_PATH empty — querying Supervisor API for ingress URL")
        try:
            import httpx
            resp = httpx.get(
                "http://supervisor/addons/self/info",
                headers={"Authorization": f"Bearer {ha_token}"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                ingress_url = data.get("data", {}).get("ingress_url", "")
                if ingress_url:
                    path = urlparse(ingress_url).path.rstrip("/")
                    logger.info("Resolved ingress path from Supervisor API: %s", path)
                    return path
                logger.warning("Supervisor API returned no ingress_url")
            else:
                logger.warning("Supervisor API returned HTTP %d", resp.status_code)
        except Exception as e:
            logger.warning("Failed to query Supervisor API for ingress path: %s", e)

        return ""

    @staticmethod
    def _get_data_dir(is_addon: bool, config_dir: str) -> Path:
        if is_addon:
            return Path("/data/dashboards")
        return Path(config_dir)

    @classmethod
    def load_dashboards(cls, config_dir: str, is_addon: bool) -> dict:
        from app.parser import parse_dashboard_from_file

        data_dir = cls._get_data_dir(is_addon, config_dir)
        dashboards: dict = {}

        if not data_dir.exists() or not data_dir.is_dir():
            return dashboards

        for yaml_file in sorted(data_dir.glob("*.yaml")):
            name = yaml_file.stem
            try:
                dashboards[name] = parse_dashboard_from_file(str(yaml_file))
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to parse %s: %s", yaml_file.name, e)

        return dashboards

    @staticmethod
    def flush_dashboard_to_disk(name: str, yaml_text: str, is_addon: bool, config_dir: str) -> None:
        from app.parser import parse_dashboard

        data_dir = AppConfig._get_data_dir(is_addon, config_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        file_path = data_dir / f"{name}.yaml"
        with open(file_path, "w") as f:
            f.write(yaml_text)

        raw = yaml.safe_load(yaml_text)
        if raw is None:
            raise ValueError("Empty YAML content")
        parse_dashboard(raw)

    @staticmethod
    def delete_dashboard_from_disk(name: str, is_addon: bool, config_dir: str) -> None:
        data_dir = AppConfig._get_data_dir(is_addon, config_dir)
        file_path = data_dir / f"{name}.yaml"
        if file_path.exists():
            file_path.unlink()
