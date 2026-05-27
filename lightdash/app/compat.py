from __future__ import annotations

import logging
import re
from typing import List

from app.models import Card, Dashboard, View

logger = logging.getLogger(__name__)

JINJA_RE = re.compile(r"\{\{|\{%")


def _card_warnings(card: Card) -> List[str]:
    warnings: List[str] = []
    orig = card.get("_original_type", "")
    if orig:
        if orig == "custom:mushroom-light-card":
            warnings.append("'custom:mushroom-light-card' mapped to 'tile' — brightness/color controls may differ from original")
        elif orig == "custom:mushroom-cover-card":
            warnings.append("'custom:mushroom-cover-card' mapped to 'entities' — cover controls may differ from original")
        elif orig == "custom:mushroom-number-card":
            warnings.append("'custom:mushroom-number-card' mapped to 'tile' — numeric input may differ from original")
        elif orig.startswith("custom:"):
            warnings.append(f"'{orig}' not fully supported — rendered as '{card.type}'")
    if card.type == "markdown":
        content = card.get("content", "")
        if JINJA_RE.search(content):
            warnings.append(
                "Markdown card contains HA Jinja2 template syntax (unsupported) — "
                "use a 'clock' card for time display instead"
            )
    if card.get("card_mod"):
        warnings.append("'card_mod' styling is not supported in LightDash")
    return warnings


def _walk_cards(view: View) -> List[Card]:
    if view.sections:
        return [c for s in view.sections for c in s.cards]
    return view.cards


def scan_view(view: View) -> List[str]:
    warnings: List[str] = []
    for card in _walk_cards(view):
        warnings.extend(_card_warnings(card))
    return warnings


def scan_dashboard(dashboard: Dashboard) -> None:
    for view in dashboard.views:
        warnings = scan_view(view)
        if warnings:
            logger.info("Compat [%s]:", view.title)
            for w in warnings:
                logger.info("  - %s", w)


def has_jinja_markdown(view: View) -> bool:
    for card in _walk_cards(view):
        if card.type == "markdown":
            content = card.get("content", "")
            if JINJA_RE.search(content):
                return True
    return False
