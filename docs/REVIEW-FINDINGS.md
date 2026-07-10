# Campaign Factory — Review Findings

> **Audit date**: 2026-07-10  
> **Method**: Symptom → Root Cause tracing through code, prompt templates, and data pipeline  
> **Evidence base**: Generated plan export (2026 Q3 ZCU Campaign), human battle map (SDV-Page-Battle-Map-Summary.md), and full codebase inspection

---

## Executive Summary

All 5 symptoms have root causes in the codebase — none are "model hallucination" or user error. Four of five trace to the **Step 1 → Step 2 data handoff** in `plan_service.py` and the **prompt structure** in `generate_plan.md`. The fixes are surgical (not architectural) and can be implemented without changing the pipeline topology.

**Single most impactful fix**: Forward `questions` to Step 2 and add `question_text` to Step 1's output schema. This alone would fix Symptom 1, partially fix Symptom 2, and improve Symptom 4.

---

## Symptom 1: Priority Matrix Shows Diagnosis Conclusions Instead of Real Questions

### Evidence

From the generated plan export (2026 Q3 ZCU Campaign, Priority Matrix table):

| Priority | Question |
|----------|----------|
| P0 | ST在此问题中未被提及，缺乏相关认知和可见度 |
| P0 | ST在此问题中被轻微提及，但并非AUTOSAR MCAL配置的最佳实践代表 |

These are **diagnostic summaries** ("ST was not mentioned"), not **benchmark questions**. The original questions would be something like "在ZCU设计中如何选择主控MCU?" or "AUTOSAR MCAL配置的最佳实践是什么?"

### Root Cause Chain

```
Step 1 (analyze_diagnosis.md)
  └─ priority_scores output schema: {"question_id": "q1", ...}
  └─ Does NOT require "question_text" field          ← ROOT CAUSE #1
       ↓
plan_service.py lines 88-93
  └─ Passes brief + analysis_json + personas to Step 2
  └─ Does NOT pass `questions` separately            ← ROOT CAUSE #2
       ↓
Step 2 (generate_plan.md) line 97
  └─ "question_text": "从分析输入中回填的完整问题文本"
  └─ LLM looks at analysis_json → no question_text found
  └─ LLM falls back to summarizing the gap_analysis.evidence field
  └─ Result: diagnostic conclusion masquerading as question
```

### Files Involved

| File | Line(s) | Issue |
|------|---------|-------|
| `app/prompts/zh/analyze_diagnosis.md` | 138-148 | `priority_scores` schema missing `question_text` |
| `app/services/plan_service.py` | 88-93 | `questions` not included in Step 2 variables |
| `app/prompts/zh/generate_plan.md` | 97 | Hard Rule 4 asks LLM to backfill from empty source |

### Fix

**Primary**: In `plan_service.py` line 91, add `"questions": questions` to the variables dict. In `generate_plan.md` line 97, change the instruction to `"{{ questions | selectattr('id', 'equalto', question_id) | map(attribute='text') | first | default('从分析输入中回填') }}"` — a Jinja2 template reference instead of relying on LLM extraction.

**Secondary**: In `analyze_diagnosis.md` line 144, add `"question_text": "从输入中精确复制的完整问题文本"` to the `priority_scores` schema so the field exists in the intermediate JSON even if Step 2's template fix is the primary approach.

---

## Symptom 2: Brief Key Inputs Lost (Stellar G + Target URL)

### Evidence

The generated plan does not mention "Stellar" (any variant: Stellar G, Stellar P3E) in anchor points or content strategy. The `target_page_url` (`st.com.cn/.../zonal-control-unit-zcu.html`) does not appear in the plan's narrative. Yet the human battle map puts Stellar P6/P3E at the center of the ZCU strategy.

### Root Cause Chain

**Layer A — Template renders but LLM ignores**:

```
generate_plan.md lines 22-26
  ├─ Line 25: "- **目标页面**: {{ brief.target_page_url }}"
  ├─ Line 26: "- **产品/方案**: {{ brief.products | join(', ') }}"
  └─ These ARE rendered into the prompt correctly
       ↓
BUT: No Hard Rule requires the LLM to USE these values in output
  └─ Compare Hard Rule 4 which explicitly mandates question_text backfill
  └─ Products and URL have no equivalent mandate
       ↓
LLM reads "目标页面: https://..." and "产品: Stellar P3E" in background
  └─ But when crafting content_brief, it's free to not mention them
  └─ The output schema (line 206) has hardcoded `"target_page_url": "{{ brief.target_page_url }}"` 
     — but only for the priority item, not enforced to appear in content narratives
```

