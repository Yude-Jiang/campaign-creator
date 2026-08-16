"""Regression guards — automated checks for bug patterns that have slipped through.

These tests encode patterns that caused production bugs:
  1. Template context mismatch:  {{ brief.xxx }} in HTML templates (should be campaign.brief.xxx)
  2. Tab index out of sync:       API validator not updated when tabs were added
  3. Residual hardcoded brand:    "ST" / "STMicroelectronics" left after de-spec pass

Each test class corresponds to one bug class we've shipped and fixed.
"""

import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from starlette.testclient import TestClient

# ═══════════════════════════════════════════════════════════
# Project root
# ═══════════════════════════════════════════════════════════
ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
APP_DIR = ROOT / "app"
STATIC_DIR = ROOT / "static"

# ═══════════════════════════════════════════════════════════
# Shared: minimal mock campaign for template rendering
# ═══════════════════════════════════════════════════════════

MOCK_BRIEF = {
    "name": "Test Campaign",
    "topic": "MCU Security",
    "target_page_url": "https://example.com/product",
    "products": ["Product X", "Product Y"],
    "keywords": ["security", "mcu"],
    "competitors_known": ["NXP", "Renesas"],
    "materials": [],
    "goal": "Brand awareness",
    "notes": "",
    "industry": "半导体",
    "language": "zh",
}

MOCK_CAMPAIGN = {
    "campaign_id": "test-campaign",
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
    "language": "zh",
    "brief": MOCK_BRIEF,
    "personas": [
        {
            "id": "p1",
            "name": "MCU 系统架构师",
            "layer": "chip/solution",
            "tech_depth": "deep",
            "decision_weight": "decision_maker",
            "pain_points": ["功耗", "实时性"],
            "info_channels": ["知乎", "CSDN"],
            "search_queries": ["MCU 选型", "汽车芯片安全"],
            "objections": ["价格高"],
            "vp_headline": "最高安全等级的 MCU",
            "vp_argument": "硬件隔离架构",
            "vp_competitor_comparison": {"NXP S32G": "硬件隔离 vs 外部 SBC", "Renesas RH850": "单芯片多通道"},
        },
    ],
    "questions": [
        {
            "id": "q1",
            "text": "汽车 MCU 的安全性如何评估？",
            "category": "concept",
            "diagnostic_value": "high",
            "search_intent": "选购指南",
            "search_volume_estimate": "1k-5k",
            "related_questions": ["ASIL 等级怎么选？"],
        },
    ],
    "diagnoses": {
        "q1": {
            "question_id": "q1",
            "raw_text": "根据分析，Test Campaign 在安全 MCU 领域排名第2...",
        },
    },
    "data_assets": [
        {
            "claim": "Product X 集成 6x Cortex-R52",
            "source": "datasheet rev3 p.12",
            "verified_by": "test",
            "added_at": "2026-01-01",
        },
    ],
    "plan": {
        "ai_perception_summary": "品牌在安全 MCU 领域有一定认知...",
        "inverted_pyramid": {
            "q1": {"strength": "moderate", "perception_tier": "solution", "summary": "排名第2"},
        },
        "competitor_landscape": [
            {
                "question_id": "q1",
                "competitors": [
                    {
                        "name": "NXP",
                        "product": "S32G",
                        "position": "leader",
                        "mention_context": "NXP S32G 是默认选择",
                    },
                ],
                "st_opportunity": "Product X 的硬件隔离架构可减少 BOM 成本",
            },
        ],
        "gap_analysis": [
            {
                "question_id": "q1",
                "gap_type": "rival_owned",
                "evidence": "NXP 被推荐为默认选择",
                "recommended_anchor": "Product X 硬件隔离 vs NXP S32G 的安全性对比",
            },
        ],
        "priorities": [
            {
                "question_id": "q1",
                "question_text": "汽车 MCU 的安全性如何评估？",
                "strategic_importance": 5,
                "st_current_strength": 2,
                "winnability": 4,
                "priority": "P0",
                "rationale": "核心差异化战场",
                "anchor_point": "Product X 硬件隔离架构实现 ASIL-D",
                "content_plan": [
                    {
                        "format": "知乎长文",
                        "channel": "技术博客",
                        "topic": "MCU 安全架构深度解析",
                        "target_persona_id": "p1",
                        "title_suggestion": "从 ASIL-B 到 ASIL-D：MCU 安全架构的演进",
                        "anchor_point": "Product X 硬件隔离架构",
                        "generated_content": "",
                    },
                ],
                "timeline": {
                    "phase_1_cold_start": "Publish anchor blog post",
                    "phase_2_niche_authority": "Publish comparison with NXP",
                    "phase_3_industry_presence": "Publish guest post on industry media",
                    "phase_4_maintenance": "Update with latest benchmarks",
                },
                "metrics": {
                    "primary": {"kpi": "AI 召回率", "target": "从 moderate 到 strong", "tool": "GEO-hub"},
                },
            },
        ],
        "content_strategy_summary": "通过技术深度内容建立安全 MCU 认知...",
    },
    "current_tab": 3,
}

# Sorted priorities for Content Studio template
MOCK_SORTED_PRIORITIES = [
    {
        "question_id": "q1",
        "question_text": "汽车 MCU 的安全性如何评估？",
        "priority": "P0",
        "gap_type": "rival_owned",
        "anchor_point": "Product X 硬件隔离架构实现 ASIL-D",
        "content_plan": [
            {
                "format": "知乎长文",
                "channel": "技术博客",
                "topic": "MCU 安全架构深度解析",
                "target_persona_id": "p1",
                "title_suggestion": "从 ASIL-B 到 ASIL-D：MCU 安全架构的演进",
                "anchor_point": "Product X 硬件隔离架构",
                "generated_content": "",
                "_fit_warning": "",
            },
        ],
    },
]

MOCK_PERSONA_MAP = {"p1": MOCK_CAMPAIGN["personas"][0]}

MOCK_CUSTOM_CONTENT = [
    {
        "_custom": True,
        "format": "email",
        "channel": "邮件",
        "channel_type": "organic",
        "target_persona_id": "p1",
        "title_suggestion": "Test Custom Email",
        "topic": "Custom email for testing",
        "anchor_point": "Custom email for testing",
        "content_brief": "Custom email for testing",
        "question_id": "q1",
        "created_at": "2026-01-01T00:00:00",
        "generated_content": "",
        "generated_model": "",
        "generated_at": "",
    },
]

MOCK_FORMAT_OPTIONS = [
    {"key": "zhihu_long", "label_zh": "知乎长文", "label_en": "Zhihu Long-Form", "channel": "知乎", "channel_type": "organic"},
    {"key": "email", "label_zh": "邮件培育序列", "label_en": "Email Nurture", "channel": "邮件", "channel_type": "organic"},
    {"key": "baidu_sem", "label_zh": "百度竞价广告", "label_en": "Baidu SEM", "channel": "百度竞价", "channel_type": "paid"},
]


