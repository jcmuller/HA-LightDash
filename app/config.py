import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AppConfig:
    ha_url: str = ""
    ha_token: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    config_path: Path = Path("config/dashboard.yaml")
    display_width: int = 800
    display_height: int = 480
    reload: bool = True

    @classmethod
    def from_env(cls) -> "AppConfig":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        return cls(
            ha_url=os.getenv("HA_URL", ""),
            ha_token=os.getenv("HA_TOKEN", ""),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            config_path=Path(os.getenv("CONFIG_PATH", "config/dashboard.yaml")),
            display_width=int(os.getenv("DISPLAY_WIDTH", "800")),
            display_height=int(os.getenv("DISPLAY_HEIGHT", "480")),
            reload=os.getenv("RELOAD", "true").lower() == "true",
        )
