"""Shared JSON parsing utilities for LLM output.

LLMs frequently return JSON wrapped in markdown code blocks, with trailing
commas, or truncated mid-generation. This module provides robust extraction
and recovery that all services share.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)


def extract_json_block(text: str) -> str:
    """Extract the first JSON block from LLM output.

    Tries in order:
    1. ```json ... ``` fenced block
    2. ``` ... ``` (no language spec)
    3. Raw {...} anywhere in text
    4. Return text as-is if nothing found
    """
    # Try ```json ... ``` first
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    # Try ``` ... ``` (no language spec)
    match = re.search(r"```\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    # Try to find a JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0).strip()
    return text.strip()


def _close_truncated_json(text: str) -> str | None:
    """Attempt to close truncated JSON by counting brackets.

    Strategy: count open brackets, append needed closing brackets.
    Only strip back to a boundary if the text ends mid-token (trailing
    comma or incomplete key/value that would create a syntax error).
    """
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    if open_braces <= 0 and open_brackets <= 0:
        return None

    closing = "]" * open_brackets + "}" * open_braces
    trimmed = text.rstrip()

    # Clean cut: ends with structural character or completed token
    if trimmed.endswith((",", "[", "{", "}", "]", '"')):
        if trimmed.endswith(","):
            trimmed = trimmed[:-1].rstrip()  # strip trailing comma
        return trimmed + closing

    # Ends mid-token (number, bare word, incomplete string).
    # Try just closing first — many truncations are syntactically valid
    # up to the cut point and only need closing brackets.
    candidate = trimmed + closing
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        pass

    # Closing wasn't enough — strip back to last valid structural boundary
    last_comma = trimmed.rfind(",")
    cut_point = last_comma
    if cut_point < 0:
        # No comma to strip to — try removing the last incomplete fragment
        # by finding the last space before a value
        last_space = trimmed.rfind(" ")
        if last_space > 0:
            cut_point = last_space
        else:
            return None

    trimmed = trimmed[:cut_point].rstrip()
    if trimmed.endswith(","):
        trimmed = trimmed[:-1].rstrip()
    return trimmed + closing


def safe_parse_json(text: str) -> dict:
    """Parse JSON from LLM output with progressive recovery.

    Attempts:
    1. Direct parse after block extraction
    2. Strip trailing commas and retry
    3. Attempt truncated JSON recovery (close open brackets)
    4. Return {} on total failure
    """
    try:
        return json.loads(extract_json_block(text))
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON from LLM output: %s", e)

    cleaned = extract_json_block(text)
    # Remove trailing commas before closing brackets/braces
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fix missing commas between key-value pairs (common LLM output error:
    # a value followed by newline and next key, but comma omitted)
    cleaned = re.sub(r'(["}\]\d])\s*\n\s*"', r'\1,\n"', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try truncated JSON recovery
    logger.warning("Attempting truncated JSON recovery...")
    try:
        recovered = _close_truncated_json(cleaned)
        if recovered:
            return json.loads(recovered)
    except json.JSONDecodeError:
        pass

    logger.error("Could not recover JSON from LLM output. Raw: %s", text[:500])
    return {}


# ── Anchor Specificity Validation ──
# NOTE: The model-token regex [A-Z][A-Z0-9]+ assumes English alphanumeric product
# naming (e.g., "P3E", "S32G"). Pure-Chinese product names (e.g., "骁龙8Gen3")
# or mixed-script names may not match. This is an acceptable simplification for the
# initial rollout — if usage expands to non-semiconductor industries, this regex
# should be reviewed and potentially parameterized by industry convention.

_GENERIC_ANCHOR_PATTERNS_ZH = [
    re.compile(r"通过(技术文章|白皮书|合作新闻|内容)"),
    re.compile(r"加强(可见度|认知|影响力)"),
    re.compile(r"提升(品牌|行业|市场)"),
    re.compile(r"^(创新者|领导者|领先的|高性能)$"),
]

_GENERIC_ANCHOR_PATTERNS_EN = [
    re.compile(
        r"(strengthen|enhance|improve|boost|increase)\s+(visibility|awareness|presence|influence|recognition)",
        re.IGNORECASE,
    ),
    re.compile(
        r"through\s+(technical\s+articles|whitepapers|partner\s+news|content\s+marketing)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(innovator|leader|industry[- ]leading|best[- ]in[- ]class|market[- ]leading)$",
        re.IGNORECASE,
    ),
]


def check_anchor_specificity(anchor: str, language: str = "zh") -> dict:
    """Check if an anchor_point is generic. Returns {'ok': bool, 'warning': str}.

    Advisory-only — does not block plan generation. Hit-rate data is collected
    via the returned warning to inform future decisions about upgrading to a
    hard block.
    """
    if not anchor or len(anchor) < 20:
        return {"ok": False, "warning": "anchor_point too short or empty"}

    patterns = _GENERIC_ANCHOR_PATTERNS_EN if language == "en" else _GENERIC_ANCHOR_PATTERNS_ZH
    for pat in patterns:
        if pat.search(anchor):
            return {
                "ok": False,
                "warning": f"anchor_point appears generic: '{anchor[:80]}...'",
            }

    # Check for product/model reference (see NOTE above about naming assumption)
    if not re.search(r"[A-Z][A-Z0-9]+", anchor):
        return {
            "ok": False,
            "warning": f"anchor_point lacks product/model reference: '{anchor[:80]}...'",
        }

    return {"ok": True, "warning": ""}