def _mock_request():
    """Create a minimal mock Starlette Request."""
    req = Mock()
    req.headers = {}
    req.query_params = {}
    req.path_params = {}
    req.url = Mock()
    req.url.path = "/campaigns/test-campaign"
    req.url.scheme = "https"
    req.url.hostname = "campaign-factory.example.com"
    req.url.port = 443
    req.url.query = ""
    req.url.__str__ = lambda self: "https://campaign-factory.example.com/campaigns/test-campaign"
    return req


def _build_page_context(template_name: str, **extra) -> dict:
    """Build the minimal context that page_context() would provide for rendering."""
    from app.api import build_tabs, page_context

    extra.setdefault("tabs", build_tabs([False] * EXPECTED_TAB_COUNT))
    extra.setdefault("active_tab", 3)
    extra.setdefault("campaign", MOCK_CAMPAIGN)
    extra.setdefault("campaign_id", "test-campaign")
    return page_context(_mock_request(), language="zh", **extra)


# ═══════════════════════════════════════════════════════════
# Guard 1: Template Variable Smoke Test
# ═══════════════════════════════════════════════════════════

HTML_TEMPLATES = [
    "tab_brief.html",
    "tab_persona.html",
    "tab_diagnosis.html",
    "tab_plan.html",
    "tab_content_studio.html",
]


class TestTemplateContextSmoke:
    """Every HTML template must render without UndefinedError given a realistic context.

    Regression for:  {{ brief.name }} in HTML templates (should be campaign.brief.name).
    When LLM prompt de-spec replaced "ST" → "{{ brief.name }}", some HTML templates
    got the same treatment, but HTML templates receive `campaign`, not `brief`.
    """

    def test_brief_template_renders(self):
        """Tab 0: Brief — needs campaign_id (None for homepage), tabs, language, request."""
        from app.api import page_context
        from app.api.pages import templates as starlette_templates

        ctx = page_context(
            _mock_request(),
            language="zh",
            tabs=[
                {"num": "0", "label": "Brief", "id": "tab-brief", "disabled": False},
                {"num": "1", "label": "Persona & Questions", "id": "tab-persona", "disabled": True},
                {"num": "2", "label": "GEO Diagnosis", "id": "tab-diagnosis", "disabled": True},
                {"num": "3", "label": "Campaign Plan", "id": "tab-plan", "disabled": True},
                {"num": "4", "label": "Content Studio", "id": "tab-content", "disabled": True},
            ],
            campaign_id=None,
        )
        # Should not raise
        starlette_templates.get_template("tab_brief.html").render(ctx)

    def test_persona_template_renders(self):
        """Tab 1: Persona & Questions — needs campaign with personas, questions."""
        from app.api.pages import templates as starlette_templates

        ctx = _build_page_context("tab_persona.html")
        starlette_templates.get_template("tab_persona.html").render(ctx)

    def test_diagnosis_template_renders(self):
        """Tab 2: GEO Diagnosis — needs campaign with diagnoses."""
        from app.api.pages import templates as starlette_templates

        ctx = _build_page_context("tab_diagnosis.html")
        starlette_templates.get_template("tab_diagnosis.html").render(ctx)

    def test_plan_template_renders(self):
        """Tab 3: Campaign Plan — needs campaign with plan data."""
        from app.api.pages import templates as starlette_templates

        ctx = _build_page_context("tab_plan.html")
        starlette_templates.get_template("tab_plan.html").render(ctx)

    def test_content_studio_template_renders(self):
        """Tab 4: Content Studio — needs campaign, sorted_priorities, persona_map, custom_content, format_options."""
        from app.api.pages import templates as starlette_templates

        ctx = _build_page_context(
            "tab_content_studio.html",
            sorted_priorities=MOCK_SORTED_PRIORITIES,
            persona_map=MOCK_PERSONA_MAP,
            custom_content=MOCK_CUSTOM_CONTENT,
            format_options=MOCK_FORMAT_OPTIONS,
        )
        starlette_templates.get_template("tab_content_studio.html").render(ctx)

    def test_all_templates_render_with_minimal_context(self):
        """Bulk guard: every HTML template must render with the campaign context."""
        from app.api.pages import templates as starlette_templates

        for filename in HTML_TEMPLATES:
            extra = {}
            if filename == "tab_content_studio.html":
                extra = {
                    "sorted_priorities": MOCK_SORTED_PRIORITIES,
                    "persona_map": MOCK_PERSONA_MAP,
                    "custom_content": MOCK_CUSTOM_CONTENT,
                    "format_options": MOCK_FORMAT_OPTIONS,
                }
            ctx = _build_page_context(filename, **extra)
            try:
                starlette_templates.get_template(filename).render(ctx)
            except Exception as e:
                pytest.fail(f"Template {filename} failed to render: {e}")


# ═══════════════════════════════════════════════════════════
# Guard 2: Tab Index Consistency
# ═══════════════════════════════════════════════════════════

# Single source of truth — if you add/remove tabs, update this.
EXPECTED_TAB_COUNT = 5
TAB_INDICES = set(range(EXPECTED_TAB_COUNT))  # {0, 1, 2, 3, 4}


