"""Tests for utility functions — file_handler validation, slugify, etc."""

import pytest
from app.utils.file_handler import validate_campaign_id


class TestValidateCampaignId:
    def test_valid_ascii(self):
        assert validate_campaign_id("my-campaign-2024") == "my-campaign-2024"

    def test_valid_cjk(self):
        assert validate_campaign_id("测试活动") == "测试活动"

    def test_valid_underscore(self):
        assert validate_campaign_id("test_campaign_v2") == "test_campaign_v2"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_campaign_id("")

    def test_dot_dot_raises(self):
        with pytest.raises(ValueError, match="must not contain '..'"):
            validate_campaign_id("../../etc/passwd")

    def test_slash_raises(self):
        with pytest.raises(ValueError, match="must not contain path separators"):
            validate_campaign_id("foo/bar")

    def test_backslash_raises(self):
        with pytest.raises(ValueError, match="must not contain path separators"):
            validate_campaign_id("foo\\bar")

    def test_null_byte_raises(self):
        with pytest.raises(ValueError, match="must not contain null bytes"):
            validate_campaign_id("test\x00inject")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="too long"):
            validate_campaign_id("x" * 200)

    def test_unsafe_chars_raises(self):
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_campaign_id("rm -rf")

    def test_at_sign_raises(self):
        """@ is not in the safe character set."""
        with pytest.raises(ValueError, match="unsafe characters"):
            validate_campaign_id("test@campaign")


class TestSlugify:
    """Test the _slugify helper via the campaign API module."""

    def test_basic_chinese(self):
        from app.api.campaign import _slugify
        assert "测试活动" in _slugify("测试活动")

    def test_english(self):
        from app.api.campaign import _slugify
        assert _slugify("My Campaign 2024") == "my-campaign-2024"

    def test_special_chars_stripped(self):
        from app.api.campaign import _slugify
        slug = _slugify("Hello! @World #2024")
        assert "!" not in slug
        assert "@" not in slug
        assert "#" not in slug

    def test_multiple_hyphens_collapsed(self):
        from app.api.campaign import _slugify
        assert _slugify("a---b") == "a-b"

    def test_empty_returns_untitled(self):
        from app.api.campaign import _slugify
        assert _slugify("!!!") == "untitled"
