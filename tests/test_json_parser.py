"""Tests for shared JSON parsing utilities — the pipeline choke point."""

import pytest
from app.utils.json_parser import extract_json_block, safe_parse_json, _close_truncated_json


class TestExtractJsonBlock:
    def test_fenced_json_block(self):
        text = 'some text\n```json\n{"a": 1}\n```\nmore text'
        assert extract_json_block(text) == '{"a": 1}'

    def test_fenced_no_language(self):
        text = '```\n{"b": 2}\n```'
        assert extract_json_block(text) == '{"b": 2}'

    def test_bare_json_object(self):
        text = 'here is {"key": "value"} in text'
        assert extract_json_block(text) == '{"key": "value"}'

    def test_no_json_returns_raw(self):
        text = 'just some plain text'
        assert extract_json_block(text) == 'just some plain text'

    def test_nested_braces(self):
        text = '```json\n{"outer": {"inner": [1,2,3]}}\n```'
        assert extract_json_block(text) == '{"outer": {"inner": [1,2,3]}}'

    def test_multiple_json_blocks_returns_first(self):
        text = '```json\n{"first": 1}\n```\n```json\n{"second": 2}\n```'
        assert extract_json_block(text) == '{"first": 1}'

    def test_whitespace_around_block(self):
        text = '  ```json  \n  {"x": 1}  \n  ```  '
        assert extract_json_block(text) == '{"x": 1}'

    def test_array_in_json(self):
        text = '```json\n[1, 2, 3]\n```'
        assert extract_json_block(text) == '[1, 2, 3]'

    def test_empty_string(self):
        assert extract_json_block("") == ""


class TestSafeParseJson:
    def test_valid_json(self):
        assert safe_parse_json('{"a": 1, "b": "hello"}') == {"a": 1, "b": "hello"}

    def test_json_in_fenced_block(self):
        text = '```json\n{"key": [1,2,3]}\n```'
        assert safe_parse_json(text) == {"key": [1, 2, 3]}

    def test_trailing_comma_in_object(self):
        text = '```json\n{"a": 1, "b": 2,}\n```'
        assert safe_parse_json(text) == {"a": 1, "b": 2}

    def test_trailing_comma_in_array(self):
        text = '{"items": [1, 2, 3,]}'
        assert safe_parse_json(text) == {"items": [1, 2, 3]}

    def test_no_json_returns_empty(self):
        text = 'this is not json at all'
        assert safe_parse_json(text) == {}

    def test_empty_string_returns_empty(self):
        assert safe_parse_json("") == {}

    def test_truncated_object_closes_braces(self):
        """Truncation: object started but never closed."""
        text = '{"question_id": "q1", "priority": "P0"'
        result = safe_parse_json(text)
        assert result["question_id"] == "q1"
        assert result["priority"] == "P0"

    def test_truncated_array_closes_brackets(self):
        """Truncation: array started but never closed."""
        text = '{"items": [1, 2, 3'
        result = safe_parse_json(text)
        assert result["items"] == [1, 2, 3]

    def test_truncated_mid_string(self):
        """Truncation: cut off in the middle of a value."""
        text = '{"a": 1, "b": "hell'
        # Should recover at least the complete field
        result = safe_parse_json(text)
        assert result.get("a") == 1

    def test_nested_truncated(self):
        """Truncation: nested object cut off."""
        text = '{"outer": {"inner": [1, 2'
        result = safe_parse_json(text)
        assert "outer" in result
        assert result["outer"]["inner"] == [1, 2]

    def test_complex_campaign_output(self):
        """Realistic: campaign plan partial output. Multi-level truncation
        with nested objects+arrays is inherently ambiguous — partial recovery
        (1 of 2 priorities) is acceptable."""
        text = '''```json
{
  "ai_perception_summary": "ST has weak presence in ZCU discussions",
  "priorities": [
    {
      "question_id": "q1",
      "priority": "P0",
      "strategic_importance": 5
    },
    {
      "question_id": "q3",
      "priority": "P1",
      "st_current_strength": 2
'''
        result = safe_parse_json(text)
        assert result["ai_perception_summary"].startswith("ST has")
        # At minimum, the first priority must be recovered
        assert len(result["priorities"]) >= 1
        assert result["priorities"][0]["priority"] == "P0"

    def test_missing_comma_between_fields(self):
        """Common LLM error: missing comma between key-value pairs."""
        text = '''```json
{
  "ai_perception_summary": "ST has weak presence",
  "priorities": [
    {
      "question_id": "q1",
      "priority": "P0"
    }
  ]
  "competitor_landscape": [
    {"competitor": "NXP", "position": "leader"}
  ]
}
```'''
        result = safe_parse_json(text)
        assert result["ai_perception_summary"] == "ST has weak presence"
        assert len(result["priorities"]) == 1
        assert len(result["competitor_landscape"]) == 1
        assert result["competitor_landscape"][0]["competitor"] == "NXP"

    def test_missing_comma_between_top_level_keys(self):
        """Simpler case: two top-level keys missing comma between them."""
        text = '{"a": 1\n"b": 2}'
        result = safe_parse_json(text)
        assert result == {"a": 1, "b": 2}


class TestCloseTruncatedJson:
    def test_no_open_brackets_returns_none(self):
        assert _close_truncated_json('{"a": 1}') is None

    def test_single_open_brace(self):
        result = _close_truncated_json('{"a": 1')
        assert result == '{"a": 1}'

    def test_trailing_comma_stripped(self):
        result = _close_truncated_json('{"a": 1,')
        assert result == '{"a": 1}'

    def test_mid_string_cut(self):
        """Cut in the middle of an incomplete value."""
        result = _close_truncated_json('{"a": 1, "b": "unfinished')
        assert result is not None
        assert result.startswith('{"a": 1')

    def test_empty_input(self):
        assert _close_truncated_json("") is None