class TestTabIndexConsistency:
    """All tab-related code must agree on the number and range of tabs.

    Regression for:  advance_tab endpoint validated 0-3 but tabs go up to 4.
    Adding a new tab requires coordinated updates across:
      - models/campaign.py     (comment: current_tab range)
      - api/__init__.py        (default_tabs())
      - api/pages.py           (home page tabs, campaign view tabs, template switch)
      - api/campaign.py        (advance_tab validator)
      - static/js/app.js       (client-side navigateToTab has no upper-bound check,
                                 but the server-side check is the enforcement point)
    """

    def test_default_tabs_count(self):
        """default_tabs() must return exactly EXPECTED_TAB_COUNT entries."""
        from app.api import default_tabs

        tabs = default_tabs()
        assert len(tabs) == EXPECTED_TAB_COUNT, (
            f"default_tabs() returned {len(tabs)} tabs, expected {EXPECTED_TAB_COUNT}"
        )
        indices = {int(t["num"]) for t in tabs}
        assert indices == TAB_INDICES, f"Tab indices {indices} don't match expected {TAB_INDICES}"

    def test_tab_definitions_are_the_single_source(self):
        """Tab count/indices are defined once and everything else derives from it."""
        from app.api import MAX_TAB_INDEX, TAB_DEFINITIONS, TAB_TEMPLATES

        assert len(TAB_DEFINITIONS) == EXPECTED_TAB_COUNT
        assert {int(t["num"]) for t in TAB_DEFINITIONS} == TAB_INDICES
        assert MAX_TAB_INDEX == EXPECTED_TAB_COUNT - 1
        assert len(TAB_TEMPLATES) == EXPECTED_TAB_COUNT

    def test_pages_does_not_hardcode_tab_lists(self):
        """pages.py must build tabs via build_tabs(), not inline dict literals.

        The original bug was three divergent copies of the tab list; a literal
        reappearing here means the copies are back.
        """
        pages_src = (APP_DIR / "api" / "pages.py").read_text(encoding="utf-8")
        assert '"num":' not in pages_src, (
            "pages.py contains an inline tab definition — use build_tabs() instead"
        )
        assert "build_tabs(" in pages_src

    def test_advance_tab_validator_derives_from_max_index(self):
        """advance_tab must bound against MAX_TAB_INDEX, not a hardcoded literal."""
        campaign_src = (APP_DIR / "api" / "campaign.py").read_text(encoding="utf-8")
        assert "0 <= tab <= MAX_TAB_INDEX" in campaign_src, (
            "advance_tab should validate against MAX_TAB_INDEX so the bound "
            "cannot drift when a tab is added"
        )
        assert not re.search(r"if not 0 <= tab <= \d+:", campaign_src), (
            "advance_tab still uses a hardcoded upper bound"
        )

    def test_model_comment_matches(self):
        """The comment documenting Campaign.current_tab must list every tab."""
        model_src = (APP_DIR / "models" / "campaign.py").read_text(encoding="utf-8")
        # The comment sits directly above or beside the field; find the "N=Name"
        # enumeration wherever it lives.
        enumerations = re.findall(r"((?:\d+=\w[\w ]*,?\s*)+)", model_src)
        best = max(enumerations, key=lambda c: len(re.findall(r"\d+=", c)), default="")
        tab_refs = re.findall(r"(\d+)=", best)
        assert len(tab_refs) == EXPECTED_TAB_COUNT, (
            f"current_tab comment lists {len(tab_refs)} tabs ({best!r}), "
            f"expected {EXPECTED_TAB_COUNT}"
        )
        assert [int(t) for t in tab_refs] == sorted(TAB_INDICES)

    def test_every_tab_index_maps_to_an_existing_template(self):
        """TAB_TEMPLATES must cover every tab index and point at real files."""
        from app.api import TAB_TEMPLATES

        assert set(range(len(TAB_TEMPLATES))) == TAB_INDICES
        for idx, name in enumerate(TAB_TEMPLATES):
            assert (TEMPLATES_DIR / name).is_file(), (
                f"Tab {idx} maps to {name}, which does not exist"
            )

    def test_js_navigate_calls_within_range(self):
        """No HTML template should call navigateToTab with index >= EXPECTED_TAB_COUNT."""
        for tmpl in TEMPLATES_DIR.glob("*.html"):
            content = tmpl.read_text(encoding="utf-8")
            # Find navigateToTab(N) calls
            calls = re.findall(r"navigateToTab\((\d+)\)", content)
            for call in calls:
                idx = int(call)
                assert idx < EXPECTED_TAB_COUNT, (
                    f"{tmpl.name}: navigateToTab({idx}) exceeds max tab index "
                    f"{EXPECTED_TAB_COUNT - 1}"
                )


# ═══════════════════════════════════════════════════════════
# Guard 3: Forbidden String Scanner
# ═══════════════════════════════════════════════════════════

# Patterns that must NOT appear in HTML templates or Python source
# (except in explicitly whitelisted files/lines)
FORBIDDEN_HTML_PATTERNS = [
    # Hardcoded brand name — should use {{ campaign.brief.name }} or brief.name
    (re.compile(r'\bSTMicroelectronics\b'), "STMicroelectronics"),
    # Standalone "ST" as a brand reference (not part of "TEST", "REST", "FIRST", etc.)
    # This is tricky — we check for patterns like "ST's", "ST 的", "for ST"
    (re.compile(r"\bST's\b"), "ST's"),
    (re.compile(r"\bST 的\b"), "ST 的"),
]

# Whitelist: files allowed to contain hardcoded "ST" (example text in brief form)
WHITELIST_FILES = {"tab_brief.html"}

# Files where "ST" in prompt templates is expected (uses {{ brief.name }}, not hardcoded)
PROMPT_FILES_SKIP = True  # Skip app/prompts/ — they use Jinja2 {{ brief.name }}


class TestForbiddenStrings:
    """No residual hardcoded brand names in HTML templates outside whitelist.

    Regression for:  tab_plan.html line 39 still had "ST's" after de-spec pass.
    The de-spec replace scripts missed some patterns due to slight string variations.
    """

    def test_no_hardcoded_brand_in_html_templates(self):
        """HTML templates must not contain hardcoded ST/STMicroelectronics."""
        for tmpl in TEMPLATES_DIR.glob("*.html"):
            if tmpl.name in WHITELIST_FILES:
                continue
            content = tmpl.read_text(encoding="utf-8")
            for pattern, label in FORBIDDEN_HTML_PATTERNS:
                matches = pattern.findall(content)
                if matches:
                    # Get line numbers for better error messages
                    lines = content.split("\n")
                    line_nums = [
                        i + 1 for i, line in enumerate(lines) if pattern.search(line)
                    ]
                    pytest.fail(
                        f"{tmpl.name}: found forbidden pattern '{label}' "
                        f"on line(s) {line_nums}. "
                        f"Use {{% if language == 'zh' %}} ... {{% endif %}} with "
                        f"{{{{ campaign.brief.name }}}} instead."
                    )

    def test_no_hardcoded_brand_in_python_source(self):
        """Python source must not contain hardcoded brand names in logic (prompts excluded)."""
        for py_file in APP_DIR.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            rel_path = str(py_file.relative_to(ROOT))

            # Skip prompt files
            if "prompts" in rel_path:
                continue

            # Check for STMicroelectronics (very clear violation)
            if "STMicroelectronics" in content:
                pytest.fail(
                    f"{rel_path}: found 'STMicroelectronics'. "
                    f"Use brief.name or campaign.brief.name instead."
                )

            # Check for standalone "ST's" or "ST 的" in string literals
            # (not in variable names like "st_opportunity")
            for pattern, label in [
                (re.compile(r"['\"]ST's['\"]"), "ST's"),
                (re.compile(r"['\"].*?ST 的.*?['\"]"), "ST 的"),
            ]:
                matches = pattern.findall(content)
                if matches:
                    pytest.fail(
                        f"{rel_path}: found hardcoded '{label}' in string literal. "
                        f"Matches: {matches}"
                    )


# ═══════════════════════════════════════════════════════════
# Guard 4: Content Studio completeness
# ═══════════════════════════════════════════════════════════

