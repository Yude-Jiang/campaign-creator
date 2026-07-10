"""Campaign CRUD API."""

import json
import logging
import re
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.models.campaign import Campaign, CampaignBrief
from app.utils.file_handler import (
    load_campaign_json,
    list_campaigns,
    save_campaign_json,
    save_diagnosis_file,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _slugify(name: str) -> str:
    """Generate a safe campaign ID from a name."""
    slug = re.sub(r"[^a-zA-Z0-9_一-鿿-]", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


# ── Campaign CRUD ──


class CampaignCreateRequest(BaseModel):
    brief: CampaignBrief
    data_assets: list[dict] | None = None


@router.post("/campaigns")
def create_campaign(req: CampaignCreateRequest):
    """Create a new campaign from the brief."""
    campaign_id = _slugify(req.brief.name) if req.brief.name else f"campaign-{datetime.now():%Y%m%d-%H%M%S}"

    # Check for duplicate
    existing = load_campaign_json(campaign_id)
    if existing:
        campaign_id = f"{campaign_id}-{datetime.now():%H%M%S}"

    campaign = Campaign(
        campaign_id=campaign_id,
        language=req.brief.language,
        brief=req.brief,
        data_assets=req.data_assets or [],
        current_tab=1,
    )

    save_campaign_json(campaign_id, campaign.model_dump())
    return {"campaign_id": campaign_id, "redirect": f"/campaigns/{campaign_id}"}


class ParseBriefRequest(BaseModel):
    text: str
    language: str = "zh"


@router.post("/parse-brief")
async def parse_brief(req: ParseBriefRequest):
    """Parse a natural-language campaign brief into structured fields using AI."""
    from app.services.llm_router import llm_router
    from app.utils.json_parser import safe_parse_json

    result = await llm_router.route_and_generate(
        task="vp_generation",  # Use DeepSeek for fast, cost-effective parsing
        prompt_name="parse_brief.md",
        variables={"text": req.text},
        language=req.language,
        max_tokens=1024,
    )
    parsed = safe_parse_json(result["text"])
    return parsed


@router.get("/campaigns")
def list_all_campaigns():
    """List all campaigns."""
    return {"campaigns": list_campaigns()}


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    """Get a campaign by ID."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return data


@router.put("/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, data: dict):
    """Update campaign data (full replace)."""
    existing = load_campaign_json(campaign_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Campaign not found")
    data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, data)
    return {"ok": True, "campaign_id": campaign_id}


@router.put("/campaigns/{campaign_id}/tab")
def advance_tab(campaign_id: str, tab: int):
    """Advance the campaign to a specific tab (0-3)."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    data["current_tab"] = tab
    data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, data)
    return {"ok": True, "current_tab": tab}


# ── Diagnosis Upload ──


@router.post("/campaigns/{campaign_id}/diagnosis/upload")
async def upload_diagnosis(campaign_id: str, file: UploadFile = File(...), question_id: str = Query(...)):
    """Upload a single GEO diagnosis file for a question."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # ── Server-side validation ──
    fname = (file.filename or "").lower()
    allowed_exts = (".md", ".html", ".htm")
    if not any(fname.endswith(ext) for ext in allowed_exts):
        raise HTTPException(
            status_code=400,
            detail="不支持的文件类型，仅接受 .md / .html / .htm | Unsupported file type — only .md / .html / .htm accepted",
        )

    content = await file.read()
    max_bytes = 5 * 1024 * 1024  # 5 MB
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(content) / 1024 / 1024:.1f} MB），上限 5 MB | File too large ({len(content) / 1024 / 1024:.1f} MB), limit 5 MB",
        )

    saved_path = save_diagnosis_file(campaign_id, question_id, content, file.filename or f"{question_id}.md")

    # Update campaign diagnoses list
    diagnoses = data.get("diagnoses", [])
    existing_idx = next((i for i, d in enumerate(diagnoses) if d.get("question_id") == question_id), None)
    entry = {
        "question_id": question_id,
        "filename": saved_path.name,  # Use actual saved filename (e.g. "q1.md"), not upload name
        "uploaded_at": datetime.now().isoformat(),
    }
    if existing_idx is not None:
        diagnoses[existing_idx] = entry
    else:
        diagnoses.append(entry)

    data["diagnoses"] = diagnoses
    data["updated_at"] = datetime.now().isoformat()

    # Freeze questions baseline on first successful diagnosis upload (S2 invariant)
    if not data.get("questions_frozen_at"):
        data["questions_frozen_at"] = datetime.now().isoformat()

    save_campaign_json(campaign_id, data)

    return {"ok": True, "question_id": question_id, "filename": file.filename}


@router.get("/campaigns/{campaign_id}/diagnosis/status")
def diagnosis_status(campaign_id: str):
    """Get diagnosis upload status (which questions have files)."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    questions = data.get("questions", [])
    diagnoses = data.get("diagnoses", [])
    diag_ids = {d["question_id"] for d in diagnoses}

    return {
        "total": len(questions),
        "uploaded": len(diag_ids),
        "missing": [q["id"] for q in questions if q["id"] not in diag_ids],
    }


# ═══════════════════════════════════════════════════════════════
# Persona & Questions Generation
# ═══════════════════════════════════════════════════════════════


@router.post("/campaigns/{campaign_id}/persona/generate")
async def generate_persona(campaign_id: str):
    """Generate Personas, Value Propositions, and Benchmark Questions via LLM."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.persona_service import generate_personas_and_questions

    language = data.get("language", "zh")
    result = await generate_personas_and_questions(data, language=language)

    data["personas"] = result.get("personas", [])
    data["questions"] = result.get("questions", [])
    data["grounding_sources"] = result.get("grounding_sources", [])
    data["grounding_used"] = result.get("grounding_used", False)
    if result.get("master_persona_snapshot"):
        data["master_persona_snapshot"] = result["master_persona_snapshot"]
    data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, data)

    return {
        "ok": True,
        "campaign_id": campaign_id,
        "personas_count": len(data["personas"]),
        "questions_count": len(data["questions"]),
        "model": result.get("model", ""),
        "grounding_used": result.get("grounding_used", False),
        "grounding_sources": result.get("grounding_sources", []),
    }


class PersonaUpdateRequest(BaseModel):
    personas: list[dict] | None = None
    questions: list[dict] | None = None


@router.put("/campaigns/{campaign_id}/persona")
def update_persona(campaign_id: str, body: PersonaUpdateRequest):
    """Save user-edited personas and/or questions.

    Merges by ID — only provided fields are updated; unedited fields preserved.
    Personas/questions with IDs not in the existing list are appended.
    """
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if body.personas is not None:
        existing_personas = {p.get("id"): p for p in data.get("personas", []) if p.get("id")}
        for incoming in body.personas:
            pid = incoming.get("id", "")
            if pid and pid in existing_personas:
                # Merge: update only provided fields, preserve rest
                existing_personas[pid].update(incoming)
            elif pid:
                # New persona with ID
                existing_personas[pid] = incoming
        data["personas"] = list(existing_personas.values())

    if body.questions is not None:
        frozen = bool(data.get("questions_frozen_at"))
        existing_questions = {q.get("id"): q for q in data.get("questions", []) if q.get("id")}
        for incoming in body.questions:
            qid = incoming.get("id", "")
            if not qid:
                continue
            if qid in existing_questions:
                target = existing_questions[qid]
                if frozen and not target.get("added_after_baseline"):
                    # Baseline question frozen: protect sensitive fields
                    protected = {"text", "text_en", "category", "diagnostic_value"}
                    touched = protected & set(incoming.keys())
                    changed = {k for k in touched if incoming.get(k) != target.get(k)}
                    if changed:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Question {qid} is frozen (baseline locked at "
                                   f"{data['questions_frozen_at']}). Locked fields: {sorted(changed)}. "
                                   f"Add a new question instead.",
                        )
                target.update(incoming)
            else:
                if frozen:
                    incoming["added_after_baseline"] = True
                existing_questions[qid] = incoming
        data["questions"] = list(existing_questions.values())

    data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, data)

    return {"ok": True, "campaign_id": campaign_id}


@router.delete("/campaigns/{campaign_id}/questions/{question_id}")
def delete_question(campaign_id: str, question_id: str):
    """Delete a question. Baseline questions (frozen, not added_after_baseline) are protected."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    questions = data.get("questions", [])
    target = next((q for q in questions if q.get("id") == question_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found")

    frozen = bool(data.get("questions_frozen_at"))
    if frozen and not target.get("added_after_baseline"):
        raise HTTPException(
            status_code=409,
            detail=f"Question {question_id} is frozen (baseline locked at "
                   f"{data['questions_frozen_at']}). Baseline questions cannot be deleted.",
        )

    data["questions"] = [q for q in questions if q.get("id") != question_id]
    data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, data)
    return {"ok": True, "campaign_id": campaign_id, "deleted": question_id}


# ═══════════════════════════════════════════════════════════════
# Campaign Plan Generation
# ═══════════════════════════════════════════════════════════════


@router.post("/campaigns/{campaign_id}/plan/generate")
async def generate_plan(campaign_id: str):
    """Generate a full Campaign Plan from diagnosis data via LLM."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.plan_service import generate_campaign_plan

    language = data.get("language", "zh")
    try:
        plan = await generate_campaign_plan(data, language=language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    data["plan"] = plan
    data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, data)

    return {
        "ok": True,
        "campaign_id": campaign_id,
        "priorities_count": len(plan.get("priorities", [])),
        "meta": plan.get("_generation_meta", {}),
    }


@router.get("/campaigns/{campaign_id}/plan/export/md", response_class=PlainTextResponse)
def export_plan_markdown(campaign_id: str, lang: str = Query("zh")):
    """Export campaign plan as Markdown."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    plan = data.get("plan", {})
    if not plan:
        raise HTTPException(status_code=400, detail="No plan generated yet")

    from app.services.export_service import export_to_markdown

    md = export_to_markdown(plan, data)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={campaign_id}_plan.md"},
    )


@router.get("/campaigns/{campaign_id}/plan/export/html", response_class=HTMLResponse)
def export_plan_html(campaign_id: str, lang: str = Query("zh")):
    """Export campaign plan as styled HTML report."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    plan = data.get("plan", {})
    if not plan:
        raise HTTPException(status_code=400, detail="No plan generated yet")

    from app.services.export_service import export_to_html

    html = export_to_html(plan, data)
    return HTMLResponse(content=html)


# ── Data Assets (T1) ──


class DataAssetsUpdateRequest(BaseModel):
    data_assets: list[dict] = Field(default_factory=list)


@router.put("/campaigns/{campaign_id}/data-assets")
def update_data_assets(campaign_id: str, body: DataAssetsUpdateRequest):
    """Replace the full data_assets list."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    # Add timestamps to any new entries that lack them
    now = datetime.now().isoformat()
    for a in body.data_assets:
        if not a.get("added_at"):
            a["added_at"] = now
        if not a.get("verified_by"):
            a["verified_by"] = "manual"
    data["data_assets"] = body.data_assets
    data["updated_at"] = now
    save_campaign_json(campaign_id, data)
    return {"ok": True, "count": len(body.data_assets)}


# ── Content Studio (Tab 4) ──


class ContentGenerateRequest(BaseModel):
    priority_index: int
    content_index: int


@router.post("/campaigns/{campaign_id}/content/compose-prompt")
def compose_content_prompt(campaign_id: str, body: ContentGenerateRequest):
    """Compose the full rendered prompt for a content item without calling the LLM.

    Returns the exact prompt that would be sent to the model — useful for
    copying into external tools or iterating on prompts manually.
    """
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.content_service import compose_prompt

    language = data.get("language", "zh")
    try:
        result = compose_prompt(
            data,
            priority_index=body.priority_index,
            content_index=body.content_index,
            language=language,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "ok": True,
        "prompt": result["prompt"],
        "template": result["template"],
        "format": result["format"],
    }


@router.post("/campaigns/{campaign_id}/content/generate")
async def generate_content(campaign_id: str, body: ContentGenerateRequest):
    """Generate content for a specific content plan item via LLM."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from app.services.content_service import generate_content as generate_content_item

    language = data.get("language", "zh")
    try:
        result = await generate_content_item(
            data,
            priority_index=body.priority_index,
            content_index=body.content_index,
            language=language,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Persist generated content back to campaign
    plan = data.get("plan", {})
    priorities = plan.get("priorities", [])
    if body.priority_index < len(priorities):
        content_plan = priorities[body.priority_index].get("content_plan", [])
        if body.content_index < len(content_plan):
            item = content_plan[body.content_index]
            item["generated_content"] = result["text"]
            item["generated_model"] = result["model"]
            item["generated_at"] = datetime.now().isoformat()

    data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, data)

    return {
        "ok": True,
        "campaign_id": campaign_id,
        "priority_index": body.priority_index,
        "content_index": body.content_index,
        "content": result["text"],
        "model": result["model"],
        "format": result.get("format", ""),
        "channel_fit_warning": result.get("channel_fit_warning", ""),
    }


@router.get("/campaigns/{campaign_id}/export/all")
def export_full_campaign(campaign_id: str):
    """Export the entire campaign as a JSON file for backup/transfer."""
    data = load_campaign_json(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    from fastapi.responses import Response

    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2, default=str),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={campaign_id}_full.json"},
    )


class CampaignImportRequest(BaseModel):
    campaign_id: str | None = None
    data: dict


@router.post("/campaigns/import")
def import_campaign(req: CampaignImportRequest):
    """Import a campaign from a JSON export file."""
    campaign_id = req.campaign_id or req.data.get("campaign_id", "")
    if not campaign_id:
        raise HTTPException(status_code=400, detail="No campaign_id in import data")

    # If campaign already exists, create a copy with timestamp
    existing = load_campaign_json(campaign_id)
    if existing:
        campaign_id = f"{campaign_id}-import-{datetime.now():%H%M%S}"
        req.data["campaign_id"] = campaign_id

    req.data["updated_at"] = datetime.now().isoformat()
    save_campaign_json(campaign_id, req.data)
    return {"ok": True, "campaign_id": campaign_id}
