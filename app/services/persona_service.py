"""Persona, VP, and Benchmark Question generation service.

Uses a 3-phase LLM pipeline for richer, deeper output:
  Phase 1: Persona Discovery (Gemini + grounding)
  Phase 2: VP Generation (DeepSeek)
  Phase 3: Question Discovery (Gemini + grounding)
"""

import json
import logging
import re

from app.services.llm_router import llm_router

logger = logging.getLogger(__name__)


def _extract_json_block(text: str) -> str:
    """Extract the first ```json ... ``` block from LLM output."""
    # Try ```json ... ``` first
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    # Try ``` ... ``` (no language spec)
    match = re.search(r"```\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    # If no code blocks, try to find a JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0).strip()
    return text.strip()


def _safe_parse_json(text: str) -> dict:
    """Try to parse JSON, returning empty dict on failure. Handles truncated output."""
    try:
        return json.loads(_extract_json_block(text))
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON from LLM output: %s", e)
        cleaned = _extract_json_block(text)
        # Remove trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try to recover truncated JSON by closing open brackets
        logger.warning("Attempting truncated JSON recovery...")
        try:
            recovered = _close_truncated_json(cleaned)
            if recovered:
                return json.loads(recovered)
        except json.JSONDecodeError:
            pass

        logger.error("Could not recover JSON from LLM output. Raw: %s", text[:500])
        return {}


def _close_truncated_json(text: str) -> str | None:
    """Attempt to close truncated JSON by counting brackets and cleaning up.

    Handles several truncation scenarios:
    1. Clean cut at end of object/array boundary — just add closing brackets.
    2. Cut mid-field (e.g. '"key": "val') — strip back to last comma, then close.
    3. Cut mid-string — strip the incomplete string, find last valid comma, close.
    """
    # Count open/close brackets and braces
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    if open_braces <= 0 and open_brackets <= 0:
        return None

    closing = "]" * open_brackets + "}" * open_braces
    trimmed = text.rstrip()

    # If already clean cut (ends with , or ] or } or quoted value after comma)
    if trimmed.endswith((",", "[", "{")):
        # Strip trailing comma and close
        if trimmed.endswith(","):
            trimmed = trimmed[:-1].rstrip()
        return trimmed + closing

    # If ending with a completed string/object/array, just close
    if trimmed.endswith(("}", "]", '"')):
        return trimmed + closing

    # Truncated mid-string or mid-value: find the last valid JSON boundary
    # Remove everything after the last valid comma or opening bracket
    last_comma = trimmed.rfind(",")
    last_brace = trimmed.rfind("{")
    last_bracket = trimmed.rfind("[")

    cut_point = max(last_comma, last_brace, last_bracket)
    if cut_point < 0:
        return None

    # If last char is a comma, keep it; if it's { or [, keep it
    if cut_point == last_comma:
        trimmed = trimmed[:cut_point]  # drop the comma
    elif cut_point in (last_brace, last_bracket):
        trimmed = trimmed[:cut_point]

    return trimmed + closing


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
    question.setdefault("search_volume_estimate", "")
    question.setdefault("seasonality", "")
    question.setdefault("related_questions", [])
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
    p1_result = await llm_router.route_and_generate(
        task="persona_discovery",
        prompt_name="persona_discovery.md",
        variables={"brief": brief},
        language=language,
        max_tokens=8192,
    )
    p1_parsed = _safe_parse_json(p1_result["text"])
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
        },
        language=language,
        max_tokens=8192,
    )
    p2_parsed = _safe_parse_json(p2_result["text"])
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
    p3_parsed = _safe_parse_json(p3_result["text"])
    questions = p3_parsed.get("questions", [])
    models_used.append(f"questions:{p3_result['model']}")
    if p3_result.get("grounding_used"):
        grounding_used = True
    grounding_sources = p3_result.get("grounding_sources", [])

    # Ensure defaults on all questions
    questions = [_ensure_question_defaults(q) for q in questions]

    return {
        "personas": personas,
        "value_propositions": value_props,
        "questions": questions,
        "model": " + ".join(models_used),
        "grounding_used": grounding_used,
        "grounding_sources": grounding_sources,
    }