class TestContentStudioIntegration:
    """Content Studio (Tab 4) must be properly wired end-to-end."""

    def test_tab_4_has_api_endpoint(self):
        """Content Studio needs its API endpoints for content generation."""
        campaign_src = (APP_DIR / "api" / "campaign.py").read_text(encoding="utf-8")
        # Should have content generation endpoint
        assert "content/generate" in campaign_src or "content/studio" in campaign_src, (
            "No Content Studio generation endpoint found in campaign.py"
        )

    def test_tab_4_has_template(self):
        """Content Studio must have its template file."""
        assert (TEMPLATES_DIR / "tab_content_studio.html").exists(), (
            "tab_content_studio.html is missing"
        )

    def test_tab_4_in_nav_enabled_with_plan(self):
        """When plan exists, Content Studio tab must be enabled in the nav."""
        from app.api import page_context

        ctx = page_context(
            _mock_request(),
            language="zh",
            tabs=[
                {"num": "0", "label": "Brief", "id": "tab-brief", "disabled": False},
                {"num": "1", "label": "Persona & Questions", "id": "tab-persona", "disabled": False},
                {"num": "2", "label": "GEO Diagnosis", "id": "tab-diagnosis", "disabled": False},
                {"num": "3", "label": "Campaign Plan", "id": "tab-plan", "disabled": False},
                {"num": "4", "label": "Content Studio", "id": "tab-content", "disabled": False},
            ],
            campaign_id="test-campaign",
            campaign=MOCK_CAMPAIGN,
        )
        # Tab 4 should be present and not disabled
        tab4 = ctx["tabs"][4]
        assert tab4["num"] == "4"
        assert tab4["disabled"] is False, "Content Studio tab should be enabled when plan exists"


# ═══════════════════════════════════════════════════════════
# Guard 5: Custom Content (Phase 4)
# ═══════════════════════════════════════════════════════════

class TestCustomContentAPI:
    """Custom content API endpoints must be wired and reachable."""

    def test_custom_content_endpoints_exist(self):
        """All 5 custom content endpoints must be defined in campaign.py."""
        campaign_src = (APP_DIR / "api" / "campaign.py").read_text(encoding="utf-8")
        endpoints = [
            "/content/formats",
            "/content/custom",
            "/content/custom/compose-prompt",
            "/content/custom/generate",
        ]
        for ep in endpoints:
            assert ep in campaign_src, f"Custom content endpoint '{ep}' not found in campaign.py"

    def test_custom_content_delete_endpoint_exists(self):
        """DELETE endpoint for custom content must exist."""
        campaign_src = (APP_DIR / "api" / "campaign.py").read_text(encoding="utf-8")
        assert 'delete_custom_content' in campaign_src, (
            "DELETE endpoint for custom content not found"
        )

    def test_get_available_formats_filters_by_language(self):
        """get_available_formats() must return only zh formats for zh, en for en."""
        from app.services.content_service import get_available_formats

        zh_formats = get_available_formats("zh")
        en_formats = get_available_formats("en")

        # zh must not include linkedin/bing
        zh_keys = {f["key"] for f in zh_formats}
        assert "linkedin" not in zh_keys, "zh formats should not include LinkedIn"
        assert "bing" not in zh_keys, "zh formats should not include Bing"
        assert "zhihu_long" in zh_keys, "zh formats should include zhihu_long"

        # en must not include zhihu/csdn/bilibili/baidu/wechat
        en_keys = {f["key"] for f in en_formats}
        assert "zhihu_long" not in en_keys, "en formats should not include zhihu"
        assert "csdn" not in en_keys, "en formats should not include CSDN"
        assert "linkedin" in en_keys, "en formats should include LinkedIn"
        assert "email" in en_keys, "en formats should include email (shared)"

    def test_build_custom_content_variables_injects_persona_fields(self):
        """build_custom_content_variables() must inject persona_pain_points, vp_headline, etc."""
        from app.services.content_service import build_custom_content_variables

        campaign_data = dict(MOCK_CAMPAIGN)
        campaign_data["custom_content"] = MOCK_CUSTOM_CONTENT

        variables, item, format_str, template_name, task_key, needs_kw = \
            build_custom_content_variables(campaign_data, 0)

        assert variables["persona_pain_points"] == ["功耗", "实时性"]
        assert variables["persona_vp_headline"] == "最高安全等级的 MCU"
        assert variables["persona_vp_argument"] == "硬件隔离架构"
        assert variables["persona_objections"] == ["价格高"]
        assert variables["persona_search_queries"] == ["MCU 选型", "汽车芯片安全"]
        assert variables["persona_info_channels"] == ["知乎", "CSDN"]

    def test_build_content_variables_injects_persona_fields(self):
        """_build_content_variables() must inject persona-derived fields."""
        from app.services.content_service import _build_content_variables

        variables, item, format_str, template_name, task_key, needs_kw = \
            _build_content_variables(MOCK_CAMPAIGN, 0, 0)

        assert "persona_pain_points" in variables
        assert "persona_vp_headline" in variables
        assert "persona_objections" in variables
        assert variables["persona_vp_headline"] == "最高安全等级的 MCU"

    def test_compose_custom_prompt_renders(self):
        """compose_custom_prompt() must render a valid prompt string."""
        from app.services.content_service import compose_custom_prompt

        campaign_data = dict(MOCK_CAMPAIGN)
        campaign_data["custom_content"] = MOCK_CUSTOM_CONTENT

        result = compose_custom_prompt(campaign_data, 0, language="zh")
        assert "prompt" in result
        assert result["template"] == "content_email.md"
        assert "MCU 系统架构师" in result["prompt"]
        # Audience Intelligence block should be present when persona has fields
        assert "Audience Intelligence" in result["prompt"]

    def test_compose_prompt_includes_audience_intelligence(self):
        """Standard compose_prompt() must include Audience Intelligence block."""
        from app.services.content_service import compose_prompt

        result = compose_prompt(MOCK_CAMPAIGN, 0, 0, language="zh")
        assert "Audience Intelligence" in result["prompt"]
        assert "最高安全等级的 MCU" in result["prompt"]
        assert "功耗" in result["prompt"]

    def test_content_studio_renders_without_custom_content(self):
        """Content Studio must render even with empty custom_content and format_options."""
        from app.api.pages import templates as starlette_templates

        ctx = _build_page_context(
            "tab_content_studio.html",
            sorted_priorities=MOCK_SORTED_PRIORITIES,
            persona_map=MOCK_PERSONA_MAP,
            custom_content=[],
            format_options=[],
        )
        # Should render without error (empty custom content section)
        starlette_templates.get_template("tab_content_studio.html").render(ctx)


# ═══════════════════════════════════════════════════════════
# Bug class 4: Untrusted LLM / upload text rendered as markup
# ═══════════════════════════════════════════════════════════

XSS_PAYLOAD = '<script>alert(1)</script>'


