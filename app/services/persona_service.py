"""Persona, VP, and Benchmark Question generation service."""

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
    """Attempt to close truncated JSON by counting brackets."""
    # Count open/close brackets and braces
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    # Check if we're inside a string (odd number of unescaped quotes on last line)
    if open_braces > 0 or open_brackets > 0:
        # Remove the last incomplete fragment (may end mid-string or mid-value)
        # Find the last complete item: trim back to last comma or opening bracket
        trimmed = text.rstrip()
        # Try adding closing brackets
        closing = "]" * open_brackets + "}" * open_braces
        # Also need to handle the inline case: remove trailing incomplete entry
        # If the text ends with a partial string, trim back to the last valid comma
        if not trimmed.rstrip().endswith((",", "[", "{")):
            # Find last comma or opening bracket
            last_comma = max(
                trimmed.rfind(","),
                trimmed.rfind("["),
                trimmed.rfind("{"),
            )
            if last_comma > 0:
                # Check if we have unclosed quotes in the trimmed portion
                trimmed = trimmed[:last_comma] + closing
                return trimmed

        return trimmed + closing
    return None


async def generate_personas_and_questions(
    campaign_data: dict,
    language: str = "zh",
) -> dict:
    """Generate Personas, Value Propositions, and Benchmark Questions.

    Uses the combined persona_vp_questions.md template with web grounding
    for persona and question discovery.

    Returns a dict with keys: personas, value_propositions, questions
    """
    brief = campaign_data.get("brief", {})

    variables = {
        "brief": brief,
    }

    result = await llm_router.route_and_generate(
        task="persona_discovery",
        prompt_name="persona_vp_questions.md",
        variables=variables,
        language=language,
        max_tokens=16384,  # Combined output needs much more than default 4096
    )

    parsed = _safe_parse_json(result["text"])

    # Handle multiple possible key names from different model outputs
    personas = (
        parsed.get("personas", [])
        or parsed.get("part1_personas", [])
    )
    questions = (
        parsed.get("questions", [])
        or parsed.get("part3_benchmark_questions", [])
        or parsed.get("benchmark_questions", [])
    )
    value_props = (
        parsed.get("value_propositions", [])
        or parsed.get("part2_value_propositions_refined", [])
    )

    # Ensure each persona has the required fields
    for p in personas:
        p.setdefault("id", "")
        p.setdefault("name", "")
        p.setdefault("layer", "practitioner")
        p.setdefault("tech_depth", "moderate")
        p.setdefault("decision_weight", "medium")
        p.setdefault("pain_points", [])
        p.setdefault("info_channels", [])
        p.setdefault("value_proposition", "")

    # Ensure each question has the required fields
    for q in questions:
        q.setdefault("id", "")
        q.setdefault("text", "")
        q.setdefault("text_en", "")
        q.setdefault("category", "category_awareness")
        q.setdefault("target_persona_ids", [])
        q.setdefault("diagnostic_value", "medium")

    return {
        "personas": personas,
        "value_propositions": value_props,
        "questions": questions,
        "model": result["model"],
        "grounding_used": result.get("grounding_used", False),
    }
