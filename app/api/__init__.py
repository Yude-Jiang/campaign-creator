"""Context helpers shared across page routes."""

from typing import Any

from fastapi import Request

from app.core.config import settings


def page_context(
    request: Request,
    *,
    language: str = "zh",
    tabs: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the common template context for every page."""
    return {
        "request": request,
        "language": language,
        "tabs": tabs or default_tabs(),
        "geo_hub_url": settings.geo_hub_url,
        **extra,
    }


def default_tabs() -> list[dict[str, Any]]:
    return [
        {"num": "0", "label": "Brief", "id": "tab-brief", "disabled": False},
        {"num": "1", "label": "Persona & Questions", "id": "tab-persona", "disabled": True},
        {"num": "2", "label": "GEO Diagnosis", "id": "tab-diagnosis", "disabled": True},
        {"num": "3", "label": "Campaign Plan", "id": "tab-plan", "disabled": True},
        {"num": "4", "label": "Content Studio", "id": "tab-content", "disabled": True},
    ]