class TestExportHtmlEscaping:
    """Every field in the HTML export originates from LLM output or an uploaded
    diagnosis file. The report is served same-origin, so unescaped markup would
    be stored XSS."""

    def _poisoned_plan(self) -> dict:
        return {
            "campaign_id": XSS_PAYLOAD,
            "generated_at": "2026-01-01T00:00:00",
            "ai_perception_summary": XSS_PAYLOAD,
            "competitor_landscape": [
                {"layer": XSS_PAYLOAD, "competitor": XSS_PAYLOAD,
                 "position": XSS_PAYLOAD, "strategy": XSS_PAYLOAD},
            ],
            "priorities": [
                {
                    "question_id": XSS_PAYLOAD,
                    "question_text": XSS_PAYLOAD,
                    "priority": "P0",
                    "gap_type": XSS_PAYLOAD,
                    "anchor_point": XSS_PAYLOAD,
                    "content_plan": [
                        {"format": XSS_PAYLOAD, "channel": XSS_PAYLOAD,
                         "channel_type": XSS_PAYLOAD, "target_persona_id": XSS_PAYLOAD,
                         "title_suggestion": XSS_PAYLOAD},
                    ],
                },
            ],
            "timeline_90days": [
                {"week": XSS_PAYLOAD,
                 "actions": [{"description": XSS_PAYLOAD, "channel": XSS_PAYLOAD}, XSS_PAYLOAD]},
            ],
            "monitoring_metrics": [
                {"question_id": XSS_PAYLOAD, "expected_recall_position": XSS_PAYLOAD,
                 "keywords": [XSS_PAYLOAD], "target_models": [XSS_PAYLOAD]},
            ],
        }

    def test_no_raw_script_tag_survives_html_export(self):
        from app.services.export_service import export_to_html

        html = export_to_html(
            self._poisoned_plan(),
            {"brief": {"name": XSS_PAYLOAD, "topic": XSS_PAYLOAD}, "questions": [], "diagnoses": []},
        )
        assert XSS_PAYLOAD not in html
        assert "<script>" not in html
        # ...but the text itself must still be visible, escaped
        assert "&lt;script&gt;" in html

    def test_priority_badge_class_is_whitelisted(self):
        """A hostile priority label must not reach the CSS class attribute."""
        from app.services.export_service import _priority_badge

        badge = _priority_badge('P0" onload="alert(1)')
        assert 'onload' not in badge or '&quot;' in badge
        assert badge.startswith('<span class="badge-p2">')

        assert _priority_badge("P1") == '<span class="badge-p1">P1</span>'
        assert _priority_badge(None) == '<span class="badge-p2">P2</span>'

    def test_coverage_shared_between_markdown_and_html(self):
        """Both exports must report identical coverage numbers."""
        from app.services.export_service import export_to_html, export_to_markdown

        plan = {
            "priorities": [
                {"question_id": "q1", "priority": "P0", "content_plan": [{"format": "zhihu_long"}]},
            ],
            "monitoring_metrics": [],
        }
        campaign = {
            "brief": {"name": "C"},
            "questions": [
                {"id": "q1", "diagnostic_value": "high"},
                {"id": "q2", "diagnostic_value": "high"},
                {"id": "q3", "diagnostic_value": "low"},
            ],
            "diagnoses": [{"question_id": "q1"}],
        }
        md = export_to_markdown(plan, campaign)
        html = export_to_html(plan, campaign)
        # 3 total questions, 1 prioritized, 1 of 2 high-value covered
        assert "| Total Questions (all) | 3 |" in md
        assert "<td>Total Questions (all)</td><td>3</td>" in html
        assert "| High-Value Covered | 1 / 2 |" in md
        assert "<td>High-Value Covered</td><td>1 / 2</td>" in html


class TestNoUnsafeInnerHtmlInterpolation:
    """Generated content and upload filenames must go into the DOM as text."""

    JS_SOURCES = ["templates/tab_content_studio.html", "templates/tab_diagnosis.html",
                  "templates/tab_brief.html", "templates/tab_persona.html", "static/js/app.js"]

    # Interpolating any of these into an innerHTML string re-opens the hole.
    FORBIDDEN = ["resp.content", "err.message", "file.name", "errMsg",
                 "resp.risk_scan", "resp.channel_fit_warning"]

    def test_untrusted_values_never_flow_into_innerhtml(self):
        offenders = []
        for rel in self.JS_SOURCES:
            for lineno, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
                if "innerHTML" not in line:
                    continue
                for token in self.FORBIDDEN:
                    if token in line:
                        offenders.append(f"{rel}:{lineno}: {token} in innerHTML assignment")
        assert not offenders, "Untrusted value assigned via innerHTML:\n" + "\n".join(offenders)


class TestTabHighlightTracksActiveTab:
    """The nav strip highlighted `loop.first` instead of the active tab, so the
    Brief tab stayed lit no matter which page you were on."""

    def _render_nav(self, active_tab: int) -> str:
        from app.api import build_tabs
        from app.api.pages import templates as starlette_templates

        ctx = _build_page_context(
            "tab_plan.html",
            tabs=build_tabs([False] * EXPECTED_TAB_COUNT),
            active_tab=active_tab,
        )
        return starlette_templates.get_template("base.html").render(ctx)

    def test_base_template_uses_active_tab_not_loop_first(self):
        base_src = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert "loop.first" not in base_src, (
            "base.html highlights the first tab regardless of the active one"
        )
        assert "active_tab" in base_src

    @pytest.mark.parametrize("active", [0, 1, 2, 3, 4])
    def test_exactly_the_active_tab_is_marked(self, active):
        html = self._render_nav(active)
        buttons = re.findall(r'<button class="tab-btn[^"]*"', html)
        assert len(buttons) == EXPECTED_TAB_COUNT
        marked = [i for i, b in enumerate(buttons) if " active" in b]
        assert marked == [active], (
            f"active_tab={active} highlighted tabs {marked}"
        )

    def test_page_context_defaults_active_tab(self):
        """Templates must never render without active_tab defined."""
        from unittest.mock import Mock

        from app.api import page_context

        ctx = page_context(Mock())
        assert ctx["active_tab"] == 0


