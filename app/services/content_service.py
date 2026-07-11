"""Content generation service for Tab 4: Content Studio.

Maps content plan items to channel-specific prompt templates and
routes generation through the LLM router.
"""

import logging
import re
from typing import Any

from app.services.llm_router import llm_router

logger = logging.getLogger(__name__)

# ── T2: Pre-publish risk scanning ──

_NUMERIC_CLAIM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|μA|mA|MHz|GHz|Gb|Mb|cm²|万片|万辆|美元|\$)")
_PENDING_MARK = re.compile(r"\[需核实[^\]]*\]|\[TBD[^\]]*\]|\[To verify[^\]]*\]", re.IGNORECASE)


def scan_content_risks(text: str, data_assets: list[dict], language: str = "zh") -> dict:
    """Return {"pending_marks": int, "numeric_claims": int, "message": str}. Never blocks."""
    pending = len(_PENDING_MARK.findall(text))
    numeric = len(_NUMERIC_CLAIM.findall(text))
    msg = ""
    if pending or (numeric and not data_assets):
        if language == "zh":
            parts = []
            if pending:
                parts.append(f"{pending} 处待核实标记")
            if numeric and not data_assets:
                parts.append(f"{numeric} 处量化声明但本 campaign 无数据资产")
            msg = "发布前检查：" + "；".join(parts) + "。请逐条核实替换或删除后再发布。"
        else:
            parts = []
            if pending:
                parts.append(f"{pending} pending verification markers")
            if numeric and not data_assets:
                parts.append(f"{numeric} numeric claims with no data assets in this campaign")
            msg = "Pre-publish check: " + "; ".join(parts) + ". Verify, replace, or remove each before publishing."
    return {"pending_marks": pending, "numeric_claims": numeric, "message": msg}


# ── Channel-Fit Soft Validation ──


def check_channel_fit(persona: dict, channel: str, language: str = "zh") -> str:
    """Soft channel-fit check. Returns warning text or "" (never raises, never blocks).

    Data source is the persona's own avoid/preferred channel fields (inherited
    from master persona skeletons via anchor). Personas without these fields
    (legacy data, free-generated personas) silently pass.
    """
    if not persona or not channel:
        return ""
    avoid = persona.get("avoid_channels") or []
    if not avoid:
        return ""
    # Substring match both directions — channel values are free-form CN/EN labels
    hit = next((a for a in avoid if a and (a in channel or channel in a)), None)
    if not hit:
        return ""
    preferred = persona.get("preferred_channels") or []
    name = persona.get("name", "")
    if language == "zh":
        msg = f"渠道适配提示：受众「{name}」通常回避此类渠道（{hit}）。"
        if preferred:
            msg += f"该受众偏好渠道：{'、'.join(preferred[:4])}。可无视此提示继续生成。"
    else:
        msg = f"Channel-fit note: audience \"{name}\" typically avoids this channel type ({hit})."
        if preferred:
            msg += f" Preferred channels: {', '.join(preferred[:4])}. You may ignore this and generate anyway."
    return msg


# ── Format → Template Mapping ──
# Ordered by specificity: more specific substrings checked first.
# Each entry: (match_substrings, template_filename, task_key, needs_keywords)

FORMAT_MAPPING: list[tuple[list[str], str, str, bool]] = [
    (["zhihu_long", "zhihu_long_form"], "content_zhihu_long.md", "content_organic_chinese", False),
    (["zhihu_qa", "zhihu_answer", "zhihu_question"], "content_zhihu_qa.md", "content_organic_chinese", False),
    (["csdn", "technical_blog"], "content_csdn.md", "content_organic_chinese", False),
    (["bilibili", "b站", "video_script"], "content_bilibili.md", "content_organic_chinese", False),
    (["wechat", "微信", "wechat_article"], "content_wechat.md", "content_organic_chinese", False),
    (["email", "邮件", "nurture"], "content_email.md", "content_email", False),
    (["baidu_sem", "baidu_search", "sem", "paid_search"], "content_baidu_sem.md", "content_paid_baidu_sem", True),
    (["baidu_feed", "baidu_info", "feed_ad"], "content_baidu_feed.md", "content_paid_baidu_feed", False),
    (["linkedin"], "content_linkedin.md", "content_organic_english", False),
    (["bing"], "content_bing_ads.md", "content_paid_bing", True),
    # Broad zhihu fallback (must be after zhihu_qa and zhihu_long)
    (["zhihu"], "content_zhihu_long.md", "content_organic_chinese", False),
    # Ultimate fallback
    (["*"], "content_zhihu_long.md", "content_organic_chinese", False),
]


