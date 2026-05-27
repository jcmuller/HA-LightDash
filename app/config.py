import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
            base_path = os.getenv("SUPERVISOR_INGRESS_PATH", "")
            config_dir = ""
        else:
            ha_url = os.getenv("HA_URL", "")
            ha_token = os.getenv("HA_TOKEN", "")
            base_path = os.getenv("BASE_PATH", "")
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
    def load_dashboards(cls, config_dir: str, is_addon: bool) -> dict:
        from app.parser import parse_dashboard_from_file, parse_dashboard

        import yaml

        dashboards: dict = {}

        if is_addon:
            options_path = Path("/data/options.json")
            if options_path.exists():
                with open(options_path) as f:
                    options = json.load(f)
                for entry in options.get("dashboards", []):
                    name = entry["name"]
                    raw = yaml.safe_load(entry["yaml"])
                    if raw:
                        dashboards[name] = parse_dashboard(raw)
        else:
            config_path = Path(config_dir)
            if config_path.exists() and config_path.is_dir():
                for yaml_file in sorted(config_path.glob("*.yaml")):
                    name = yaml_file.stem
                    dashboards[name] = parse_dashboard_from_file(str(yaml_file))

        return dashboards