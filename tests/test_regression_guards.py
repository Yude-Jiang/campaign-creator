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
    from app.api import page_context

    return page_context(
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
        active_tab=3,
        **extra,
    )


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
        """Tab 4: Content Studio — needs campaign, sorted_priorities, persona_map."""
        from app.api.pages import templates as starlette_templates

        ctx = _build_page_context(
            "tab_content_studio.html",
            sorted_priorities=MOCK_SORTED_PRIORITIES,
            persona_map=MOCK_PERSONA_MAP,
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

    def test_pages_home_tabs_match(self):
        """Home page tab definitions must have EXPECTED_TAB_COUNT entries."""
        # Extract tab definitions from pages.py source
        pages_src = (APP_DIR / "api" / "pages.py").read_text(encoding="utf-8")
        # Count how many times tab definitions appear (should be 2: home + campaign-view)
        tab_lists = re.findall(r'"num":\s*"(\d+)"', pages_src)
        # Home page tabs: first 5 nums, campaign-view tabs: next 5 nums
        # Just verify the total pattern is consistent
        nums = sorted(set(int(n) for n in tab_lists))
        # pages.py should reference tabs 0-4 in its template switching
        assert nums == sorted(TAB_INDICES), (
            f"pages.py references tab indices {nums}, expected {sorted(TAB_INDICES)}"
        )

    def test_advance_tab_validator_matches(self):
        """advance_tab endpoint must validate 0 to EXPECTED_TAB_COUNT-1."""
        campaign_src = (APP_DIR / "api" / "campaign.py").read_text(encoding="utf-8")
        # Find the range check:  if not 0 <= tab <= N:
        match = re.search(r"if not 0 <= tab <= (\d+):", campaign_src)
        assert match, "Could not find advance_tab range validator in campaign.py"
        max_tab = int(match.group(1))
        assert max_tab == EXPECTED_TAB_COUNT - 1, (
            f"advance_tab validates tab <= {max_tab}, expected tab <= {EXPECTED_TAB_COUNT - 1}"
        )

    def test_advance_tab_docstring_matches(self):
        """advance_tab docstring must reflect the actual tab range."""
        campaign_src = (APP_DIR / "api" / "campaign.py").read_text(encoding="utf-8")
        # Find docstring mentioning tab range:  (0-N)
        match = re.search(r"Advance the campaign to a specific tab \(0-(\d+)\)", campaign_src)
        assert match, "Could not find advance_tab docstring with tab range"
        doc_max = int(match.group(1))
        assert doc_max == EXPECTED_TAB_COUNT - 1, (
            f"advance_tab docstring says 0-{doc_max}, expected 0-{EXPECTED_TAB_COUNT - 1}"
        )

    def test_model_comment_matches(self):
        """Campaign.current_tab comment must list all EXPECTED_TAB_COUNT tabs."""
        model_src = (APP_DIR / "models" / "campaign.py").read_text(encoding="utf-8")
        # Find:  current_tab: int = 0  # 0=Brief, 1=Persona, ...
        match = re.search(r"current_tab.*?#\s*(.*)", model_src)
        assert match, "Could not find current_tab comment in campaign.py model"
        comment = match.group(1)
        tab_refs = re.findall(r"(\d+)=", comment)
        assert len(tab_refs) == EXPECTED_TAB_COUNT, (
            f"Model comment lists {len(tab_refs)} tabs ({comment}), expected {EXPECTED_TAB_COUNT}"
        )

    def test_pages_template_switch_covers_all_tabs(self):
        """pages.py must have if/elif branches for all tab indices 0..4."""
        pages_src = (APP_DIR / "api" / "pages.py").read_text(encoding="utf-8")
        # Find all:  if current_tab == N:  /  elif current_tab == N:
        branches = re.findall(r"(?:if|elif) current_tab == (\d+):", pages_src)
        covered = {int(b) for b in branches}
        assert covered == TAB_INDICES, (
            f"Template switch covers tabs {covered}, expected {TAB_INDICES}"
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