# ── Format Options (for Custom Content UI) ──
# Each entry maps to FORMAT_MAPPING above via key substring matching.
# zh_platforms / en_platforms used by get_available_formats() for language filtering.

FORMAT_OPTIONS: list[dict[str, str]] = [
    {"key": "zhihu_long", "label_zh": "知乎长文", "label_en": "Zhihu Long-Form", "channel": "知乎", "channel_type": "organic"},
    {"key": "zhihu_qa", "label_zh": "知乎问答", "label_en": "Zhihu Q&A", "channel": "知乎", "channel_type": "organic"},
    {"key": "csdn", "label_zh": "CSDN 技术博客", "label_en": "CSDN Technical Blog", "channel": "CSDN", "channel_type": "organic"},
    {"key": "bilibili", "label_zh": "B站视频脚本", "label_en": "Bilibili Video Script", "channel": "B站", "channel_type": "organic"},
    {"key": "wechat", "label_zh": "微信公众号", "label_en": "WeChat Article", "channel": "微信", "channel_type": "organic"},
    {"key": "email", "label_zh": "邮件培育序列", "label_en": "Email Nurture Series", "channel": "邮件", "channel_type": "organic"},
    {"key": "baidu_sem", "label_zh": "百度竞价广告", "label_en": "Baidu SEM", "channel": "百度竞价", "channel_type": "paid"},
    {"key": "baidu_feed", "label_zh": "百度信息流广告", "label_en": "Baidu Feed Ad", "channel": "百度信息流", "channel_type": "paid"},
    {"key": "linkedin", "label_zh": "LinkedIn", "label_en": "LinkedIn", "channel": "LinkedIn", "channel_type": "organic"},
    {"key": "bing", "label_zh": "Bing Ads", "label_en": "Bing Ads", "channel": "Bing", "channel_type": "paid"},
]

_ZH_PLATFORM_KEYS = {"zhihu_long", "zhihu_qa", "csdn", "bilibili", "wechat", "baidu_sem", "baidu_feed"}
_EN_PLATFORM_KEYS = {"linkedin", "bing"}


def get_available_formats(language: str = "zh") -> list[dict[str, str]]:
    """Return FORMAT_OPTIONS filtered by campaign language.

    Chinese campaigns hide LinkedIn/Bing (no zh templates).
    English campaigns hide zhihu/csdn/bilibili/baidu/wechat (no en templates).
    """
    if language == "zh":
        return [o for o in FORMAT_OPTIONS if o["key"] not in _EN_PLATFORM_KEYS]
    else:
        return [o for o in FORMAT_OPTIONS if o["key"] not in _ZH_PLATFORM_KEYS]


def _resolve_format(format_str: str) -> dict[str, str | bool]:
    """Map a free-form format string to a prompt template and task key.

    Uses substring matching against FORMAT_MAPPING.
    Returns {"template_name": str, "task_key": str, "needs_keywords": bool}
    """
    fmt_lower = format_str.lower().strip()
    for substrings, template, task_key, needs_kw in FORMAT_MAPPING:
        if "*" in substrings:
            # Universal fallback
            logger.warning("Unrecognized format '%s', falling back to %s", format_str, template)
            return {"template_name": template, "task_key": task_key, "needs_keywords": needs_kw}
        if any(s in fmt_lower for s in substrings):
            return {"template_name": template, "task_key": task_key, "needs_keywords": needs_kw}

    # Should never reach here due to "*" fallback, but be safe
    return {"template_name": "content_zhihu_long.md", "task_key": "content_organic_chinese", "needs_keywords": False}


