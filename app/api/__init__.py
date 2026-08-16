"""Context helpers shared across page routes."""

from typing import Any

from fastapi import Request

from app.core.config import settings

# Single source of truth for the tab strip. Order defines the tab index used by
# `current_tab`, the /tab endpoint's 0-4 validation, and `active_tab` highlighting.
TAB_DEFINITIONS: list[dict[str, str]] = [
    {"num": "0", "label": "Brief", "id": "tab-brief"},
    {"num": "1", "label": "Persona & Questions", "id": "tab-persona"},
    {"num": "2", "label": "GEO Diagnosis", "id": "tab-diagnosis"},
    {"num": "3", "label": "Campaign Plan", "id": "tab-plan"},
    {"num": "4", "label": "Content Studio", "id": "tab-content"},
]

MAX_TAB_INDEX = len(TAB_DEFINITIONS) - 1

# Which template renders each tab index.
TAB_TEMPLATES: list[str] = [
    "tab_brief.html",
    "tab_persona.html",
    "tab_diagnosis.html",
    "tab_plan.html",
    "tab_content_studio.html",
]


def build_tabs(disabled: list[bool] | None = None) -> list[dict[str, Any]]:
    """Build the tab strip. `disabled[i]` marks tab i as not navigable.

    Defaults to everything past the Brief disabled, which is the correct state
    for a page with no campaign loaded yet.
    """
    if disabled is None:
        disabled = [False] + [True] * MAX_TAB_INDEX
    return [{**tab, "disabled": disabled[i]} for i, tab in enumerate(TAB_DEFINITIONS)]


def default_tabs() -> list[dict[str, Any]]:
    return build_tabs()


def page_context(
    request: Request,
    *,
    language: str = "zh",
    tabs: list[dict[str, Any]] | None = None,
    active_tab: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    """Build the common template context for every page."""
    return {
        "request": request,
        "language": language,
        "tabs": tabs or default_tabs(),
        "active_tab": active_tab,
        "geo_hub_url": settings.geo_hub_url,
        **extra,
    }
