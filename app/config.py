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
    dashboard_path: str = "lovelace"
    config_path: Optional[Path] = None
    reload: bool = True

    @classmethod
    def from_env(cls) -> "AppConfig":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        cfg_path_str = os.getenv("CONFIG_PATH", "")
        cfg_path = Path(cfg_path_str) if cfg_path_str else None

        return cls(
            ha_url=os.getenv("HA_URL", ""),
            ha_token=os.getenv("HA_TOKEN", ""),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            dashboard_path=os.getenv("DASHBOARD_PATH", "lovelace"),
            config_path=cfg_path,
            reload=os.getenv("RELOAD", "true").lower() == "true",
        )