def _find_persona(personas: list[dict], target_id: Any, language: str = "zh") -> dict:
    """Find a persona by ID, with fallback handling for lists and missing matches."""
    if not personas:
        return {"name": "技术决策者" if language == "zh" else "Technical Decision Maker", "layer": "practitioner"}

    # Handle target_persona_id being a list (from LLM output) or string
    lookup_id = target_id
    if isinstance(target_id, list) and target_id:
        lookup_id = target_id[0]
    if not lookup_id:
        return personas[0]

    # Try exact ID match
    for p in personas:
        if p.get("id") == lookup_id:
            return p

    # Try fuzzy: match against name or layer
    name_lower = str(lookup_id).lower()
    for p in personas:
        pid = str(p.get("id", "")).lower()
        pname = str(p.get("name", "")).lower()
        player = str(p.get("layer", "")).lower()
        if name_lower in pid or name_lower in pname or name_lower in player:
            return p

    # Fallback to first persona
    logger.warning("Persona not found for id '%s', using first available", lookup_id)
    return personas[0]


def _find_question(questions: list[dict], question_id: str) -> str:
    """Find question text by ID, returning empty string if not found."""
    for q in questions:
        if q.get("id") == question_id:
            return q.get("text", "")
    logger.warning("Question not found for id '%s'", question_id)
    return ""


def _build_content_variables(
    campaign_data: dict,
    priority_index: int,
    content_index: int,
) -> tuple[dict[str, Any], dict, str, str, str, bool]:
    """Resolve format, build variables, and return everything needed to render the prompt.

    Returns:
        (variables, content_item, format_str, template_name, task_key, needs_keywords)
    """
    plan = campaign_data.get("plan", {})
    if not plan:
        raise ValueError("No plan data found — generate a Campaign Plan first")

    priorities = plan.get("priorities", [])
    if priority_index < 0 or priority_index >= len(priorities):
        raise ValueError(f"priority_index {priority_index} out of range (0-{len(priorities) - 1})")

    priority_item = priorities[priority_index]
    content_plan = priority_item.get("content_plan", [])
    if content_index < 0 or content_index >= len(content_plan):
        raise ValueError(
            f"content_index {content_index} out of range (0-{len(content_plan) - 1})"
        )

    content_item = content_plan[content_index]
    format_str = content_item.get("format", "")
    if not format_str:
        raise ValueError("Content item has no format — cannot determine template")

    # ── Resolve format to template ──
    resolved = _resolve_format(format_str)
    template_name = str(resolved["template_name"])
    task_key = str(resolved["task_key"])
    needs_keywords = bool(resolved["needs_keywords"])

    # ── Gather template variables ──
    brief = campaign_data.get("brief", {})

    # Persona lookup
    personas = campaign_data.get("personas", [])
    target_id = content_item.get("target_persona_id", "")
    lang = campaign_data.get("language", "zh")
    persona = _find_persona(personas, target_id, language=lang)

    # Question lookup
    questions = campaign_data.get("questions", [])
    question_id = priority_item.get("question_id", "")
    question_text = _find_question(questions, question_id)
    if not question_text:
        # Fallback: use anchor_point as subject matter
        question_text = priority_item.get("anchor_point", "")

    anchor_point = priority_item.get("anchor_point", "")
    keywords = brief.get("keywords", [])

    # The content_brief from the plan — used as editing guidance
    content_brief_context = content_item.get("content_brief", "") or content_item.get("llm_prompt", "")

    # ── Build template variables ──
    variables: dict[str, Any] = {
        "brief": brief,
        "persona": persona,
        "anchor_point": anchor_point,
        "question_text": question_text,
    }
    if needs_keywords:
        variables["keywords"] = keywords

    variables["content_brief"] = content_brief_context
    variables["data_assets"] = campaign_data.get("data_assets", [])

    # ── Inject persona-derived fields for richer prompt context (sliced to prevent bloat) ──
    p = persona or {}
    variables["persona_pain_points"] = p.get("pain_points", [])[:3]
    variables["persona_vp_headline"] = p.get("vp_headline", "")
    variables["persona_vp_argument"] = p.get("vp_argument", "")
    variables["persona_objections"] = p.get("objections", [])[:2]
    variables["persona_search_queries"] = p.get("search_queries", [])[:5]
    variables["persona_info_channels"] = p.get("info_channels", [])[:3]

    return variables, content_item, format_str, template_name, task_key, needs_keywords


