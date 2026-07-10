from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api import page_context

templates = Jinja2Templates(directory="templates")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, lang: str = Query("zh")):
    """Landing page — Tab 0: Campaign Brief."""
    return templates.TemplateResponse(
        request,
        "tab_brief.html",
        page_context(
            request,
            language=lang,
            tabs=[
                {"num": "0", "label": "Brief", "id": "tab-brief", "disabled": False},
                {"num": "1", "label": "Persona & Questions", "id": "tab-persona", "disabled": True},
                {"num": "2", "label": "GEO Diagnosis", "id": "tab-diagnosis", "disabled": True},
                {"num": "3", "label": "Campaign Plan", "id": "tab-plan", "disabled": True},
                {"num": "4", "label": "Content Studio", "id": "tab-content", "disabled": True},
            ],
            campaign_id=None,
        ),
    )


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_view(request: Request, campaign_id: str, lang: str = Query("zh")):
    """Full campaign view with all tabs."""
    from app.utils.file_handler import load_campaign_json

    data = load_campaign_json(campaign_id)
    if not data:
        return templates.TemplateResponse(
            request,
            "tab_brief.html",
            page_context(
                request,
                language=lang,
                tabs=[
                    {"num": "0", "label": "Brief", "id": "tab-brief", "disabled": False},
                    {"num": "1", "label": "Persona & Questions", "id": "tab-persona", "disabled": True},
                    {"num": "2", "label": "GEO Diagnosis", "id": "tab-diagnosis", "disabled": True},
                    {"num": "3", "label": "Campaign Plan", "id": "tab-plan", "disabled": True},
                    {"num": "4", "label": "Content Studio", "id": "tab-content", "disabled": True},
                ],
                campaign_id=None,
                error="Campaign not found",
            ),
        )

    current_tab = data.get("current_tab", 0)
    has_personas = bool(data.get("personas"))
    has_diagnoses = bool(data.get("diagnoses"))
    has_plan = bool(data.get("plan"))

    tabs = [
        {"num": "0", "label": "Brief", "id": "tab-brief", "disabled": False},
        {"num": "1", "label": "Persona & Questions", "id": "tab-persona", "disabled": not has_personas and current_tab < 1},
        {"num": "2", "label": "GEO Diagnosis", "id": "tab-diagnosis", "disabled": not has_personas},
        {"num": "3", "label": "Campaign Plan", "id": "tab-plan", "disabled": not has_diagnoses},
        {"num": "4", "label": "Content Studio", "id": "tab-content", "disabled": not has_plan},
    ]

    # Determine which tab template to render
    if current_tab == 0:
        template_name = "tab_brief.html"
    elif current_tab == 1:
        template_name = "tab_persona.html"
    elif current_tab == 2:
        template_name = "tab_diagnosis.html"
    elif current_tab == 3:
        template_name = "tab_plan.html"
    elif current_tab == 4:
        template_name = "tab_content_studio.html"
    else:
        template_name = "tab_brief.html"

    # Compute extra context for Tab 4
    extra_context: dict = {}
    if current_tab == 4 and data.get("plan"):
        plan = data.get("plan", {})
        priorities = plan.get("priorities", [])
        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        sorted_priorities = sorted(
            priorities,
            key=lambda p: priority_order.get(str(p.get("priority", "P2")), 99),
        )
        # Build persona lookup map for name resolution
        persona_map = {p["id"]: p for p in data.get("personas", []) if p.get("id")}

        # ── Compute channel-fit warnings (T4.9, transient — never persisted) ──
        from app.services.content_service import check_channel_fit

        lang = data.get("language", "zh")
        for p in sorted_priorities:
            for item in p.get("content_plan", []):
                pid = item.get("target_persona_id", "")
                # target_persona_id may be str or list — handle both
                pids = [pid] if isinstance(pid, str) else (pid or [])
                warnings = [
                    w for w in (
                        check_channel_fit(persona_map.get(x, {}), item.get("channel", ""), lang)
                        for x in pids if x
                    ) if w
                ]
                item["_fit_warning"] = warnings[0] if warnings else ""

        extra_context["sorted_priorities"] = sorted_priorities
        extra_context["persona_map"] = persona_map

    return templates.TemplateResponse(
        request,
        template_name,
        page_context(
            request,
            language=data.get("language", lang),
            tabs=tabs,
            campaign_id=campaign_id,
            campaign=data,
            active_tab=current_tab,
            **extra_context,
        ),
    )
