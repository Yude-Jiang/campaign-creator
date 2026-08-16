"""Content generation service for Tab 4: Content Studio.

Maps content plan items to channel-specific prompt templates and
routes generation through the LLM router.
"""

import logging
import re
import uuid
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


# Values different providers use to mean "I ran out of output budget".
_TRUNCATED_REASONS = {"length", "max_tokens", "MAX_TOKENS"}


def _truncation_warning(finish_reason: str, max_tokens: int, language: str) -> str:
    """Return a warning if generation stopped because it ran out of tokens.

    Nothing used to check this, so a long-form article that hit the ceiling was
    returned mid-sentence and presented as finished.
    """
    if not finish_reason or finish_reason not in _TRUNCATED_REASONS:
        return ""
    if language == "zh":
        return (
            f"内容在 {max_tokens} token 上限处被截断，结尾很可能不完整。"
            "请缩短编辑指引或分段生成后再发布。"
        )
    return (
        f"Generation stopped at the {max_tokens}-token ceiling, so the ending is "
        "likely cut off. Shorten the brief or generate in sections before publishing."
    )


class UnknownFormatError(ValueError):
    """The content item's format string matches no known template.

    Previously this fell through to a Zhihu long-form article, so a mislabelled
    LinkedIn item silently produced a Chinese blog post and only a log line
    recorded it. Callers should surface the available formats and let the user
    choose.
    """

    def __init__(self, format_str: str):
        self.format_str = format_str
        super().__init__(f"Unrecognized content format: {format_str!r}")


# Output budget per template. A single global 4096 both truncated long-form
# articles mid-sentence and left ad copy with pointless headroom. These are
# generous enough that hitting the ceiling means the model ran away, not that
# the brief was too long.
FORMAT_MAX_TOKENS: dict[str, int] = {
    "content_zhihu_long.md": 8192,      # 2000-3500 字 plus markdown structure
    "content_csdn.md": 8192,
    "content_wechat.md": 6144,
    "content_bilibili.md": 6144,        # script + shot notes
    "content_linkedin.md": 6144,
    "content_zhihu_qa.md": 4096,
    "content_email.md": 4096,           # a sequence of several emails
    "content_baidu_feed.md": 2048,
    "content_baidu_sem.md": 2048,       # many short variants
    "content_bing_ads.md": 2048,
}
DEFAULT_MAX_TOKENS = 4096


# ── Format → Template Mapping ──
# Ordered by specificity: more specific substrings checked first.
# Each entry: (match_substrings, template_filename, task_key, needs_keywords)

FORMAT_MAPPING: list[tuple[list[str], str, str, bool]] = [
    # Chinese aliases matter: plan `format` values are LLM-generated free text
    # and a zh campaign routinely produces labels like "知乎长文". Those used to
    # match nothing and be rescued by a silent fallback.
    (["zhihu_long", "zhihu_long_form", "知乎长文", "知乎文章"],
     "content_zhihu_long.md", "content_organic_chinese", False),
    (["zhihu_qa", "zhihu_answer", "zhihu_question", "知乎问答", "知乎回答"],
     "content_zhihu_qa.md", "content_organic_chinese", False),
    (["csdn", "technical_blog", "技术博客"],
     "content_csdn.md", "content_organic_chinese", False),
    (["bilibili", "b站", "video_script", "视频脚本"],
     "content_bilibili.md", "content_organic_chinese", False),
    (["wechat", "微信", "wechat_article", "公众号"],
     "content_wechat.md", "content_organic_chinese", False),
    (["email", "邮件", "nurture", "培育"],
     "content_email.md", "content_email", False),
    (["baidu_sem", "baidu_search", "sem", "paid_search", "百度竞价", "竞价", "搜索广告"],
     "content_baidu_sem.md", "content_paid_baidu_sem", True),
    (["baidu_feed", "baidu_info", "feed_ad", "百度信息流", "信息流"],
     "content_baidu_feed.md", "content_paid_baidu_feed", False),
    (["linkedin", "领英"],
     "content_linkedin.md", "content_organic_english", False),
    (["bing", "必应"],
     "content_bing_ads.md", "content_paid_bing", True),
    # Broad zhihu catch — must stay after the two specific zhihu entries.
    (["zhihu", "知乎"], "content_zhihu_long.md", "content_organic_chinese", False),
]