def compose_prompt(
    campaign_data: dict,
    priority_index: int,
    content_index: int,
    language: str = "zh",
) -> dict[str, Any]:
    """Compose the full prompt for a content item WITHOUT calling the LLM.

    Returns the rendered prompt as it would be sent to the model, along with
    metadata about the template and format used.
    """
    variables, content_item, format_str, template_name, task_key, _ = \
        _build_content_variables(campaign_data, priority_index, content_index)

    # Render using the same Jinja2 environment as the LLM router
    from app.services.llm_router import _jinja_env

    template_path = f"{language}/{template_name}"
    try:
        tmpl = _jinja_env.get_template(template_path)
    except Exception:
        raise ValueError(
            f"Template '{template_name}' not found for language '{language}'. "
            f"This channel may not support the current campaign language."
        )

    rendered = tmpl.render(**variables)

    return {
        "prompt": rendered,
        "template": template_name,
        "format": format_str,
        "language": language,
    }


async def generate_content(
    campaign_data: dict,
    priority_index: int,
    content_index: int,
    language: str = "zh",
) -> dict[str, Any]:
    """Generate content for a specific content plan item via LLM.

    Args:
        campaign_data: Full campaign dict
        priority_index: Index into plan.priorities
        content_index: Index into priorities[pi].content_plan
        language: "zh" or "en"

    Returns:
        {"text": str, "model": str, "format": str, "template": str, ...}

    Raises:
        ValueError: If plan, priority, or content item not found
        RuntimeError: If LLM call fails
    """
    variables, content_item, format_str, template_name, task_key, _ = \
        _build_content_variables(campaign_data, priority_index, content_index)

    logger.info(
        "Generating content: format=%s → template=%s, task=%s, model chain routed",
        format_str,
        template_name,
        task_key,
    )

    # ── Channel-fit soft check (T4.9) ──
    channel = content_item.get("channel", "")
    channel_fit_warning = check_channel_fit(variables["persona"], channel, language)

    # ── Call LLM Router ──
    result = await llm_router.route_and_generate(
        task=task_key,
        prompt_name=template_name,
        variables=variables,
        language=language,
        max_tokens=4096,
    )

    # ── T2: Pre-publish risk scan ──
    data_assets = campaign_data.get("data_assets", [])
    risk_scan = scan_content_risks(result["text"], data_assets, language)

    return {
        "text": result["text"],
        "model": result["model"],
        "format": format_str,
        "template": template_name,
        "channel_fit_warning": channel_fit_warning,
        "risk_scan": risk_scan,
    }


# ── Custom Content (user-added, not plan-derived) ──


