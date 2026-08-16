from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api import TAB_TEMPLATES, build_tabs, page_context

templates = Jinja2Templates(directory="templates")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, lang: str = Query("zh")):
    """Landing page — Tab 0: Campaign Brief."""
    return templates.TemplateResponse(
        request,
        "tab_brief.html",
        page_context(request, language=lang, tabs=build_tabs(), campaign_id=None, active_tab=0),
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
                tabs=build_tabs(),
                campaign_id=None,
                active_tab=0,
                error="Campaign not found",
            ),
        )

    current_tab = data.get("current_tab", 0)
    if not isinstance(current_tab, int) or not 0 <= current_tab < len(TAB_TEMPLATES):
        current_tab = 0

    has_personas = bool(data.get("personas"))
    has_diagnoses = bool(data.get("diagnoses"))
    has_plan = bool(data.get("plan"))

    tabs = build_tabs([
        False,
        not has_personas and current_tab < 1,
        not has_personas,
        not has_diagnoses,
        not has_plan,
    ])

    template_name = TAB_TEMPLATES[current_tab]

    # Compute extra context for Tab 3 (Plan) and Tab 4 (Content Studio)
    extra_context: dict = {}

    if current_tab == 3:
        # Persona lookup map for Plan display
        extra_context["persona_map"] = {
            p.get("id"): p for p in data.get("personas", []) if p and p.get("id")
        }

    if current_tab == 4 and data.get("plan"):
        plan = data.get("plan", {})
        priorities = plan.get("priorities", [])
        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        sorted_priorities = sorted(
            priorities,
            key=lambda p: priority_order.get(str(p.get("priority", "P2")), 99),
        )
        # Build persona lookup map for name resolution
        persona_map = {p.get("id"): p for p in data.get("personas", []) if p and p.get("id")}

        # ── Compute channel-fit warnings (T4.9, transient — never persisted) ──
        from app.services.content_service import check_channel_fit, scan_content_risks

        lang_code = data.get("language", "zh")
        data_assets = data.get("data_assets", [])
        for p in sorted_priorities:
            for item in p.get("content_plan", []):
                pid = item.get("target_persona_id", "")
                # target_persona_id may be str or list — handle both
                pids = [pid] if isinstance(pid, str) else (pid or [])
                warnings = [
                    w for w in (
                        check_channel_fit(persona_map.get(x, {}), item.get("channel", ""), lang_code)
                        for x in pids if x
                    ) if w
                ]
                item["_fit_warning"] = warnings[0] if warnings else ""
                # ── T2: Risk scan for pre-existing generated content (transient) ──
                existing_text = item.get("generated_content", "")
                if existing_text:
                    item["_risk_scan"] = scan_content_risks(existing_text, data_assets, lang_code)

        extra_context["sorted_priorities"] = sorted_priorities
        extra_context["persona_map"] = persona_map
        # Custom content support
        extra_context["custom_content"] = data.get("custom_content", [])
        from app.services.content_service import get_available_formats

        extra_context["format_options"] = get_available_formats(lang_code)

    return templates.TemplateResponse(
        request,
        template_name,
        page_context(
            request,
            # The campaign's own language is authoritative — it selects the prompt
            # set used for every generation step. Changing it goes through
            # PUT /api/campaigns/{id}/language, not a ?lang= query param.
            language=data.get("language", lang),
            tabs=tabs,
            campaign_id=campaign_id,
            campaign=data,
            active_tab=current_tab,
            **extra_context,
        ),
    )
