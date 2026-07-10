# Campaign Factory — Current State

> **Audit date**: 2026-07-10  
> **Scope**: Full codebase structure, data flow, LLM call matrix, data model coverage  
> **Purpose**: Provide the baseline for a root-cause review of 5 confirmed output quality symptoms

---

## 1. Project Structure

```
campaign-factory/
├── app/
│   ├── api/
│   │   └── campaign.py          # FastAPI router — all endpoints
│   ├── core/
│   │   └── config.py            # App settings (geo_hub_url, etc.)
│   ├── models/
│   │   ├── campaign.py          # Campaign, CampaignBrief pydantic models
│   │   ├── persona.py           # Persona model (22 fields)
│   │   └── question.py          # Question model (10+ fields)
│   ├── prompts/
│   │   ├── zh/                  # Chinese prompt templates (15 files)
│   │   │   ├── analyze_diagnosis.md     # Step 1: GEO analysis
│   │   │   ├── generate_plan.md         # Step 2: Campaign plan generation ★
│   │   │   ├── persona_discovery.md     # Phase 1: Persona discovery (Gemini+grounding)
│   │   │   ├── vp_generation.md         # Phase 2: Value prop generation (DeepSeek)
│   │   │   ├── question_discovery.md    # Phase 3: Question generation (Gemini+grounding)
│   │   │   ├── parse_brief.md           # Natural-language brief parser
│   │   │   ├── content_zhihu_long.md    # 知乎长文 template
│   │   │   ├── content_zhihu_qa.md      # 知乎问答 template
│   │   │   ├── content_csdn.md          # CSDN 技术博客 template
│   │   │   ├── content_bilibili.md      # B站视频脚本 template
│   │   │   ├── content_wechat.md        # 微信图文 template
│   │   │   ├── content_email.md         # 邮件培育 template
│   │   │   ├── content_baidu_sem.md     # 百度竞价 template
│   │   │   ├── content_baidu_feed.md    # 百度信息流 template
│   │   │   ├── recheck_comparison.md    # Re-check: comparison
│   │   │   └── recheck_attribution.md   # Re-check: attribution
│   │   └── en/                  # English mirrors (same set)
│   ├── services/
│   │   ├── llm_router.py        # Multi-model routing + Jinja2 rendering
│   │   ├── persona_service.py   # 3-phase persona pipeline
│   │   ├── plan_service.py      # 2-step plan pipeline ★ CRITICAL
│   │   ├── content_service.py   # Content generation + channel mapping
│   │   ├── export_service.py    # Markdown/HTML export
│   │   ├── diagnosis_parser.py  # Raw file → text extraction
│   │   └── providers/           # Claude, Gemini, DeepSeek, Kimi wrappers
│   ├── utils/
│   │   ├── json_parser.py       # safe_parse_json with progressive recovery
│   │   └── file_handler.py      # Atomic file writes + campaign locking
│   └── main.py                  # FastAPI app entry point
├── templates/
│   ├── base.html                # Shared layout + CSS
│   ├── tab_brief.html           # Tab 0: Campaign Brief input
│   ├── tab_persona.html         # Tab 1: Persona + Questions
│   ├── tab_diagnosis.html       # Tab 2: GEO Diagnosis upload
│   ├── tab_plan.html            # Tab 3: Campaign Plan display
│   └── tab_content_studio.html  # Tab 4: Content generation
├── static/
│   └── css/app.css              # Global styles
├── data/campaigns/{id}/         # Per-campaign JSON + diagnosis files
├── docs/
│   ├── CURRENT-STATE.md         # ← this file
│   └── REVIEW-FINDINGS.md       # ← root-cause analysis
└── tests/                       # 64 tests
```

---

## 2. End-to-End Data Flow

```
┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  Tab 0       │    │  Tab 1        │    │  Tab 2        │    │  Tab 3         │    │  Tab 4        │
│  Brief       │───→│  Persona + Q  │───→│  Diagnosis    │───→│  Campaign      │───→│  Content      │
│              │    │               │    │               │    │  Plan          │    │  Studio       │
└──────────────┘    └───────────────┘    └───────────────┘    └───────────────┘    └──────────────┘
       │                   │                    │                    │                    │
       ▼                   ▼                    ▼                    ▼                    ▼
  CampaignBrief     3 personas           N diagnosis         Plan JSON           Generated
  (10 fields)       + N questions        files (.md/.html)   (7 sections)        content text
       │                   │                    │                    │                    │
       │                   │                    │                    │                    │
       ▼                   ▼                    ▼                    ▼                    ▼
  POST /campaigns   3× LLM calls:         Raw text →         2× LLM calls:       Per-format LLM:
  → campaign.json   Gemini→DeepSeek      diagnosis_parser    Kimi→Kimi/          deepseek/kimi
                    →Gemini              → raw_text[]         DeepSeek            + channel template
```

**Key insight**: Each tab depends on ALL previous tabs' data. The data flows left-to-right through the campaign JSON file. There is NO cross-tab loop — once downstream data is generated, upstream changes are NOT automatically propagated.