def build_custom_content_variables(
    campaign_data: dict,
    content_index: int,
) -> tuple[dict[str, Any], dict, str, str, str, bool]:
    """Build Jinja2 variables for a custom content item.

    Mirrors _build_content_variables but reads from campaign_data["custom_content"][content_index]
    instead of plan.priorities[].content_plan[].
    """
    custom_content = campaign_data.get("custom_content", [])
    if content_index < 0 or content_index >= len(custom_content):
        raise ValueError(
            f"content_index {content_index} out of range (0-{len(custom_content) - 1})"
        )

    item = custom_content[content_index]
    format_str = item.get("format", "")
    if not format_str:
        raise ValueError("Custom content item has no format — cannot determine template")

    # Resolve format to template
    resolved = _resolve_format(format_str)
    template_name = str(resolved["template_name"])
    task_key = str(resolved["task_key"])
    needs_keywords = bool(resolved["needs_keywords"])

    # Gather template variables
    brief = campaign_data.get("brief", {})

    # Persona lookup
    personas = campaign_data.get("personas", [])
    target_id = item.get("target_persona_id", "")
    lang = campaign_data.get("language", "zh")
    persona = _find_persona(personas, target_id, language=lang)

    # Question / topic lookup
    question_id = item.get("question_id", "")
    questions = campaign_data.get("questions", [])
    question_text = _find_question(questions, question_id)
    if not question_text:
        question_text = item.get("topic", item.get("anchor_point", ""))

    anchor_point = item.get("anchor_point", "") or item.get("topic", "")

    # Build variables (same shape as _build_content_variables output)
    variables: dict[str, Any] = {
        "brief": brief,
        "persona": persona,
        "anchor_point": anchor_point,
        "question_text": question_text,
    }
    if needs_keywords:
        variables["keywords"] = brief.get("keywords", [])

    variables["content_brief"] = item.get("content_brief", "") or item.get("topic", "")
    variables["data_assets"] = campaign_data.get("data_assets", [])

    # Inject persona-derived fields
    p = persona or {}
    variables["persona_pain_points"] = p.get("pain_points", [])[:3]
    variables["persona_vp_headline"] = p.get("vp_headline", "")
    variables["persona_vp_argument"] = p.get("vp_argument", "")
    variables["persona_objections"] = p.get("objections", [])[:2]
    variables["persona_search_queries"] = p.get("search_queries", [])[:5]
    variables["persona_info_channels"] = p.get("info_channels", [])[:3]

    return variables, item, format_str, template_name, task_key, needs_keywords


def compose_custom_prompt(
    campaign_data: dict,
    content_index: int,
    language: str = "zh",
) -> dict[str, Any]:
    """Compose the full prompt for a custom content item without calling the LLM."""
    variables, _item, format_str, template_name, task_key, _ = \
        build_custom_content_variables(campaign_data, content_index)

    from app.services.llm_router import _jinja_env

    template_path = f"{language}/{template_name}"
    try:
        tmpl = _jinja_env.get_template(template_path)
    except Exception:
        raise ValueError(
            f"Template '{template_name}' not found for language '{language}'. "
            f"This channel may not support the current campaign language."
        )

    rendered = tmpl.render(**variables)

    return {
        "prompt": rendered,
        "template": template_name,
        "format": format_str,
        "language": language,
    }


async def generate_custom_content(
    campaign_data: dict,
    content_index: int,
    language: str = "zh",
) -> dict[str, Any]:
    """Generate content for a custom content item via LLM."""
    variables, item, format_str, template_name, task_key, _ = \
        build_custom_content_variables(campaign_data, content_index)

    logger.info(
        "Generating custom content: format=%s → template=%s, task=%s",
        format_str,
        template_name,
        task_key,
    )

    channel = item.get("channel", "")
    channel_fit_warning = check_channel_fit(variables["persona"], channel, language)

    result = await llm_router.route_and_generate(
        task=task_key,
        prompt_name=template_name,
        variables=variables,
        language=language,
        max_tokens=4096,
    )

    data_assets = campaign_data.get("data_assets", [])
    risk_scan = scan_content_risks(result["text"], data_assets, language)

    return {
        "text": result["text"],
        "model": result["model"],
        "format": format_str,
        "template": template_name,
        "channel_fit_warning": channel_fit_warning,
        "risk_scan": risk_scan,
    }