class TestCampaignLanguageSwitch:
    """The language toggle rebuilt the URL with ?lang=, but campaign_view always
    overrode it with the stored campaign language — a dead button."""

    def test_language_endpoint_exists_and_persists(self, tmp_path, monkeypatch):
        import app.utils.file_handler as fh
        from app.main import app as fastapi_app

        monkeypatch.setattr(fh, "CAMPAIGNS_DIR", tmp_path / "campaigns")
        client = TestClient(fastapi_app)

        created = client.post("/api/campaigns", json={
            "brief": {"name": "lang-test", "topic": "t", "language": "zh"},
        })
        assert created.status_code == 200
        cid = created.json()["campaign_id"]

        resp = client.put(f"/api/campaigns/{cid}/language", json={"language": "en"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["language"] == "en"

        stored = client.get(f"/api/campaigns/{cid}").json()
        assert stored["language"] == "en"
        assert stored["brief"]["language"] == "en"

    def test_language_endpoint_rejects_unknown_language(self, tmp_path, monkeypatch):
        import app.utils.file_handler as fh
        from app.main import app as fastapi_app

        monkeypatch.setattr(fh, "CAMPAIGNS_DIR", tmp_path / "campaigns")
        client = TestClient(fastapi_app)

        created = client.post("/api/campaigns", json={
            "brief": {"name": "lang-reject", "topic": "t", "language": "zh"},
        })
        cid = created.json()["campaign_id"]

        resp = client.put(f"/api/campaigns/{cid}/language", json={"language": "fr"})
        assert resp.status_code == 422

    def test_client_persists_language_for_campaigns(self):
        """setLanguage must hit the API when a campaign is loaded, not just
        rewrite the query string."""
        js = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
        assert "/language" in js, "setLanguage never calls the language endpoint"
        assert "_campaignId" in js


class TestCustomContentStableAddressing:
    """Custom content was addressed by list position, so deleting an earlier
    item silently retargeted every button already rendered in the browser."""

    def _client(self, tmp_path, monkeypatch):
        import app.utils.file_handler as fh
        from app.main import app as fastapi_app

        monkeypatch.setattr(fh, "CAMPAIGNS_DIR", tmp_path / "campaigns")
        return TestClient(fastapi_app)

    def _make_campaign(self, client) -> str:
        created = client.post("/api/campaigns", json={
            "brief": {"name": "custom-addr", "topic": "t", "language": "zh"},
        })
        assert created.status_code == 200, created.text
        return created.json()["campaign_id"]

    def _add(self, client, cid, topic) -> str:
        resp = client.post(f"/api/campaigns/{cid}/content/custom", json={
            "format": "zhihu_long",
            "target_persona_id": "p1",
            "topic": topic,
        })
        assert resp.status_code == 200, resp.text
        content_id = resp.json()["content_id"]
        assert content_id, "create must return a stable content_id"
        return content_id

    def test_delete_does_not_shift_other_items(self, tmp_path, monkeypatch):
        client = self._client(tmp_path, monkeypatch)
        cid = self._make_campaign(client)

        first = self._add(client, cid, "first")
        second = self._add(client, cid, "second")
        third = self._add(client, cid, "third")
        assert len({first, second, third}) == 3

        # Delete the first item — under positional addressing, `third` would
        # slide from index 2 to index 1.
        resp = client.delete(f"/api/campaigns/{cid}/content/custom/{first}")
        assert resp.status_code == 200, resp.text

        # The id still resolves to the same logical item.
        prompt = client.post(f"/api/campaigns/{cid}/content/custom/compose-prompt",
                             json={"content_id": third})
        assert prompt.status_code == 200, prompt.text
        assert "third" in prompt.json()["prompt"]

        stored = client.get(f"/api/campaigns/{cid}").json()["custom_content"]
        assert [i["topic"] for i in stored] == ["second", "third"]
        assert [i["id"] for i in stored] == [second, third]

    def test_deleting_unknown_id_is_404_not_silent(self, tmp_path, monkeypatch):
        client = self._client(tmp_path, monkeypatch)
        cid = self._make_campaign(client)
        self._add(client, cid, "only")

        resp = client.delete(f"/api/campaigns/{cid}/content/custom/cc_doesnotexist")
        assert resp.status_code == 404

    def test_legacy_positional_key_still_resolves(self, tmp_path, monkeypatch):
        """Campaigns saved before ids existed must keep working."""
        from app.services.content_service import resolve_custom_index

        legacy = [{"topic": "a"}, {"topic": "b"}]
        assert resolve_custom_index(legacy, 0) == 0
        assert resolve_custom_index(legacy, "1") == 1
        with pytest.raises(ValueError):
            resolve_custom_index(legacy, 5)

    def test_id_wins_over_a_numeric_lookalike(self):
        from app.services.content_service import resolve_custom_index

        items = [{"id": "7", "topic": "a"}, {"id": "cc_x", "topic": "b"}]
        # "7" is a real id at position 0 — it must not be read as index 7.
        assert resolve_custom_index(items, "7") == 0

    def test_ensure_custom_ids_backfills_only_missing(self):
        from app.services.content_service import ensure_custom_ids

        items = [{"id": "cc_keep"}, {}, {"id": ""}]
        assert ensure_custom_ids(items) is True
        assert items[0]["id"] == "cc_keep"
        assert items[1]["id"].startswith("cc_")
        assert items[2]["id"].startswith("cc_")
        assert len({i["id"] for i in items}) == 3
        # Idempotent
        assert ensure_custom_ids(items) is False


class TestProviderConfigConsistency:
    """Config drift between code, .env.example, and README shipped a Kimi base
    URL that 404s, and left a dead Claude provider wired into the registry."""

    def test_every_registered_provider_is_routable(self):
        """A provider in the registry that no task routes to is dead code."""
        from app.services.llm_router import PROVIDERS, TASK_ROUTING

        routed = set()
        for routing in TASK_ROUTING.values():
            for slot in ("primary", "secondary", "fallback"):
                if routing.get(slot):
                    routed.add(routing[slot])

        unroutable = set(PROVIDERS) - routed
        assert not unroutable, (
            f"Providers registered but never routed to: {sorted(unroutable)}. "
            f"Either route them or remove them."
        )

    def test_every_routed_provider_is_registered(self):
        from app.services.llm_router import PROVIDERS, TASK_ROUTING

        for task, routing in TASK_ROUTING.items():
            for slot in ("primary", "secondary", "fallback"):
                name = routing.get(slot)
                if name:
                    assert name in PROVIDERS, (
                        f"Task '{task}' routes {slot} to unknown provider '{name}'"
                    )

    def test_kimi_base_url_keeps_v1_suffix(self):
        """The OpenAI-compatible client appends /chat/completions, so dropping
        /v1 silently 404s and the failure is swallowed by the fallback chain."""
        from app.core.config import Settings

        assert Settings().kimi_base_url.rstrip("/").endswith("/v1")

        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        kimi_lines = [ln for ln in env_example.splitlines()
                      if ln.startswith("KIMI_BASE_URL=")]
        assert kimi_lines, "KIMI_BASE_URL missing from .env.example"
        assert kimi_lines[0].rstrip("/").endswith("/v1"), (
            f".env.example ships a Kimi base URL without /v1: {kimi_lines[0]}"
        )

    def test_env_example_documents_every_settings_key(self):
        """Provider keys in Settings must be discoverable in .env.example."""
        from app.core.config import Settings

        env_example = (ROOT / ".env.example").read_text(encoding="utf-8").upper()
        for field in Settings.model_fields:
            if field.endswith("_api_key") or field.endswith("_base_url"):
                assert field.upper() in env_example, (
                    f"Settings.{field} is not mentioned in .env.example"
                )

    def test_no_dead_claude_references(self):
        """Claude was removed from routing; the provider, dependency, and docs
        must not linger."""
        assert not (APP_DIR / "services" / "providers" / "claude.py").exists()

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "anthropic" not in pyproject

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "ANTHROPIC_API_KEY" not in readme

        from app.core.config import Settings
        assert "anthropic_api_key" not in Settings.model_fields


class TestDockerfilePortHandling:
    """EXPOSE $PORT was evaluated at build time when PORT was undefined, and the
    CMD had no default, so `docker run` without -e PORT failed to start."""

    def test_port_has_a_default(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "EXPOSE $PORT" not in dockerfile, "EXPOSE needs a literal port"
        assert "${PORT:-" in dockerfile, "CMD must default PORT for local runs"


# ═══════════════════════════════════════════════════════════
# Bug class 5: Overstated provenance
# ═══════════════════════════════════════════════════════════


class TestGroundingHonesty:
    """`grounding_used` reported whether a search tool was *offered*, not
    whether the model searched, and the persona phase's citations were dropped
    on the floor — so personas looked as well-sourced as questions."""

    def test_grounding_used_requires_actual_search_evidence(self):
        """Offering the tool is not evidence; queries or sources are."""
        from app.services.llm_router import LLMRouter

        src = (APP_DIR / "services" / "llm_router.py").read_text(encoding="utf-8")
        assert '"grounding_used": bool(grounding_sources or grounding_queries)' in src, (
            "grounding_used must derive from real search evidence, not the request flag"
        )
        assert '"grounding_requested": use_grounding' in src, (
            "the request flag should still be reported, under its own name"
        )
        assert hasattr(LLMRouter, "route_and_generate")

    def test_gemini_extracts_the_queries_actually_issued(self):
        from app.services.providers.gemini import (
            _extract_grounding_queries_rest,
            _extract_grounding_sources_rest,
        )

        searched = {"candidates": [{"groundingMetadata": {
            "webSearchQueries": ["ZCU 选型", ""],
            "groundingChunks": [{"web": {"uri": "https://a.com", "title": "A"}}],
        }}]}
        assert _extract_grounding_queries_rest(searched) == ["ZCU 选型"]
        assert _extract_grounding_sources_rest(searched) == [
            {"url": "https://a.com", "title": "A"}
        ]

        # Tool attached, never invoked — the case that used to read as grounded.
        untouched = {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}
        assert _extract_grounding_queries_rest(untouched) == []
        assert _extract_grounding_sources_rest(untouched) == []

    def test_persona_phase_sources_are_not_discarded(self):
        """Phase 1's citations were overwritten by Phase 3's."""
        src = (APP_DIR / "services" / "persona_service.py").read_text(encoding="utf-8")
        assert "persona_grounding" in src and "question_grounding" in src
        assert 'grounding_sources = p3_result.get("grounding_sources", [])' not in src, (
            "persona-phase grounding sources are being dropped again"
        )

    @pytest.mark.parametrize("state,expected,forbidden", [
        (
            {"requested": True, "used": True,
             "sources": [{"url": "https://z.com/1", "title": "SRC"}], "queries": ["q"]},
            "Google 搜索引用来源",
            ["未实际发起检索", "本次未启用 Google 搜索验证", "未匹配到高质量引用来源"],
        ),
        (
            {"requested": True, "used": True, "sources": [], "queries": ["冷门词"]},
            "未匹配到高质量引用来源",
            ["未实际发起检索", "本次未启用 Google 搜索验证"],
        ),
        (
            {"requested": True, "used": False, "sources": [], "queries": []},
            "未实际发起检索",
            ["本次未启用 Google 搜索验证", "Google 搜索引用来源"],
        ),
        (
            {"requested": False, "used": False, "sources": [], "queries": []},
            "本次未启用 Google 搜索验证",
            ["未实际发起检索", "Google 搜索引用来源"],
        ),
    ])
    def test_persona_disclosure_states_are_mutually_exclusive(self, state, expected, forbidden):
        from app.api.pages import templates as starlette_templates

        campaign = dict(MOCK_CAMPAIGN)
        campaign["persona_grounding"] = state
        campaign["question_grounding"] = {
            "requested": False, "used": False, "sources": [], "queries": [],
        }
        ctx = _build_page_context("tab_persona.html", campaign=campaign, active_tab=1)
        html = starlette_templates.get_template("tab_persona.html").render(ctx)

        # Isolate the persona section — the questions section has its own block.
        block = html[html.index("目标 Persona（"):html.index('<div id="persona-container">')]
        assert expected in block, f"expected {expected!r} in the persona disclosure"
        for f in forbidden:
            assert f not in block, f"persona disclosure should not also say {f!r}"

    def test_persona_disclosure_disclaims_the_ungrounded_vp_step(self):
        """VPs come from a separate, ungrounded model — the citation list must
        not appear to cover them."""
        from app.api.pages import templates as starlette_templates

        campaign = dict(MOCK_CAMPAIGN)
        campaign["persona_grounding"] = {
            "requested": True, "used": True,
            "sources": [{"url": "https://z.com/1", "title": "S"}], "queries": ["q"],
        }
        ctx = _build_page_context("tab_persona.html", campaign=campaign, active_tab=1)
        html = starlette_templates.get_template("tab_persona.html").render(ctx)
        assert "不在此来源范围内" in html

    def test_old_campaigns_still_render(self):
        """Campaigns generated before per-phase tracking have neither new key."""
        from app.api.pages import templates as starlette_templates

        campaign = dict(MOCK_CAMPAIGN)
        campaign.pop("persona_grounding", None)
        campaign.pop("question_grounding", None)
        campaign["grounding_used"] = True
        campaign["grounding_sources"] = [{"url": "https://old.com", "title": "LEGACY"}]
        ctx = _build_page_context("tab_persona.html", campaign=campaign, active_tab=1)
        html = starlette_templates.get_template("tab_persona.html").render(ctx)
        assert "LEGACY" in html


class TestVpPromptDoesNotDemandFabrication:
    """Rules 2/3 ordered the model to cite specific parameters and name
    competitor comparisons, while rule 5 forbade unsourced numbers — and with
    no data assets the whitelist section was not even rendered, so rule 5
    pointed at nothing."""

    BRIEF = {"name": "C", "topic": "ZCU", "industry": "半导体",
             "products": ["P3E"], "keywords": ["ZCU"], "competitors_known": ["NXP S32G"]}
    PERSONAS = [{"id": "p1", "name": "架构师", "layer": "practitioner",
                 "tech_depth": "deep", "decision_weight": "high",
                 "pain_points": ["x"], "objections": [], "decision_criteria": [],
                 "info_channels": ["CSDN"]}]

    def _render(self, language, data_assets):
        from app.services.llm_router import _jinja_env

        return _jinja_env.get_template(f"{language}/vp_generation.md").render(
            brief=self.BRIEF, personas=self.PERSONAS, data_assets=data_assets
        )

    @pytest.mark.parametrize("language,marker", [
        ("zh", "已核实数据资产：无"),
        ("en", "Verified Data Assets: none"),
    ])
    def test_no_assets_renders_an_explicit_prohibition(self, language, marker):
        prompt = self._render(language, [])
        assert marker in prompt, (
            "with no data assets the prompt must say so explicitly, instead of "
            "silently omitting the section that rule 5 refers to"
        )

    @pytest.mark.parametrize("language", ["zh", "en"])
    def test_assets_render_as_a_whitelist(self, language):
        prompt = self._render(language, [
            {"claim": "P3E integrates 6x Cortex-R52", "source": "DS14123 p.12"},
        ])
        assert "DS14123 p.12" in prompt
        assert "已核实数据资产：无" not in prompt
        assert "Verified Data Assets: none" not in prompt

    def test_specificity_rule_is_scoped_to_mechanisms_when_unsourced(self):
        """Rule 2 must stop demanding parameters when there is nothing to cite."""
        zh = self._render("zh", [])
        assert "不是具体的数字" in zh
        en = self._render("en", [])
        assert "not specific numbers" in en

    def test_competitor_comparison_rule_is_scoped_when_unsourced(self):
        zh = self._render("zh", [])
        assert "定性判断" in zh
        en = self._render("en", [])
        assert "stated qualitatively" in en


class TestPersonaGenerationFailsLoudly:
    """Phase 1 returning nothing used to substitute a single empty placeholder
    persona and report success, so every downstream step — VPs, questions, the
    whole plan — was built on a fabricated audience."""

    def _campaign(self):
        return {"campaign_id": "c", "language": "zh", "brief": dict(MOCK_BRIEF)}

    def test_no_personas_raises_instead_of_fabricating(self, monkeypatch):
        import asyncio

        import app.services.persona_service as ps

        async def fake_route(**kwargs):
            return {"text": '{"personas": []}', "model": "gemini",
                    "grounding_requested": True, "grounding_used": False,
                    "grounding_sources": [], "grounding_queries": []}

        monkeypatch.setattr(ps.llm_router, "route_and_generate", fake_route)

        with pytest.raises(RuntimeError) as exc:
            asyncio.run(
                ps.generate_personas_and_questions(self._campaign(), language="zh")
            )
        assert "gemini" in str(exc.value)

    def test_no_placeholder_persona_remains_in_source(self):
        src = (APP_DIR / "services" / "persona_service.py").read_text(encoding="utf-8")
        assert '"id": "prac_default"' not in src, (
            "the silent placeholder persona is back"
        )

    def test_endpoint_maps_upstream_failure_to_502(self, tmp_path, monkeypatch):
        import app.services.persona_service as ps
        import app.utils.file_handler as fh
        from app.main import app as fastapi_app

        monkeypatch.setattr(fh, "CAMPAIGNS_DIR", tmp_path / "campaigns")

        async def boom(*a, **kw):
            raise RuntimeError("Persona 生成失败 | Persona generation failed")

        monkeypatch.setattr(ps, "generate_personas_and_questions", boom)

        client = TestClient(fastapi_app, raise_server_exceptions=False)
        cid = client.post("/api/campaigns", json={
            "brief": {"name": "fail-loud", "topic": "t", "language": "zh"},
        }).json()["campaign_id"]

        resp = client.post(f"/api/campaigns/{cid}/persona/generate")
        assert resp.status_code == 502, resp.text
        assert "Persona generation failed" in resp.json()["detail"]

        # The campaign must be left untouched, not half-written.
        stored = client.get(f"/api/campaigns/{cid}").json()
        assert stored["personas"] == []


class TestPersonaBasisIsVisible:
    """`basis` was computed, stored, stripped from exports, and never shown —
    so a reader could not tell which personas carried human-authored
    constraints. Its value also read as 'web-researched', which it never was."""

    def test_value_is_anchored_not_research(self):
        src = (APP_DIR / "services" / "persona_service.py").read_text(encoding="utf-8")
        assert '"anchored" if p.get("anchor") else "generated"' in src
        assert '"research" if p.get("anchor")' not in src

    def test_model_still_accepts_the_legacy_value(self):
        from app.models.persona import Persona

        assert Persona(basis="anchored").basis == "anchored"
        assert Persona(basis="generated").basis == "generated"
        # Campaigns written before the rename must still load.
        assert Persona(basis="research").basis == "research"

    @pytest.mark.parametrize("basis,expected,forbidden", [
        ("anchored", "骨架锚定", "自由生成"),
        ("research", "骨架锚定", "自由生成"),   # legacy spelling
        ("generated", "自由生成", "骨架锚定"),
        ("", "自由生成", "骨架锚定"),           # missing → not anchored
    ])
    def test_card_shows_provenance_chip(self, basis, expected, forbidden):
        from app.api.pages import templates as starlette_templates

        campaign = dict(MOCK_CAMPAIGN)
        campaign["personas"] = [{
            "id": "p1", "name": "架构师", "layer": "practitioner", "basis": basis,
        }]
        ctx = _build_page_context("tab_persona.html", campaign=campaign, active_tab=1)
        html = starlette_templates.get_template("tab_persona.html").render(ctx)
        assert expected in html
        assert forbidden not in html

    def test_basis_stays_out_of_client_facing_exports(self):
        """Visible in the app, not in the deliverable — unchanged behaviour."""
        from app.services.export_service import _scrub_persona_for_export

        scrubbed = _scrub_persona_for_export(
            {"name": "A", "basis": "anchored", "anchor": "m01"}
        )
        assert scrubbed == {"name": "A"}


class TestMasterPersonaProvenance:
    """The skeletons are the only human-authored input to persona generation;
    their provenance file was gitignored, so the basis for the one trustworthy
    layer lived only on someone's laptop."""

    PROVENANCE = APP_DIR / "data" / "master_personas" / "PROVENANCE.md"

    def test_provenance_file_is_tracked(self):
        assert self.PROVENANCE.is_file(), "PROVENANCE.md is missing"
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for line in gitignore.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert "PROVENANCE" not in stripped, (
                f".gitignore excludes the provenance record again: {line!r}"
            )

    def test_every_skeleton_has_a_provenance_entry(self):
        import json

        text = self.PROVENANCE.read_text(encoding="utf-8")
        skeletons = sorted(
            (APP_DIR / "data" / "master_personas").glob("m*.json")
        )
        assert skeletons, "no master persona skeletons found"
        for f in skeletons:
            code = json.loads(f.read_text(encoding="utf-8"))["code"]
            assert f"### {code}" in text, (
                f"{f.name} (code {code}) has no Sources section in PROVENANCE.md"
            )