**Layer B — Empty data risk**:

```
CampaignBrief.products: list[str] = Field(default_factory=list)
  └─ If user wrote "Stellar G" in topic/notes but not products field
  └─ Then {{ brief.products | join(', ') }} → "" (empty string)
  └─ LLM sees "产品/方案: " with nothing after it → treats as no product constraint
```

### Files Involved

| File | Line(s) | Issue |
|------|---------|-------|
| `app/prompts/zh/generate_plan.md` | 22-26 | No Hard Rule enforcing product/URL usage in output |
| `app/prompts/zh/generate_plan.md` | 103-115 | `anchor_point` and `content_brief` instructions don't require product names |
| `app/models/campaign.py` | 12 | `products` defaults to `[]` — no validation that it's populated |

### Fix

**Primary**: Add a Hard Rule in `generate_plan.md`: "**Brief 信息强制落地**：每个 priority item 的 `anchor_point` 必须包含目标页面 URL，每个 `content_brief` 必须包含至少一个 `brief.products` 中的具体产品名称。如果 brief 某字段为空，在相应位置标注 `[需补充]` 而非静默跳过。"

**Secondary**: In `plan_service.py`, before calling Step 2, add a sanity check that produces a warning text prepended to `analysis_json` if `brief.products` or `brief.target_page_url` is empty.

---

## Symptom 3: gap_type Mismatched with Strategy (rival_owned → "正面硬吹")

### Evidence

For `gap_type: rival_owned` problems, the generated strategy reads like direct confrontation:
- "ST 应通过技术文章和白皮书加强在 AI 知识库中的可见度"
- "ST 可以通过提供开源的参考设计和软件栈来建立差异化优势"

The human battle map's approach for rival_owned is diametrically opposite:
- "以'单芯片 ZCU 方案'类目替代'ZCU 芯片选型挑战者'框架"
- "title_suggestion 不得以竞品对比为框架；竞品名提及仅限具体参数对照场景"

### Root Cause Chain

```
generate_plan.md line 126 (the rival_owned rule):
  └─ EXISTS — the rule is there
  └─ BUT it's buried in the 5th bullet of the content_plan design principles
  └─ Position: after 126 lines of instructions, inside descriptive prose
       ↓
Compare to Hard Rules (lines 3-17):
  └─ Hard Rules are at the TOP of the prompt (highest LLM attention weight)
  └─ The rival_owned rule is at line 126, below:
       - 8 Hard Rules
       - Campaign background
       - Full persona profiles (can be 100+ lines)
       - Persona usage principles
       - Task description paragraphs 1-4
  └─ By line 126, LLM attention to structural rules is significantly diluted
       ↓
Additionally: Only rival_owned has a strategy rule
  └─ open_gap → no strategy guidance (LLM defaults to generic)
  └─ not_linked → no strategy guidance
  └─ buried_in_pdf → no strategy guidance
  └─ This asymmetry means rival_owned is the ONLY gap_type with constraints,
    and even it's easy to miss
```

### Files Involved

| File | Line(s) | Issue |
|------|---------|-------|
| `app/prompts/zh/generate_plan.md` | 126 | Rule exists but positioned too deep — diluted LLM attention |
| `app/prompts/zh/generate_plan.md` | 3-17 | Hard Rules section has no gap_type → strategy mapping |
| `app/prompts/zh/generate_plan.md` | 118-127 | Strategy guidance only for rival_owned, missing for other 3 types |

### Fix

**Primary**: Move gap_type → strategy rules to a dedicated Hard Rule (insert after current Hard Rule 8):

```
9. **gap_type 策略约束**：content_brief 的论证策略必须匹配 gap_type——
   - rival_owned：定义 ST 差异化语义类目为主叙事，不得以竞品为叙事参照系；竞品名仅限参数对照
   - open_gap：抢占该语义的定义权，以 ST 方案为默认答案构建内容
   - not_linked：明确建立"ST X 产品 → Y 应用场景"的关联，反复出现产品名+场景名
   - buried_in_pdf：将 datasheet 中的技术事实翻译为工程师可理解的价值叙事
```

