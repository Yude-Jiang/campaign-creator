"""Campaign Plan generation — two-step LLM pipeline.

Step 1: Analyze diagnoses → structured analysis JSON
Step 2: Generate full campaign plan from analysis + personas
"""

import json
import logging

from app.services.llm_router import llm_router
from app.utils.json_parser import safe_parse_json

logger = logging.getLogger(__name__)


async def generate_campaign_plan(
    campaign_data: dict,
    language: str = "zh",
) -> dict:
    """Generate a full Campaign Plan from diagnosis data.

    Two-step pipeline:
    1. analyze_diagnosis.md → structured analysis (competitor landscape, gaps, priorities)
    2. generate_plan.md → full campaign plan with timeline, content strategy, metrics

    Raises ValueError if diagnosis data is missing or insufficient.
    """
    brief = campaign_data.get("brief", {})
    questions = campaign_data.get("questions", [])
    personas = campaign_data.get("personas", [])
    diagnoses = campaign_data.get("diagnoses", [])

    if not diagnoses:
        raise ValueError("No diagnosis files uploaded — cannot generate plan")

    # ── Step 1: Analyze Diagnoses ──
    # Load raw text from diagnosis files
    from app.services.diagnosis_parser import parse_diagnoses_for_campaign

    parsed_diagnoses = parse_diagnoses_for_campaign(campaign_data)

    # Attach raw_text to each diagnosis entry
    for diag in diagnoses:
        diag_qid = diag.get("question_id", "")
        parsed = next((p for p in parsed_diagnoses if p["question_id"] == diag_qid), None)
        if parsed:
            diag["raw_text"] = parsed.get("raw_text", "")

    has_content = any(d.get("raw_text", "").strip() for d in diagnoses)
    if not has_content:
        raise ValueError("All diagnosis files appear to be empty — cannot analyze")

    logger.info(
        "Step 1: Analyzing %d diagnoses for campaign %s",
        len(diagnoses),
        campaign_data.get("campaign_id", "unknown"),
    )

    try:
        analysis_result = await llm_router.route_and_generate(
            task="diagnosis_analysis",
            prompt_name="analyze_diagnosis.md",
            variables={
                "brief": brief,
                "questions": questions,
                "diagnoses": diagnoses,
            },
            language=language,
            max_tokens=8192,
        )
    except Exception as e:
        logger.error("Step 1 (diagnosis analysis) failed: %s", e)
        raise RuntimeError(f"Diagnosis analysis failed: {e}") from e

    analysis_json = safe_parse_json(analysis_result["text"])
    if not analysis_json:
        logger.warning("Step 1 returned empty analysis — plan will be based on raw data only")

    logger.info("Diagnosis analysis complete (model: %s)", analysis_result["model"])

    # ── Step 2: Generate Campaign Plan ──
    logger.info("Step 2: Generating campaign plan")

    try:
        plan_result = await llm_router.route_and_generate(
            task="plan_generation",
            prompt_name="generate_plan.md",
            variables={
                "brief": brief,
                "analysis_json": json.dumps(analysis_json, ensure_ascii=False, indent=2),
                "personas": personas,
            },
            language=language,
            max_tokens=16384,
        )
    except Exception as e:
        logger.error("Step 2 (plan generation) failed: %s", e)
        raise RuntimeError(f"Campaign plan generation failed: {e}") from e

    plan_json = safe_parse_json(plan_result["text"])
    logger.info("Plan generation complete (model: %s)", plan_result["model"])

    # ── Handle different output structures from different models ──
    # Some models wrap everything in a "campaign_plan" key
    inner = plan_json.get("campaign_plan", plan_json)

    # ── Merge into unified plan ──
    # Map LLM output keys to canonical keys
    summary = (
        inner.get("ai_perception_summary", "")
        or inner.get("ai_cognition_summary", {})
    )
    if isinstance(summary, dict):
        summary = summary.get("summary", str(summary))

    merged = {
        "campaign_id": campaign_data.get("campaign_id", ""),
        "ai_perception_summary": summary,
        "inverted_pyramid": inner.get("inverted_pyramid", {}),
        "competitor_landscape": (
            inner.get("competitor_landscape", [])
            or inner.get("competitive_landscape_strategy", [])
        ),
        "priorities": (
            inner.get("priorities", [])
            or inner.get("priority_matrix_battle_cards", [])
        ),
        "timeline_90days": (
            inner.get("timeline_90days", [])
            or inner.get("ninety_day_timeline", [])
        ),
        "monitoring_metrics": inner.get("monitoring_metrics", []),
        "content_strategy_summary": inner.get("content_strategy_summary", ""),
    }
    plan_json = merged

    # ── Post-process: Recalculate priority from 3D scores ──
    # LLMs can produce inconsistent priority labels — recalculate deterministically:
    #   P0: strategic_importance ≥ 4 AND winnability ≥ 3 AND st_current_strength ≤ 2
    #   P1: strategic_importance ≥ 3 OR (winnability ≥ 3 AND st_current_strength ≤ 3)
    #   P2: everything else
    for item in plan_json.get("priorities", []):
        si = item.get("strategic_importance", 0) or 0
        scs = item.get("st_current_strength", 0) or 0
        w = item.get("winnability", 0) or 0
        if si >= 4 and w >= 3 and scs <= 2:
            item["priority"] = "P0"
        elif si >= 3 or (w >= 3 and scs <= 3):
            item["priority"] = "P1"
        else:
            item["priority"] = "P2"

    # Attach metadata about the generation process
    plan_json["_generation_meta"] = {
        "analysis_model": analysis_result["model"],
        "plan_model": plan_result["model"],
        "analysis_grounding": analysis_result.get("grounding_used", False),
        "plan_grounding": plan_result.get("grounding_used", False),
    }

    return plan_json
