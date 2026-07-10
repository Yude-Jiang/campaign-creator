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