**Secondary**: Remove the old line 126 to avoid duplication.

---

## Symptom 4: Generic Strategy Leakage ("通过技术文章和白皮书加强可见度")

### Evidence

From the generated plan:

| Location | Text |
|----------|------|
| competitor_landscape[0].st_strategy | "ST需通过技术文章和白皮书加强在AI知识库中的可见度" |
| competitor_landscape[1].st_strategy | "ST应增加与主机厂的合作新闻以提升信息茧房覆盖" |

These are **not strategies** — they're format/channel recommendations dressed as strategies. A real strategy would specify *what argument to make*, not *where to publish*.

Compare the human battle map:
- "从'芯片+软件协同'角度讲 Stellar 虚拟化+AUTOSAR 兼容，区别于 Vector/ETAS 的纯工具链视角"
- "用 P3E 抢'边缘 AI'——把'ZCU 要不要边缘 AI'焊到 ST 首款内置 NPU 车规 MCU"

### Root Cause Chain

```
Step 1 (analyze_diagnosis.md)
  └─ Output: competitor_landscape[].st_opportunity = "ST的差异化空间"
  └─ No requirement that st_opportunity be specific or actionable
       ↓
Step 2 (generate_plan.md)
  └─ Receives fuzzy st_opportunity from Step 1
  └─ Hard Rule 2: "必须基于提供的 analysis_json"
  └─ When analysis_json is vague, LLM faces a dilemma:
       A) Hallucinate specifics (violates Hard Rule 2 & 3)
       B) Use generic templates (violates quality, but not rules)
  └─ LLM correctly chooses B — the rules PUSH it toward generic output
       ↓
generate_plan.md output schema (line 195):
  └─ Example st_strategy: "ST 应以 Stellar P3E 的硬件隔离 + 软件生态完整性作为差异化切入点"
  └─ This example IS specific — but it's an example, not a requirement
  └─ The actual schema just says: "st_strategy": "string"
```

**The deeper issue**: Hard Rule 3 ("不得编造数据") and Hard Rule 2 ("基于分析输入") create a **specificity ceiling**. If Step 1's analysis isn't rich enough, Step 2's output *must* be generic. The fix needs to be at Step 1 — making the analysis output more specific — not just at Step 2.

### Files Involved

| File | Line(s) | Issue |
|------|---------|-------|
| `app/prompts/zh/analyze_diagnosis.md` | 74-84 | `st_opportunity` has no specificity requirement |
| `app/prompts/zh/analyze_diagnosis.md` | 129-136 | `gap_analysis[].recommended_anchor` exists but similarly unconstrained |
| `app/prompts/zh/generate_plan.md` | 9 | Hard Rule 3 prevents hallucination but enables generic output when data is thin |
| `app/prompts/zh/generate_plan.md` | 192-195 | Output schema example is specific but not enforceable |

### Fix

**Primary** (Step 1): In `analyze_diagnosis.md`, strengthen the `st_opportunity` instruction:
```
"st_opportunity": "基于竞品分析，ST 的具体差异化机会。必须包含：(1)ST 哪个具体产品/技术可回应此机会，(2)与哪个竞品的什么弱点形成对比。禁止使用'加强可见度''提升认知''增加内容'等无具体行动的表述——如果诊断数据不支持具体判断，写'诊断数据不足以形成具体机会判断，建议补充 X 类诊断'而非用模糊表述填充"
```

**Secondary** (Step 2): In `generate_plan.md`, add a Hard Rule: "**反通用策略**：competitor_landscape 的 st_strategy 和 priority 的 anchor_point 中，禁止出现'通过技术文章/白皮书/合作新闻加强可见度/提升认知'等以发布渠道代替策略内容的表述。策略必须回答'说什么'而非'在哪说'。"

---

## Symptom 5: Content Rules Not Enforced (Marketing Slogans + Persona-Format Mismatch)

### Evidence

Two sub-issues:

**A. Marketing slogans**: The generated content (when Content Studio runs) leans toward marketing language rather than technical depth. The `content_brief` from Step 2 feeds into content templates with only advisory constraints.

**B. Persona-format mismatch**: A persona with `avoid_channels: ["百度竞价"]` could still get `baidu_search_ad` content generated. The `check_channel_fit()` function warns but doesn't block — and it's only called during `generate_content`, not during `compose_prompt`.

### Root Cause Chain

**Part A — Marketing slogans**:

