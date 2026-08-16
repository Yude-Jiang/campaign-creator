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

    Returns a dict with keys: personas, questions, model,
    persona_grounding, question_grounding (each phase's grounding is
    tracked separately — see _grounding_record).
    """
    brief = campaign_data.get("brief", {})

    models_used = []

    def _grounding_record(result: dict) -> dict:
        """Capture what grounding actually happened for one phase.

        Each phase is recorded separately: persona claims and question claims
        are sourced independently, and collapsing them into one flag made the
        personas look as well-sourced as the questions.
        """
        return {
            "model": result.get("model", ""),
            "requested": bool(result.get("grounding_requested")),
            "used": bool(result.get("grounding_used")),
            "sources": result.get("grounding_sources", []),
            "queries": result.get("grounding_queries", []),
        }

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
    persona_grounding = _grounding_record(p1_result)
    logger.info(
        "Phase 1 grounding: requested=%s used=%s sources=%d",
        persona_grounding["requested"],
        persona_grounding["used"],
        len(persona_grounding["sources"]),
    )

    if not personas:
        # Previously this substituted a single empty placeholder persona and
        # returned ok — the caller could not tell generation had failed, and
        # every downstream step (VPs, questions, the whole plan) was built on
        # a fabricated audience. Fail loudly instead.
        logger.error(
            "Phase 1 produced no personas (model=%s). Raw output head: %s",
            p1_result.get("model", "?"),
            (p1_result.get("text") or "")[:300],
        )
        raise RuntimeError(
            "Persona 生成失败：模型未返回任何 persona（model="
            f"{p1_result.get('model', '?')}）。请重试；若反复失败，检查模型配置或简化 Brief。 | "
            "Persona generation failed: the model returned no personas "
            f"(model={p1_result.get('model', '?')}). Retry; if it keeps failing, "
            "check model configuration or simplify the Brief."
        )

    # Scrub leaked codes + validate anchors against loaded master set
    valid_codes = {mp["code"] for mp in master_personas}
    for p in personas:
        _scrub_codes(p)
        anchor = p.get("anchor", "")
        if anchor and anchor not in valid_codes:
            p["anchor"] = ""
        # "anchored" = instantiated from a hand-written master skeleton, so its
        # decision_role / funnel_stage / channel preferences carry human
        # authorship. It does NOT mean the persona was web-researched — the
        # earlier value "research" was routinely read that way.
        p["basis"] = "anchored" if p.get("anchor") else "generated"

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
    if not value_props:
        logger.error(
            "Phase 2 produced no value propositions (model=%s) — personas will "
            "have empty VP fields. Raw output head: %s",
            p2_result.get("model", "?"),
            (p2_result.get("text") or "")[:300],
        )

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
    question_grounding = _grounding_record(p3_result)
    logger.info(
        "Phase 3 grounding: requested=%s used=%s sources=%d",
        question_grounding["requested"],
        question_grounding["used"],
        len(question_grounding["sources"]),
    )

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
        "persona_grounding": persona_grounding,
        "question_grounding": question_grounding,
        # Legacy keys — question-scoped, as they have always been. Kept so
        # campaigns generated before per-phase tracking still render.
        "grounding_used": question_grounding["used"],
        "grounding_sources": question_grounding["sources"],
        "master_persona_snapshot": master_snapshot,
    }
