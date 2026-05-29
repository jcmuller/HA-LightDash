from __future__ import annotations

import os
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

_env: Environment | None = None


def _get_env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=True,
        )
    return _env


def register_helpers(helpers: Dict[str, Any]) -> None:
    _get_env().globals.update(helpers)


def render_template(template_name: str, **context) -> str:
    template = _get_env().get_template(template_name)
    return template.render(**context)