```
Step 2 → content_brief ("编辑指引") → Step 3 (Content Studio)
  └─ If content_brief is generic (Symptom 4), the content template has
     weak signal to work with
  └─ Content templates (content_zhihu_long.md, content_csdn.md, etc.) DO have
     anti-slogan rules (e.g., "非硬广", "不要强行推销")
  └─ But these are positive instructions ("write technically"), not negative
     detection ("if you catch yourself writing X, rewrite")
  └─ The data_assets whitelist (lines 5-6 of content_zhihu_long.md) prevents
     number-fabrication but doesn't prevent vague marketing language
```

**Part B — Persona-format mismatch**:

```
content_service.py line 299:
  channel_fit_warning = check_channel_fit(variables["persona"], channel, language)
  └─ Returns warning string or ""
  └─ Placed in result dict
  └─ Tab 4 UI renders it as a yellow warning box (tab_content_studio.html lines 137-139)
  └─ NEVER blocks generation — user can ignore
       ↓
content_service.py line 47-73 (check_channel_fit):
  └─ Substring match: if any avoid_channels entry appears in channel name
  └─ Only triggers if persona HAS avoid_channels
  └─ If persona doesn't have the field (legacy data), silently passes
```

Also: `compose_prompt` (the "Copy Full Prompt" feature, line 231-264) does NOT call `check_channel_fit` at all.

### Files Involved

| File | Line(s) | Issue |
|------|---------|-------|
| `app/services/content_service.py` | 47-73 | `check_channel_fit` is advisory-only, never blocks |
| `app/services/content_service.py` | 299 | Channel fit called but result is purely informational |
| `app/services/content_service.py` | 231-264 | `compose_prompt` doesn't call `check_channel_fit` |
| `app/api/campaign.py` | 510-555 | Content generation endpoint has no pre-flight channel-fit gate |
| `app/prompts/zh/content_zhihu_long.md` | 5-6 | Data assets whitelist prevents number-fabrication but not marketing-speak |
| `app/prompts/zh/content_baidu_sem.md` | 5 | Has gap_type awareness (rival_owned rule) — exception, not the norm |

### Fix

**Part A**: In each content template, add a "禁止表述" (forbidden phrases) block:
```
## 禁止表述
以下表述模式在任何情况下不得出现在输出中：
- "引领行业"/"业界领先"/"最佳选择"/"首选方案"（无第三方背书的 superlative）
- "通过技术创新"/"强大性能"/"卓越品质"（无具体技术细节支撑的形容词堆砌）
- ST 品牌名连续出现 3 次以上（硬广信号——AI 模型会降权此类内容）
```
This gives the LLM a concrete negative pattern to avoid, which is more effective than positive instructions alone.

**Part B**: In `content_service.py`, add a `BLOCK_ON_CHANNEL_MISMATCH` config flag (default false, allowing rollout). When enabled, `check_channel_fit` non-empty → raise `ValueError` before LLM call. In `compose_prompt`, add the same check. In the API endpoint, return the warning as a separate field so the UI can show a confirmation dialog.

---

## Methodology Compliance Matrix

These 7 criteria are the right ones for auditing an LLM-pipeline system. Here is the current state against each:

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | **Data Pipeline Integrity** — Every downstream step receives all fields it needs from upstream | ❌ FAIL | `questions` not forwarded to Step 2 (Symptom 1); `question_text` missing from Step 1 output schema |
| 2 | **Mandatory Instruction Placement** — Critical constraints are in Hard Rules (top of prompt), not buried in prose | ⚠️ PARTIAL | Hard Rules 1-8 are well-placed; gap_type strategies are buried at line 126 (Symptom 3); no anti-generic rule exists |
| 3 | **Output Schema ↔ Input Alignment** — Schema fields must be extractable from actual inputs | ❌ FAIL | Step 2 asks for `question_text` from `analysis_json` which doesn't contain it (Symptom 1); `anchor_point` requires "specific diagnosis findings" but analysis may be thin |
| 4 | **Generic Fallback Detection** — System detects and surfaces when LLM defaults to filler | ❌ ABSENT | No "specificity scoring," no filler-phrase detection, no flag when st_strategy = "通过技术文章加强可见度" (Symptom 4) |
| 5 | **Soft vs Hard Enforcement Boundary** — Critical violations block; non-critical warn | ⚠️ PARTIAL | Priority recalculation is hard-enforced (good); channel-fit and content risks are advisory-only (needs hardening for some cases — Symptom 5) |
| 6 | **Model-Task Fitness** — Each task uses the best model for that specific capability | ⚠️ PARTIAL | Persona discovery uses Gemini+grounding (strong choice); plan_generation uses Kimi → DeepSeek → Gemini — but Gemini may be better for structured JSON output |
| 7 | **Post-Processing Robustness** — JSON recovery + field validation after LLM output | ⚠️ PARTIAL | `safe_parse_json` has progressive recovery (good); but NO semantic field validation (are all required fields present? is question_text non-empty? is gap_type a valid enum?) |