---

## 3. LLM Call Matrix

| # | Pipeline Phase | Task Key | Primary Model | Prompt File | Input Variables | Output Shape | Grounding |
|---|---------------|----------|---------------|-------------|-----------------|-------------|-----------|
| 0 | Brief Parse | `parse_brief` | DeepSeek | `parse_brief.md` | `{text}` | `{name, topic, products[], goal, ...}` | No |
| 1a | Persona Discovery | `persona_discovery` | **Gemini** | `persona_discovery.md` | `{brief}` | `{personas: [...], search_queries: [...]}` | **Yes** |
| 1b | VP Generation | `vp_generation` | **DeepSeek** | `vp_generation.md` | `{brief, personas}` | `{personas: [...]}` (enriched) | No |
| 1c | Question Discovery | `question_discovery` | **Gemini** | `question_discovery.md` | `{brief, personas}` | `{questions: [...]}` | **Yes** |
| 2 | Diagnosis Analysis | `diagnosis_analysis` | **Kimi** | `analyze_diagnosis.md` | `{brief, questions, diagnoses}` | `{ai_perception_summary, inverted_pyramid, competitor_landscape, gap_analysis, priority_scores}` | No |
| 3 | Plan Generation | `plan_generation` | **Kimi** | `generate_plan.md` | `{brief, analysis_json, personas}` | `{ai_perception_summary, competitor_landscape, priorities[], timeline_90days[], monitoring_metrics[], content_strategy_summary}` | No |
| 4a | Content Compose | (none, dry-run) | — | `content_{format}.md` | `{brief, persona, content_brief, anchor_point, question_text, data_assets}` | Rendered prompt string | No |
| 4b | Content Generate | `content_organic_chinese` etc. | **DeepSeek** | `content_{format}.md` | Same as 4a | Generated content text | No |

### Model Selection Rationale (from code, not speculation)

- **Gemini**: Used where Google Search grounding adds value (persona + question discovery from real web data)
- **DeepSeek**: Used for Chinese creative generation (VP, content writing, SEM copy)
- **Kimi**: Used for analytical tasks (diagnosis analysis, plan generation) — "best at structured Chinese analysis"
- **Claude**: Registered but not in any routing chain

### Chain-of-Responsibility Fallback

Every task has `primary → secondary → fallback`, with `gemini` as ultimate universal fallback (line 182-184 of `llm_router.py`).

---

## 4. Critical Data Handoff: Step 1 → Step 2

This is the **single most important interface in the system** — where 4 of the 5 reported symptoms originate.

### What Step 1 (analyze_diagnosis.md) PRODUCES

```json
{
  "ai_perception_summary": "string",
  "inverted_pyramid": { "q1": {"strength": "...", "perception_tier": "...", "summary": "..."} },
  "competitor_landscape": [{"question_id": "q1", "competitors": [...], "st_opportunity": "..."}],
  "gap_analysis": [{"question_id": "q1", "gap_type": "open_gap|rival_owned|not_linked|buried_in_pdf", "evidence": "...", "recommended_anchor": "..."}],
  "priority_scores": [{"question_id": "q1", "strategic_importance": 5, "st_current_strength": 2, "winnability": 4, "priority": "P0", "rationale": "..."}]
}
```

**Notable absences from Step 1 output**:
- ❌ `question_text` — NOT in `priority_scores` entries
- ❌ `question_text` — NOT in `gap_analysis` entries
- ❌ `question_text` — NOT in `competitor_landscape` entries
- ❌ Product-level recall — the `inverted_pyramid` is at question-level, not per-model

### What Step 2 (generate_plan.md) NEEDS

```json
{
  "priorities": [{
    "question_id": "q1",
    "question_text": "← MUST backfill from analysis input (Hard Rule 4)",
    "anchor_point": "← MUST cite specific diagnosis findings",
    "gap_type": "...",
    "content_plan": [{"content_brief": "← MUST include competitor names + ST product specifics"}]
  }]
}
```

### What `plan_service.py` PASSES to Step 2 (lines 88-93)

```python
variables={
    "brief": brief,                                           # ✅ Brief is passed
    "analysis_json": json.dumps(analysis_json, ...),          # ⚠️ Contains no question_text
    "personas": personas,                                     # ✅ Personas are passed
    # ❌ questions is NOT passed — LLM can't see original question texts
}
```

**The gap**: `questions` is available in `campaign_data` (line 28 of plan_service.py) but is **not forwarded** to Step 2. Step 1's output schema doesn't carry `question_text`. The LLM is asked to "回填" (backfill) from an input that doesn't contain the text.

---

## 5. Data Models

### CampaignBrief (10 fields)

