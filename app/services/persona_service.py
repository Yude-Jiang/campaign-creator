"""Persona, VP, and Benchmark Question generation service.

Uses a 3-phase LLM pipeline for richer, deeper output:
  Phase 1: Persona Discovery (Gemini + grounding)
  Phase 2: VP Generation (DeepSeek)
  Phase 3: Question Discovery (Gemini + grounding)
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from app.services.llm_router import llm_router
from app.utils.json_parser import safe_parse_json

logger = logging.getLogger(__name__)

MASTER_PERSONA_DIR = Path(__file__).parent.parent / "data" / "master_personas"
_CODE_PATTERN = re.compile(r"\bm0\d\b")


def _load_master_personas() -> list[dict]:
    """Load master persona skeletons. Returns [] if dir missing (graceful degradation)."""
    if not MASTER_PERSONA_DIR.is_dir():
        return []
    result = []
    for f in sorted(MASTER_PERSONA_DIR.glob("m*.json")):
        try:
            result.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("Skipping malformed master persona %s: %s", f.name, e)
    return result


def _scrub_codes(persona: dict) -> dict:
    """Remove anchor codes leaked into any text field (model sometimes echoes context ids)."""
    for key, val in persona.items():
        if key == "anchor":
            continue
        if isinstance(val, str):
            persona[key] = _CODE_PATTERN.sub("", val).strip()
        elif isinstance(val, list):
            persona[key] = [
                _CODE_PATTERN.sub("", v).strip() if isinstance(v, str) else v
                for v in val
            ]
    return persona


def _ensure_persona_defaults(persona: dict) -> dict:
    """Fill in default values for persona fields."""
    persona.setdefault("id", "")
    persona.setdefault("name", "")
    persona.setdefault("layer", "practitioner")
    persona.setdefault("tech_depth", "moderate")
    persona.setdefault("decision_weight", "medium")
    persona.setdefault("daily_tasks", [])
    persona.setdefault("search_queries", [])
    persona.setdefault("info_channels", [])
    persona.setdefault("trusted_sources", [])
    persona.setdefault("pain_points", [])
    persona.setdefault("objections", [])
    persona.setdefault("decision_criteria", [])
    persona.setdefault("value_proposition", "")
    persona.setdefault("vp_headline", "")
    persona.setdefault("vp_argument", "")
    persona.setdefault("vp_proof_points", [])
    persona.setdefault("vp_competitor_comparison", {})
    persona.setdefault("anchor", "")
    persona.setdefault("basis", "generated")
    persona.setdefault("decision_role", "")
    persona.setdefault("funnel_stage", "")
    persona.setdefault("preferred_channels", [])
    persona.setdefault("avoid_channels", [])
    return persona


def _ensure_question_defaults(question: dict) -> dict:
    """Fill in default values for question fields."""
    question.setdefault("id", "")
    question.setdefault("text", "")
    question.setdefault("text_en", "")
    question.setdefault("category", "category_awareness")
    question.setdefault("target_persona_ids", [])
    question.setdefault("diagnostic_value", "medium")
    question.setdefault("assumed_platform", "")
    question.setdefault("assumed_heat", "")
    question.setdefault("search_intent", "")
    question.setdefault("difficulty_level", "")
    question.setdefault("assumed_search_volume", question.pop("search_volume_estimate", ""))
    question.setdefault("seasonality", "")
    question.setdefault("related_questions", [])
    question.setdefault("funnel_stage", "")
    question.setdefault("added_after_baseline", False)
    return question


async def generate_personas_and_questions(
    campaign_data: dict,
    language: str = "zh",
) -> dict:
    """Generate Personas, Value Propositions, and Benchmark Questions.

    Three-phase pipeline:
      1. Persona Discovery — deep research with web grounding (Gemini)
      2. VP Generation — differentiated value propositions per persona (DeepSeek)
      3. Question Discovery — benchmark questions with rich metadata (Gemini)

    Returns a dict with keys: personas, questions, model, grounding_used
    """
    brief = campaign_data.get("brief", {})

    models_used = []
    grounding_used = False

    # ── Phase 1: Persona Discovery ──
    logger.info("Phase 1: Persona Discovery (Gemini + grounding)")

    # Load master persona skeletons (graceful degradation if dir missing)
    master_personas = _load_master_personas()
    region = "china" if language == "zh" else "emea_us"
    if master_personas:
        logger.info("Loaded %d master persona skeletons (region=%s)", len(master_personas), region)
    else:
        logger.info("No master personas found — using pure generation mode")

    p1_result = await llm_router.route_and_generate(
        task="persona_discovery",
        prompt_name="persona_discovery.md",
        variables={
            "brief": brief,
            "master_personas": master_personas,
            "region": region,
        },
        language=language,
        max_tokens=8192,
    )
    p1_parsed = safe_parse_json(p1_result["text"])
    personas = p1_parsed.get("personas", [])
    models_used.append(f"personas:{p1_result['model']}")
    if p1_result.get("grounding_used"):
        grounding_used = True

    if not personas:
        logger.warning("Phase 1 returned no personas — using fallback")
        personas = [{
            "id": "prac_default",
            "name": "技术决策者" if language == "zh" else "Technical Decision Maker",
            "layer": "practitioner",
        }]

    # Scrub leaked codes + validate anchors against loaded master set
    valid_codes = {mp["code"] for mp in master_personas}
    for p in personas:
        _scrub_codes(p)
        anchor = p.get("anchor", "")
        if anchor and anchor not in valid_codes:
            p["anchor"] = ""
        p["basis"] = "research" if p.get("anchor") else "generated"

    # Ensure defaults on all personas
    personas = [_ensure_persona_defaults(p) for p in personas]

    # ── Phase 2: VP Generation ──
    logger.info("Phase 2: VP Generation (DeepSeek)")
    p2_result = await llm_router.route_and_generate(
        task="vp_generation",
        prompt_name="vp_generation.md",
        variables={
            "brief": brief,
            "personas": personas,
            "data_assets": campaign_data.get("data_assets", []),
        },
        language=language,
        max_tokens=8192,
    )
    p2_parsed = safe_parse_json(p2_result["text"])
    value_props = p2_parsed.get("value_propositions", [])
    models_used.append(f"vps:{p2_result['model']}")

    # Merge VP data back into personas
    vp_map = {vp["persona_id"]: vp for vp in value_props if "persona_id" in vp}
    for p in personas:
        vp = vp_map.get(p["id"], {})
        p["vp_headline"] = vp.get("headline", "")
        p["vp_argument"] = vp.get("argument", "")
        p["vp_proof_points"] = vp.get("proof_points", [])
        p["vp_competitor_comparison"] = vp.get("competitor_comparison", {})
        # Also set a combined value_proposition string for backward compat
        if not p.get("value_proposition") and vp.get("headline"):
            p["value_proposition"] = vp["headline"]

    # ── Phase 3: Question Discovery ──
    logger.info("Phase 3: Question Discovery (Gemini + grounding)")
    p3_result = await llm_router.route_and_generate(
        task="question_discovery",
        prompt_name="question_discovery.md",
        variables={
            "brief": brief,
            "personas": personas,
            "value_propositions": value_props,
        },
        language=language,
        max_tokens=8192,
    )
    p3_parsed = safe_parse_json(p3_result["text"])
    questions = p3_parsed.get("questions", [])
    models_used.append(f"questions:{p3_result['model']}")
    if p3_result.get("grounding_used"):
        grounding_used = True
    grounding_sources = p3_result.get("grounding_sources", [])

    # Ensure defaults on all questions
    questions = [_ensure_question_defaults(q) for q in questions]

    # Snapshot which master persona versions were used (freeze principle)
    master_snapshot = None
    if master_personas:
        master_snapshot = {
            "codes": [mp["code"] for mp in master_personas],
            "schema_version": master_personas[0].get("schema_version", "1.0") if master_personas else "1.0",
            "loaded_at": datetime.now().isoformat(),
        }

    return {
        "personas": personas,
        "value_propositions": value_props,
        "questions": questions,
        "model": " + ".join(models_used),
        "grounding_used": grounding_used,
        "grounding_sources": grounding_sources,
        "master_persona_snapshot": master_snapshot,
    }
