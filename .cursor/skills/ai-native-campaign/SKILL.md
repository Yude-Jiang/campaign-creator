---
name: ai-native-campaign
description: >-
  Runs the AI-native / GEO campaign workflow used by Campaign Factory: brief →
  personas & benchmark questions → AI-perception diagnosis → priority plan →
  channel content. Use when the user mentions AI native campaign, GEO campaign,
  AI perception diagnosis, GEO-hub, Campaign Factory, 生成式引擎优化, AI感知诊断,
  or asks to plan content from LLM/AI-answer gaps for a technical topic.
---

# AI Native Campaign

Systematize marketing campaigns from **AI perception gaps** (how ChatGPT / Gemini / etc. answer buyer questions), not from traditional SEO keyword lists alone.

Canonical app: this repo (Campaign Factory). Prefer driving the app when it is available; otherwise run the same phases in chat and write artifacts under `data/campaigns/` or a path the user names.

## Non-negotiables

1. **Evidence over invention** — Never invent market share, revenue, unreleased specs, or diagnosis findings. Missing data → mark `[需核实]` / `[诊断数据不足，建议补充…]`.
2. **Question text is sacred** — `question_text` must be an exact copy of the benchmark question by `question_id`. Never replace it with a diagnosis summary.
3. **gap_type drives strategy** — Do not mix playbooks. Read [references/gap-type-playbook.md](references/gap-type-playbook.md).
4. **Goal is the north star** — Priority, channels, timeline, and narrative serve `brief.goal` (default: improve AI visibility + differentiated perception).
5. **Persona-distinct briefs** — If swapping Persona A’s `content_brief` onto Persona B still reads fine, both fail.
6. **Products + URL must appear** — Anchor points and content strategy must use real `brief.products` /型号 and `brief.target_page_url` when provided.
7. **No brand hardcoding in personas** — Persona names/descriptions must not force a single vendor brand string; strategy layers may name the brand explicitly.

## Pipeline (left → right; no auto-backprop)

| Phase | Tab | Input | Output | Prompt / code anchors |
|-------|-----|-------|--------|------------------------|
| 0 Brief | 0 | Topic, page, products, keywords, goal, language | `CampaignBrief` | `app/prompts/{zh,en}/parse_brief.md` |
| 1 Persona + Q | 1 | Brief (+ master personas if present) | 4–5 personas, benchmark questions | `persona_discovery.md` → `vp_generation.md` → `question_discovery.md` |
| 2 Diagnosis | 2 | GEO-hub files per question | Parsed `diagnoses[].raw_text` | `app/services/diagnosis_parser.py` |
| 3 Plan | 3 | Brief + questions + diagnoses + personas | Analysis JSON → plan JSON | `analyze_diagnosis.md` → `generate_plan.md` via `plan_service.py` |
| 4 Content | 4 | Plan item + persona + data_assets | Channel draft + risk scan | `content_*.md` via `content_service.py` |

Upstream edits do **not** refresh downstream artifacts. After brief/persona/diagnosis changes, regenerate the affected later phases.

Schemas and priority formula: [references/output-schemas.md](references/output-schemas.md).

## Phase playbooks

### 0 — Brief

Collect at minimum: `name`, `topic`, `target_page_url`, `products[]`, `keywords[]`, `goal`, `language` (`zh`|`en`). Optional: `competitors_known`, `materials`, `industry`, `notes`.

If the user pastes unstructured text, parse into that shape (same fields as `CampaignBrief` in `app/models/campaign.py`). Confirm products and goal before continuing.

### 1 — Personas & benchmark questions

Cover three layers (each ≥1; practitioners ≥2):

| Layer | Cares about |
|-------|-------------|
| `decision_maker` | TCO, supply chain, ecosystem, compliance |
| `practitioner` | Datasheets, ref designs, SDK, compatibility |
| `influencer` | Architecture compare, roadmap, whitepapers |

Depth floor per persona: ≥5 `pain_points`, ≥5 `info_channels`, ≥3 `search_queries`. Prefer real community roles (web-grounded when tools allow).

Benchmark questions must be what a buyer would ask an AI — high `diagnostic_value`, mapped to personas, not internal slogans.

If master persona skeletons exist in the repo/data, set `anchor` to the skeleton code only; never leak codes into user-facing fields. Inherit `preferred_channels` / `avoid_channels`.

### 2 — GEO diagnosis

For each question, ingest GEO-hub (or equivalent) model answers as evidence. Store per `question_id`. Do not analyze until files exist for the questions being prioritized; call out missing diagnoses explicitly.

### 3 — Diagnosis analysis → campaign plan

**Step A — Analyze** (`analyze_diagnosis.md`): from diagnosis text only, produce `ai_perception_summary`, `inverted_pyramid`, `competitor_landscape`, `gap_analysis`, `priority_scores` (include exact `question_text`).

**Step B — Plan** (`generate_plan.md`): pass **brief + analysis_json + personas + questions**. Produce full plan: summary, competitor landscape, `priorities[]` (with `anchor_point`, `gap_type`, persona-targeted `content_plan`), `timeline_90days`, `monitoring_metrics`, `content_strategy_summary`.

Priority labels must match the formula in the schemas reference (code may recompute).

### 4 — Content studio

Map each content item to a channel template via `FORMAT_MAPPING` in `content_service.py` (知乎长文/问答、CSDN、B站、微信、邮件、百度 SEM/信息流；EN: LinkedIn、Bing ads).

Respect `avoid_channels` / prefer `preferred_channels`. Run `scan_content_risks` logic: pending markers and numeric claims without `data_assets` → warn before publish. Prefer claims backed by `data_assets` (claim + source + verified_by).

## Operating modes

**A. Drive Campaign Factory**

```bash
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Walk tabs 0→4. Persist under `data/campaigns/{id}/`. Use API routes in `app/api/campaign.py` when automating.

**B. Chat-only / artifact mode**

Emit the same JSON shapes as the app. Name files clearly (`brief.json`, `personas.json`, `questions.json`, `analysis.json`, `plan.json`, `content/{channel}-{slug}.md`). Keep language consistent with `brief.language`.

## Quality gate (before handing off)

- [ ] Every priority row shows real `question_text`, not a diagnosis paraphrase
- [ ] Every `content_brief` matches its `gap_type` playbook
- [ ] Products/型号 and target URL appear in anchors / strategy where brief provided them
- [ ] No fabricated quantitative claims; unverified numbers marked
- [ ] Personas distinguishable; channels respect avoid lists
- [ ] Plan serves `brief.goal`
- [ ] Language of outputs matches `brief.language` (zh pages → Chinese copy; en → English)

## When editing this repo

Prompt/behavior changes belong in `app/prompts/{zh,en}/` and the matching service. Keep zh/en pairs in sync. After pipeline fixes, add or extend tests under `tests/` for regressions called out in `docs/REVIEW-FINDINGS.md` (especially question_text handoff and gap_type strategy).