# ── Format Options (for Custom Content UI) ──
# Each entry maps to FORMAT_MAPPING above via key substring matching.
# zh_platforms / en_platforms used by get_available_formats() for language filtering.

FORMAT_OPTIONS: list[dict[str, str]] = [
    {
        "key": "zhihu_long",
        "label_zh": "知乎长文",
        "label_en": "Zhihu Long-Form",
        "channel": "知乎",
        "channel_type": "organic",
    },
    {
        "key": "zhihu_qa",
        "label_zh": "知乎问答",
        "label_en": "Zhihu Q&A",
        "channel": "知乎",
        "channel_type": "organic",
    },
    {
        "key": "csdn",
        "label_zh": "CSDN 技术博客",
        "label_en": "CSDN Technical Blog",
        "channel": "CSDN",
        "channel_type": "organic",
    },
    {
        "key": "bilibili",
        "label_zh": "B站视频脚本",
        "label_en": "Bilibili Video Script",
        "channel": "B站",
        "channel_type": "organic",
    },
    {
        "key": "wechat",
        "label_zh": "微信公众号",
        "label_en": "WeChat Article",
        "channel": "微信",
        "channel_type": "organic",
    },
    {
        "key": "email",
        "label_zh": "邮件培育序列",
        "label_en": "Email Nurture Series",
        "channel": "邮件",
        "channel_type": "organic",
    },
    {
        "key": "baidu_sem",
        "label_zh": "百度竞价广告",
        "label_en": "Baidu SEM",
        "channel": "百度竞价",
        "channel_type": "paid",
    },
    {
        "key": "baidu_feed",
        "label_zh": "百度信息流广告",
        "label_en": "Baidu Feed Ad",
        "channel": "百度信息流",
        "channel_type": "paid",
    },
    {
        "key": "linkedin",
        "label_zh": "LinkedIn",
        "label_en": "LinkedIn",
        "channel": "LinkedIn",
        "channel_type": "organic",
    },
    {
        "key": "bing",
        "label_zh": "Bing Ads",
        "label_en": "Bing Ads",
        "channel": "Bing",
        "channel_type": "paid",
    },
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


def _resolve_format(format_str: str) -> dict[str, str | bool | int]:
    """Map a free-form format string to a prompt template and task key.

    Raises UnknownFormatError rather than guessing. The plan's `format` values
    are LLM-generated free text, so guessing meant a channel mismatch nobody
    saw until they read the output.
    """
    fmt_lower = format_str.lower().strip()
    for substrings, template, task_key, needs_kw in FORMAT_MAPPING:
        if any(s in fmt_lower for s in substrings):
            return {
                "template_name": template,
                "task_key": task_key,
                "needs_keywords": needs_kw,
                "max_tokens": FORMAT_MAX_TOKENS.get(template, DEFAULT_MAX_TOKENS),
            }

    logger.warning("Unrecognized content format %r — asking the user to choose", format_str)
    raise UnknownFormatError(format_str)


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


# ── Diagnostic context ──
# The whole premise of the tool is diagnosis-driven content, but generation used
# to receive only `anchor_point` from the priority item. Everything the GEO
# diagnosis established — which gap this piece is meant to close, how visible
# the brand currently is, who owns the answer today, what the models actually
# said — was discarded before the writing step. That is why output reads
# generic: it did not know what it was for.

# Each gap type calls for a structurally different piece, not a different tone.
GAP_TYPE_STRATEGY: dict[str, dict[str, str]] = {
    "open_gap": {
        "zh": "无人占位：该问题下没有任何厂商建立起权威答案。内容目标是**定义场景和它的判据**——"
              "把「什么条件下该这样做」讲成只有你讲得清的样子。抢定义权优先于抢曝光。",
        "en": "Open gap: no vendor owns the answer here. The goal is to **define the scenario and its "
              "criteria** — cover 'under what conditions this is the right call' so thoroughly that the "
              "framing becomes yours. Owning the definition matters more than visibility.",
    },
    "rival_owned": {
        "zh": "已有他方占位：AI 已把该问题的答案绑定到别的方案。**不要去争这个位置**——正面比较"
              "只会加固对方与该问题的语义关联。改为向下切一层：找出该问题里我们条件最优的**子场景**，"
              "把整篇文章收敛到那个子场景上，讲透它的约束、判据和取舍。目标不是赢得这个 query，"
              "是成为它下一层某个更具体 query 的唯一答案。",
        "en": "Already owned by another approach: the models bind this answer elsewhere. **Do not contest "
              "that position** — comparison only reinforces their association with the question. Go one "
              "level narrower instead: find the **sub-scenario** within this question where our conditions "
              "are strongest, and commit the whole piece to it — its constraints, its criteria, its "
              "trade-offs. The goal is not to win this query but to become the only answer to a more "
              "specific one beneath it.",
    },
    "not_linked": {
        "zh": "认知未关联：品牌本身被认知，但没有和这个主题建立联系。内容目标是**建立证据链**——"
              "把既有能力和该场景显式连起来，让关联在文本中可被直接提取，而不是靠读者推断。",
        "en": "Not linked: the brand is known but not connected to this topic. The goal is to **build the "
              "evidence chain** — state the connection between existing capability and this scenario "
              "explicitly, so it can be extracted directly rather than inferred.",
    },
    "buried_in_pdf": {
        "zh": "信息被埋：答案存在于 datasheet/白皮书里，但模型提取不到。内容目标是**结构化重述**——"
              "把已有事实改写成可直接引用的问答式段落，每段自带完整上下文，不依赖前文指代。",
        "en": "Buried: the answer exists in datasheets or whitepapers but models cannot extract it. The "
              "goal is a **structured restatement** — rewrite known facts as self-contained, quotable "
              "passages that carry their own context.",
    },
}


def _diagnosis_excerpt(campaign_data: dict, question_id: str, limit: int = 1200) -> str:
    """Return the raw diagnosis text for one question, trimmed.

    Reading the file here is deliberate: the analysis and plan steps compress
    the diagnosis into scores and an anchor, which loses the specifics a writer
    needs — which competitors the models named, what they got wrong.
    """
    if not question_id:
        return ""
    diagnoses = campaign_data.get("diagnoses") or []
    # Older campaigns stored bare filenames here rather than dicts.
    entry = next(
        (d for d in diagnoses
         if isinstance(d, dict) and d.get("question_id") == question_id),
        None,
    )
    if not entry:
        return ""

    raw = entry.get("raw_text") or ""
    if not raw and entry.get("filename"):
        try:
            from app.utils.file_handler import read_diagnosis_file

            raw = read_diagnosis_file(
                campaign_data.get("campaign_id", ""), entry["filename"]
            ) or ""
        except Exception as e:  # a missing file must not block writing
            logger.warning("Could not read diagnosis for %s: %s", question_id, e)
            return ""
    return raw.strip()[:limit]


def _diagnostic_context(campaign_data: dict, priority_item: dict, language: str) -> dict[str, Any]:
    """Assemble what the diagnosis established about this specific question."""
    plan = campaign_data.get("plan") or {}
    gap_type = str(priority_item.get("gap_type") or "").strip()
    strategy = GAP_TYPE_STRATEGY.get(gap_type, {}).get(language, "")

    # Only competitors the plan actually named — a full landscape dump would
    # crowd out the persona and asset sections.
    landscape = [
        {
            "competitor": c.get("competitor", ""),
            "position": c.get("position", ""),
            "strategy": c.get("st_strategy") or c.get("strategy") or "",
        }
        for c in (plan.get("competitor_landscape") or [])[:4]
        if c.get("competitor")
    ]

    return {
        "gap_type": gap_type,
        "gap_strategy": strategy,
        "priority_label": priority_item.get("priority", ""),
        "st_current_strength": priority_item.get("st_current_strength"),
        "winnability": priority_item.get("winnability"),
        "strategic_importance": priority_item.get("strategic_importance"),
        "ai_perception_summary": str(plan.get("ai_perception_summary") or "")[:600],
        "competitor_landscape": landscape,
        "diagnosis_excerpt": _diagnosis_excerpt(
            campaign_data, priority_item.get("question_id", "")
        ),
    }


def _build_variables(
    campaign_data: dict,
    content_item: dict,
    *,
    question_id: str,
    anchor_point: str,
    subject_fallback: str = "",
    format_override: str | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, str, str, bool, int]:
    """Resolve the template for a content item and build its Jinja2 variables.

    Shared by plan-derived and custom content — they differ only in where the
    item, question id, and anchor come from.

    Returns:
        (variables, format_str, template_name, task_key, needs_keywords)
    """
    # An explicit override wins: it is how the user answers the 422 raised when
    # the stored format names no channel we can write for.
    format_str = format_override or content_item.get("format", "")
    if not format_str:
        raise UnknownFormatError("")

    resolved = _resolve_format(format_str)
    template_name = str(resolved["template_name"])
    task_key = str(resolved["task_key"])
    needs_keywords = bool(resolved["needs_keywords"])
    max_tokens = int(resolved["max_tokens"])

    brief = campaign_data.get("brief", {})
    lang = campaign_data.get("language", "zh")

    persona = _find_persona(
        campaign_data.get("personas", []),
        content_item.get("target_persona_id", ""),
        language=lang,
    )

    # Question text is the subject matter; fall back to the anchor when the
    # question is missing (custom items may have no question at all).
    question_text = _find_question(campaign_data.get("questions", []), question_id)
    if not question_text:
        question_text = subject_fallback or anchor_point

    variables: dict[str, Any] = {
        "brief": brief,
        "persona": persona,
        "anchor_point": anchor_point,
        "question_text": question_text,
    }
    if needs_keywords:
        variables["keywords"] = brief.get("keywords", [])

    variables["content_brief"] = (
        content_item.get("content_brief", "")
        or content_item.get("llm_prompt", "")       # legacy plans
        or content_item.get("topic", "")            # custom items
    )
    variables["data_assets"] = campaign_data.get("data_assets", [])

    # Persona-derived context. Still sliced to keep the prompt bounded, but the
    # fields a writer actually argues from — decision criteria, trusted sources,
    # proof points — were missing entirely.
    p = persona or {}
    variables["persona_pain_points"] = p.get("pain_points", [])[:4]
    variables["persona_vp_headline"] = p.get("vp_headline", "")
    variables["persona_vp_argument"] = p.get("vp_argument", "")
    variables["persona_objections"] = p.get("objections", [])[:3]
    variables["persona_search_queries"] = p.get("search_queries", [])[:5]
    variables["persona_info_channels"] = p.get("info_channels", [])[:3]
    variables["persona_decision_criteria"] = p.get("decision_criteria", [])[:5]
    variables["persona_trusted_sources"] = p.get("trusted_sources", [])[:4]
    variables["persona_daily_tasks"] = p.get("daily_tasks", [])[:3]
    variables["persona_tech_depth"] = p.get("tech_depth", "")
    variables["persona_funnel_stage"] = p.get("funnel_stage", "")
    variables["persona_decision_role"] = p.get("decision_role", "")
    variables["persona_vp_proof_points"] = p.get("vp_proof_points", [])[:5]
    variables["persona_vp_competitor_comparison"] = p.get("vp_competitor_comparison", {})

    # What the GEO diagnosis established about this question.
    variables["diagnostic"] = diagnostic or {}

    return variables, format_str, template_name, task_key, needs_keywords, max_tokens


def _build_content_variables(
    campaign_data: dict,
    priority_index: int,
    content_index: int,
    format_override: str | None = None,
) -> tuple[dict[str, Any], dict, str, str, str, int]:
    """Build variables for a plan-derived content item.

    Returns:
        (variables, content_item, format_str, template_name, task_key, max_tokens)
    """
    plan = campaign_data.get("plan", {})
    if not plan:
        raise ValueError("No plan data found — generate a Campaign Plan first")

    priorities = plan.get("priorities", [])
    if priority_index < 0 or priority_index >= len(priorities):
        raise ValueError(f"priority_index {priority_index} out of range (0-{len(priorities) - 1})")

    priority_item = priorities[priority_index]
    lang = campaign_data.get("language", "zh")
    content_plan = priority_item.get("content_plan", [])
    if content_index < 0 or content_index >= len(content_plan):
        raise ValueError(
            f"content_index {content_index} out of range (0-{len(content_plan) - 1})"
        )

    content_item = content_plan[content_index]
    variables, format_str, template_name, task_key, needs_keywords, max_tokens = _build_variables(
        campaign_data,
        content_item,
        question_id=priority_item.get("question_id", ""),
        anchor_point=priority_item.get("anchor_point", ""),
        format_override=format_override,
        diagnostic=_diagnostic_context(campaign_data, priority_item, lang),
    )
    return variables, content_item, format_str, template_name, task_key, max_tokens


def _render_prompt(
    variables: dict[str, Any],
    template_name: str,
    format_str: str,
    language: str,
) -> dict[str, Any]:
    """Render a content template with the router's Jinja2 environment."""
    from app.services.llm_router import _jinja_env

    try:
        tmpl = _jinja_env.get_template(f"{language}/{template_name}")
    except Exception as e:
        raise ValueError(
            f"Template '{template_name}' not found for language '{language}'. "
            f"This channel may not support the current campaign language."
        ) from e

    return {
        "prompt": tmpl.render(**variables),
        "template": template_name,
        "format": format_str,
        "language": language,
    }


async def _generate(
    campaign_data: dict,
    variables: dict[str, Any],
    content_item: dict,
    format_str: str,
    template_name: str,
    task_key: str,
    language: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    """Route a content item through the LLM and run the post-generation checks."""
    logger.info(
        "Generating content: format=%s → template=%s, task=%s",
        format_str,
        template_name,
        task_key,
    )

    channel_fit_warning = check_channel_fit(
        variables["persona"], content_item.get("channel", ""), language
    )

    result = await llm_router.route_and_generate(
        task=task_key,
        prompt_name=template_name,
        variables=variables,
        language=language,
        max_tokens=max_tokens,
    )

    truncated = _truncation_warning(result.get("finish_reason", ""), max_tokens, language)
    if truncated:
        logger.warning(
            "Content generation hit the %d-token ceiling (format=%s, model=%s)",
            max_tokens, format_str, result["model"],
        )

    return {
        "text": result["text"],
        "truncated": bool(truncated),
        "truncation_warning": truncated,
        "max_tokens": max_tokens,
        "model": result["model"],
        "format": format_str,
        "template": template_name,
        "channel_fit_warning": channel_fit_warning,
        "risk_scan": scan_content_risks(
            result["text"], campaign_data.get("data_assets", []), language
        ),
    }


def compose_prompt(
    campaign_data: dict,
    priority_index: int,
    content_index: int,
    language: str = "zh",
    format_override: str | None = None,
) -> dict[str, Any]:
    """Compose the full prompt for a content item WITHOUT calling the LLM.

    Returns the rendered prompt as it would be sent to the model, along with
    metadata about the template and format used.
    """
    variables, _item, format_str, template_name, _task, _budget = \
        _build_content_variables(campaign_data, priority_index, content_index, format_override)
    return _render_prompt(variables, template_name, format_str, language)


async def generate_content(
    campaign_data: dict,
    priority_index: int,
    content_index: int,
    language: str = "zh",
    format_override: str | None = None,
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
    variables, content_item, format_str, template_name, task_key, max_tokens = \
        _build_content_variables(campaign_data, priority_index, content_index, format_override)
    return await _generate(
        campaign_data, variables, content_item,
        format_str, template_name, task_key, language, max_tokens,
    )


# ── Custom Content (user-added, not plan-derived) ──


def new_custom_id() -> str:
    """Mint a stable identifier for a custom content item."""
    return f"cc_{uuid.uuid4().hex[:12]}"


def ensure_custom_ids(custom_items: list[dict]) -> bool:
    """Backfill ids on legacy custom items. Returns True if anything changed.

    Call this inside a write path (under the campaign lock) so older campaigns
    pick up stable ids the first time they are touched.
    """
    changed = False
    for item in custom_items:
        if isinstance(item, dict) and not item.get("id"):
            item["id"] = new_custom_id()
            changed = True
    return changed


def resolve_custom_index(custom_items: list[dict], content_key: str | int) -> int:
    """Resolve a custom content item to its current list index.

    Items are addressed by their stable `id`. A purely numeric key is accepted
    as a positional fallback for campaigns created before ids existed —
    positional addressing is what let a delete shift every later item out from
    under the buttons already rendered in the browser.
    """
    key = str(content_key)

    for i, item in enumerate(custom_items):
        if isinstance(item, dict) and item.get("id") and item["id"] == key:
            return i

    if key.lstrip("-").isdigit():
        idx = int(key)
        if 0 <= idx < len(custom_items):
            return idx
        raise ValueError(
            f"content_index {idx} out of range (0-{len(custom_items) - 1})"
        )

    raise ValueError(f"Custom content item '{key}' not found")


def build_custom_content_variables(
    campaign_data: dict,
    content_key: str | int,
    format_override: str | None = None,
) -> tuple[dict[str, Any], dict, str, str, str, int]:
    """Build variables for a user-added custom content item.

    `content_key` is the item's stable id (or a positional index for campaigns
    created before ids existed).
    """
    custom_content = campaign_data.get("custom_content", [])
    item = custom_content[resolve_custom_index(custom_content, content_key)]

    variables, format_str, template_name, task_key, needs_keywords, max_tokens = _build_variables(
        campaign_data,
        item,
        question_id=item.get("question_id", ""),
        anchor_point=item.get("anchor_point", "") or item.get("topic", ""),
        subject_fallback=item.get("topic", ""),
        format_override=format_override,
    )
    return variables, item, format_str, template_name, task_key, max_tokens


def compose_custom_prompt(
    campaign_data: dict,
    content_key: str | int,
    language: str = "zh",
    format_override: str | None = None,
) -> dict[str, Any]:
    """Compose the full prompt for a custom content item without calling the LLM."""
    variables, _item, format_str, template_name, _task, _budget = \
        build_custom_content_variables(campaign_data, content_key, format_override)
    return _render_prompt(variables, template_name, format_str, language)


async def generate_custom_content(
    campaign_data: dict,
    content_key: str | int,
    language: str = "zh",
    format_override: str | None = None,
) -> dict[str, Any]:
    """Generate content for a custom content item via LLM."""
    variables, item, format_str, template_name, task_key, max_tokens = \
        build_custom_content_variables(campaign_data, content_key, format_override)
    return await _generate(
        campaign_data, variables, item,
        format_str, template_name, task_key, language, max_tokens,
    )