| Field | Type | Default | Rendered in generate_plan.md? |
|-------|------|---------|-------------------------------|
| `name` | `str` | `""` | Line 22 |
| `topic` | `str` | `""` | Line 24 |
| `target_page_url` | `str` | `""` | Line 25 (hardcoded in output schema line 206) |
| `products` | `list[str]` | `[]` | Line 26 (`join(', ')`) |
| `keywords` | `list[str]` | `[]` | Line 258 (monitoring_metrics example) |
| `competitors_known` | `list[str]` | `[]` | ❌ Not rendered |
| `materials` | `list[str]` | `[]` | ❌ Not rendered |
| `goal` | `str` | `""` | Line 23 (with fallback) |
| `notes` | `str` | `""` | ❌ Not rendered |
| `language` | `Literal["zh","en"]` | `"zh"` | Controls prompt subdirectory |

### Campaign (top-level, persisted to JSON)

```
Campaign
├── campaign_id: str
├── language: "zh" | "en"
├── brief: CampaignBrief
├── personas: list[dict]       # 22-field persona dicts
├── questions: list[dict]      # question dicts with id, text, category, diagnostic_value
├── diagnoses: list[dict]      # {question_id, filename, raw_text (after parsing)}
├── data_assets: list[dict]    # {claim, source, verified_by, added_at}
└── plan: dict | None          # Full plan JSON (7 sections)
```

### Key Observation: `plan` is the ONLY output that persists

The Step 1 analysis (`analysis_json`) is NOT persisted — it's an intermediate artifact passed in-memory from `plan_service.py` Step 1 to Step 2. If Step 2 fails, Step 1 is lost and must be re-run. This means plan regeneration always re-runs BOTH steps.

---

## 6. Post-Processing & Safety Nets

### Priority Recalculation (plan_service.py lines 137-151)

```python
# Deterministic recalculation — overrides LLM's priority label
P0: strategic_importance ≥ 4 AND winnability ≥ 3 AND st_current_strength ≤ 2
P1: strategic_importance ≥ 3 OR (winnability ≥ 3 AND st_current_strength ≤ 3)
P2: everything else
```

This is a **hard enforcement** — the LLM's priority label is discarded and recalculated.

### JSON Recovery (json_parser.py)

Progressive recovery pipeline: direct parse → strip trailing commas → add missing commas between lines → truncated JSON closure → return `{}` on total failure.

No semantic validation post-recovery (e.g., checking that `priorities` contains all expected fields, or that `question_text` is not empty).

### Content Risk Scan (content_service.py lines 21-42)

Checks for `[需核实]` / `[TBD]` markers and numeric claims without data assets. **Advisory only** — returns a warning message, never blocks.

### Channel-Fit Check (content_service.py lines 47-73)

Soft validation: checks if persona `avoid_channels` matches current content channel. **Advisory only** — returns warning string, never blocks generation.

---

## 7. The Plan Output Schema (generate_plan.md lines 184-273)

The output JSON has 7 top-level keys:

| Key | Content | Guarded by Hard Rule? |
|-----|---------|----------------------|
| `ai_perception_summary` | ≤300 chars | #1 (JSON-only) |
| `competitor_landscape` | Array of {layer, competitor, product, position, st_strategy} | #1 |
| `priorities` | Array of battle cards with content_plan[] | #4 (question_text), #6 (channel-persona), #7 (persona precision), #8 (goal) |
| `timeline_90days` | 4 phases with actions[] | #1 |
| `monitoring_metrics` | Per-question recall targets | #1 |
| `content_strategy_summary` | One-sentence narrative summary | #1 |

### `content_brief` Quality Requirements (lines 118-127)

Five explicit requirements for content_brief — but these are in the **descriptive section**, not in the Hard Rules block. The LLM treats Hard Rules differently from descriptive text.

---

## 8. UI Rendering Pipeline for Plan Display

```
plan JSON → tab_plan.html (Jinja2 SSR) → browser
                ↓
         export_service.py → Markdown or HTML export
```

The `tab_plan.html` template renders plan sections with `{% if %}` guards — missing sections are silently omitted. The HTML export (`export_service.py`) renders independently, not sharing template logic with the in-app display.

---

## 9. Identified Structural Weaknesses

| # | Weakness | Location | Severity |
|---|----------|----------|----------|
| 1 | `questions` not forwarded to Step 2 | `plan_service.py:88-93` | 🔴 Critical |
| 2 | Step 1 output schema lacks `question_text` | `analyze_diagnosis.md:138-148` | 🔴 Critical |
| 3 | `competitors_known` and `materials` never rendered in any prompt | `generate_plan.md:22-26` | 🟡 Medium |
| 4 | `gap_type` strategy rules buried in content_plan prose, not in Hard Rules | `generate_plan.md:126` | 🟡 Medium |
| 5 | No post-parse field validation beyond JSON recovery | `json_parser.py` | 🟡 Medium |
| 6 | Content quality checks are advisory-only, never block | `content_service.py:47-73, 21-42` | 🟡 Medium |
| 7 | Step 1 intermediate result not persisted — regeneration always re-runs both steps | `plan_service.py` | 🟢 Low (cost, not quality) |
| 8 | `notes` field on brief never rendered in any prompt | `generate_plan.md` | 🟢 Low |