---

## Prioritized Improvement List

Ordered by impact × ease-of-fix (not by symptom number):

| Rank | Fix | Symptoms Addressed | Effort | Risk |
|------|-----|--------------------|--------|------|
| 🔴 **P0** | Forward `questions` to Step 2 + add `question_text` to Step 1 output schema | #1 (full), #2 (partial), #4 (partial) | Low — 2 files, ~5 lines changed | Very low — additive change |
| 🔴 **P0** | Add gap_type → strategy Hard Rule (#9) to `generate_plan.md` | #3 (full), #4 (partial) | Low — 1 file, ~10 lines added | Low — replaces weaker buried rule |
| 🟡 **P1** | Add "Brief 信息强制落地" Hard Rule | #2 (full) | Low — 1 file, ~5 lines | Low — additive |
| 🟡 **P1** | Add "anti-generic" detection in `analyze_diagnosis.md` st_opportunity instructions | #4 (full) | Low — 1 file, ~10 lines changed | Low — more specific, not more restrictive |
| 🟡 **P1** | Add "禁止表述" blocks to all 8 content templates | #5A (full) | Medium — 8 files, ~8 lines each | Low — negative constraints are easier for LLMs to follow |
| 🟢 **P2** | Add channel-fit hard-block behind config flag in `content_service.py` | #5B (full) | Medium — 3 files, ~20 lines | Medium — could frustrate users if too aggressive, needs flag |
| 🟢 **P2** | Add semantic field validation to `json_parser.py` post-recovery | #1 (defense-in-depth) | Medium — 1 file, ~40 lines | Low — additive, doesn't change behavior unless validation fails |

---

## What's NOT Broken

To be clear about scope — these aspects of the system work as designed and are not contributing to the 5 symptoms:

1. **Model routing & fallback** (`llm_router.py`) — The chain-of-responsibility with gemini ultimate fallback is robust. No evidence that model choice causes any of the 5 symptoms.
2. **JSON recovery** (`json_parser.py`) — Progressive recovery (trailing commas → missing commas → truncation closure) handles the common LLM output failures. Not the source of quality issues.
3. **Persona pipeline** (`persona_service.py`) — The 3-phase approach (Gemini→DeepSeek→Gemini) produces rich 22-field personas. The plan prompt renders 16 persona fields. The quality issue is in HOW the plan LLM uses them, not in the persona data itself.
4. **Atomic file writes** (`file_handler.py`) — Campaign data integrity is well-protected with per-campaign `threading.Lock` + `.tmp` → rename pattern.
5. **Priority recalculation** (`plan_service.py:137-151`) — Deterministic override of LLM priority labels is correct and working.
6. **HTML/Markdown export** (`export_service.py`) — Faithful rendering of whatever plan JSON exists. Output quality issues are upstream, not in export.

---

## Appendix: Cross-Reference — Symptoms ↔ Code Locations

| Symptom | Primary File(s) | Lines | Mechanism |
|---------|-----------------|-------|-----------|
| #1: Question text loss | `plan_service.py`, `analyze_diagnosis.md`, `generate_plan.md` | 91, 144, 97 | Missing data field in pipeline handoff |
| #2: Brief info loss | `generate_plan.md`, `campaign.py` | 22-26, 103-115, 12 | No enforcement rule + empty default risk |
| #3: gap_type mismatch | `generate_plan.md` | 126 | Rule buried at low-attention position |
| #4: Generic strategies | `analyze_diagnosis.md`, `generate_plan.md` | 74-84, 9 | Specificity ceiling from "don't hallucinate" rule |
| #5: Content rule gaps | `content_service.py`, content templates | 47-73, 299, 231-264 | Advisory-only enforcement + missing negative constraints |
