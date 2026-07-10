# Campaign Factory — FIX-PLAN

> **基于**: REVIEW-FINDINGS.md (2026-07-10)  
> **原则**: 多 campaign / 跨行业工具。ST 只是第一个测试用例，不是被焊进代码的假设。  
> **状态**: ✅ REVIEW 已批准 — 2026-07-10，以下所有决策已确认，进入实施阶段。

---

## Review 决策记录

| 问题 | 决策 | 理由 |
|------|------|------|
| Q1 · question_text 方案 | ✅ **采纳 Benchmark 对照表方案** | 比 Jinja2 回查更可靠——在 prompt 里给 id→text 对照表 + "精确复制不得改写"Hard Rule，这是 LLM 能力范围内最稳的做法 |
| Q2 · "半导体行业"角色限定词 | ✅ **参数化而非保留** | 成本极低（变量替换），收益是真通用。改为 `{{ brief.industry \| default('B2B 技术') }}`。P1 之后执行。 |
| Q3 · json_parser 锚点校验 | ✅ **先 advisory + 记录命中率** | 渐进思路对。加一条：advisory 期间记录 generic 命中率数据，有真实数据再决定是否升硬阻断。不做这一条，"收集数据"就是空话。 |
| Q4 · Step 1 也补 question_text | ✅ **必须加** | 工件自包含原则——Step 1 输出应不依赖下游临时拼接。只靠 Step 2 对照表是"能用但脆"，Step 1 补上是"契约完整"。 |
| 补充 1 · 英文 generic pattern | ✅ **实施时补 en 版** | `_GENERIC_ANCHOR_PATTERNS` 的正则是中文 hardcode（通过技术文章/加强可见度）。英文需要对应 pattern（strengthen visibility / enhance awareness），否则英文 plan 的锚点校验漏网。 |
| 补充 2 · 型号 token 正则 | ✅ **注释标注假设** | `[A-Z][A-Z0-9]+` 对半导体英文型号（P3E/S32G）有效，但纯中文产品名或混合式命名（骁龙8Gen3）会漏。现在是合理简化，但必须在注释里标注假设，防止静默失效。 |
| 补充 3 · 行业参数化 | ✅ **新增 de-spec 条目** | 所有 prompt 中的 `半导体行业` / `semiconductor industry` → `{{ brief.industry \| default('B2B 技术') }}` / `{{ brief.industry \| default('B2B technology') }}`。需在 CampaignBrief 新增 `industry` 字段。 |

---

## 目录

1. [P0-1: 转发 questions + 补 question_text](#p0-1)
2. [P0-2: gap_type → 打法映射 Hard Rule（通用化）](#p0-2)
3. [P1: 禁止表述块（通用化重写）](#p1)
4. [新增: 强制语义锚点校验](#anchor)
5. [新增: 去特定化审查（全量审计）](#despec)
6. [汇总: 改动文件 × 风险 × 测试影响](#summary)

---

<a name="p0-1"></a>
## P0-1: 转发 questions + 补 question_text

**修复**: Symptom 1（全部）+ Symptom 2/4（部分）  
**文件**: 3 个，共约 6 行改动  
**风险**: 零（纯加性，不改现有逻辑）

### 改动 1/3: `plan_service.py:88-93` — 转发 questions

```diff
     plan_result = await llm_router.route_and_generate(
         task="plan_generation",
         prompt_name="generate_plan.md",
         variables={
             "brief": brief,
+            "questions": questions,
             "analysis_json": json.dumps(analysis_json, ensure_ascii=False, indent=2),
             "personas": personas,
         },
```

**说明**: `questions` 在 plan_service.py 第 28 行已经提取（`questions = campaign_data.get("questions", [])`），只是没有传进 Step 2。加一行即可。

### 改动 2/3: `generate_plan.md:97` — question_text 用 Jinja2 模板引用

```diff
   "question_text": "从分析输入中回填的完整问题文本",
```

→ 改为：

```jinja2
  "question_text": "{% raw %}{% for q in questions %}{% if q.id == question_id %}{{ q.text }}{% endif %}{% endfor %}{% endraw %}",
```

**⚠️ 待确认**: 此处 `question_id` 在输出 schema 中是 LLM 填写的值，而 `questions` 是模板变量。Jinja2 不能做"等 LLM 填完 question_id 再回查"这种运行时操作。因此这个改法**不可行**——Jinja2 在渲染时 `question_id` 还不存在。

**替代方案**: 改用两步策略——

在 `generate_plan.md` 的"诊断分析结果" section 之前，插入一段：

```jinja2
{% raw %}
## Benchmark Questions（用于回填 question_text）

{% for q in questions %}
- **ID**: {{ q.id }} | **Text**: {{ q.text }}
{% endfor %}

在输出 priority item 时，从上述列表中按 question_id 精确复制对应的 question_text。不得总结、改写或编造。
{% endraw %}
```

同时把 Hard Rule 4 改成：

```diff
-4. **保留关键字段**：每个 priority item 必须回填 question_text（从分析输入中提取），确保下游展示有完整信息。
+4. **question_text 精确复制**：每个 priority item 的 question_text 必须从上方的 Benchmark Questions 列表中按 question_id 精确复制。不得总结、不得改写、不得从 diagnosis 内容推断。如果 question_id 在列表中找不到对应的 text，填写 "[未匹配到问题文本，question_id: X]" 而非编造。
```

然后在 `generate_plan.md` 第 97 行（原 question_text schema）改为：

```diff
-  "question_text": "从分析输入中回填的完整问题文本",
+  "question_text": "从上方的 Benchmark Questions 列表中按 question_id 精确复制的完整问题文本",
```

并且在 schema 的字段约束（第 266 行附近）加一条：

```diff
-- `priorities` 必须覆盖分析输入中的所有问题——P2 可简化但不可遗漏
+- `question_text` 必须逐字复制自上方 Benchmark Questions 列表，禁止任何改写、总结或推断。此处错误直接导致下游 Content Studio 生成的内容与实际问题脱节，是为数不多的"一次错误、全线报废"字段。
```

**英文镜像**: 同样改动 `app/prompts/en/generate_plan.md`。

### 改动 3/3: `analyze_diagnosis.md:138-148` — priority_scores schema 补 question_text

```diff
   "priority_scores": [
     {
       "question_id": "q1",
+      "question_text": "从输入中精确复制的完整问题文本",
       "strategic_importance": 5,
```

**英文镜像**: 同样改动 `app/prompts/en/analyze_diagnosis.md`。

**说明**: 即使 Step 2 已有精确复制机制，Step 1 的输出也应该自包含完整信息。这是防御性设计——如果以后 Step 1 的输出被用于其他用途，question_text 就在里面。

### 测试影响

这 3 处改动都是数据传递 / prompt 文本改动，不改变 API 接口签名。现有 64 个测试应全部保持通过。

---

<a name="p0-2"></a>
## P0-2: gap_type → 打法映射 Hard Rule（通用化）

**修复**: Symptom 3（全部）+ Symptom 4（部分）  
**文件**: 2 个（zh + en 的 generate_plan.md）  
**风险**: 低（新规则 + 删除旧规则，不影响已有输出 key）

### 改动: `generate_plan.md` — 新增 Hard Rule 9，删除旧 line 126

**新增**（在 Hard Rule 8 之后，Hard Rule 区末尾）：

```markdown
9. **gap_type 决定策略方向（不得混用）**：content_brief 的论证策略必须匹配该问题的 gap_type——

   | gap_type | 策略方向 | 禁止做法 |
   |----------|---------|---------|
   | `open_gap` / `absence` | **造语料**：建立本品牌在该语义下的首个权威框架。以定义者的身份组织内容——先定义问题应该怎么思考，再自然引出本品牌方案。 | 禁止以"我们也是选项之一"的语气写——open_gap 没有防御对象，进攻就是最好的防御。 |
   | `rival_owned` / `dominance` | **换语义绕开**：定义一个本品牌可独立拥有的差异化类目，以该类目为主语组织全部内容。竞品名仅在参数对照表中出现，不作为叙事参照系反复回指。标题和首段不得以竞品名开篇。 | 禁止以"本品牌 vs 竞品X"为叙事框架；禁止使用"AI 忽略了本品牌""被低估的 X"等受害者叙事；禁止在标题/首段出现竞品名。 |
   | `not_linked` / `mismatch` | **架桥**：反复共现"本品牌产品名 + 该问题/应用场景"，建立 AI 对该关联的统计记忆。用具体产品型号打具体场景，不用泛品牌名。 | 禁止只提品牌不提产品型号——not_linked 的本质是 AI 不知道"X 产品能做 Y 事"，泛品牌名不能解决此问题。 |
   | `buried_in_pdf` | **结构化搬运**：将 datasheet/白皮书中的技术事实翻译为工程师可理解的价值叙事（"X 参数 → 意味着你可以在 Y 场景下省掉 Z"）。保留原文中的可验证数据点，用场景化语言重新表达。 | 禁止概括为"性能优异/可靠性高"——buried 的内容恰恰是具体参数，泛化等于丢弃了唯一的优势证据。 |

   违反示例：对 `rival_owned` 的问题，content_brief 写成"本文强调本品牌是该领域的创新者和领先者"——这是正面对抗，判为不合规。应改写为"以 [本品牌独有的差异化类目] 为主语组织全文，建立该类目的独立权威"。
```

**删除**: `generate_plan.md` 第 126 行的旧 rival_owned 规则（已合并到上表中，避免重复）。该行当前内容：

```
- **rival_owned 策略规则**：gap_type 为 rival_owned 的问题——content_brief 必须指定一个 ST 可定义的差异化语义类目...
```

全部删除该行（zh 版本 ~126 行，en 版本 ~128 行）。

**英文镜像**: 同样改动，注意：
- gap_type 枚举值用英文（已一致）
- 表中的中文描述翻译为英文
- 违反示例中的"本品牌" → "this brand"

### 测试影响

新增 prompt 文本，不影响 API。64 个测试全部保持通过。

---

<a name="p1"></a>
## P1: 禁止表述块（通用化重写）

**修复**: Symptom 5A（内容营销口号）  
**文件**: 12 个内容模板（zh 6 + en 6，linkedin/bing 不在此次 scope）  
**风险**: 低（新增约束块，不删除现有内容）

### 设计原则

分两类——领域无关的可以直接写死；品牌相关的必须参数化。

### 通用禁止表述块（插入每个内容模板的 "## Hard Rules" 区末尾）

**中文版**（zh 的 8 个模板: zhihu_long, zhihu_qa, csdn, bilibili, wechat, email, baidu_sem, baidu_feed）：

```markdown
## 禁止表述（硬性约束）

以下表述模式在任何情况下不得出现在最终输出中：

### 领域无关（任何 campaign 通用）
- **无第三方背书的 superlative**："引领行业""业界领先""最佳选择""首选方案""终极方案""唯一之选"
- **无技术细节支撑的形容词堆砌**："强大的性能""卓越的品质""极致体验""通过技术创新"——如果"性能"具体指什么参数、"创新"具体指什么机理没有写出来，这句话就不合格
- **以发布渠道代替策略内容**："通过技术文章加强可见度""借助白皮书提升认知""以合作新闻扩大影响"——这些是发布方式，不是内容策略

### 品牌相关（从 brief 动态决定）
- 品牌名连续出现 3 次以上（不含标题、URL、署名行）→ 硬广信号，AI 模型会降权此类内容。每 500 字品牌名出现不超过 2 次。
- 竞品名（来自 brief.competitors_known）不得出现在标题或首段。参数对照场景中每个竞品名全篇出现不超过 2 次。
```

**英文版**（en 的对应模板）：

```markdown
## Forbidden Phrases (Hard Constraint)

The following patterns must NEVER appear in final output:

### Domain-Agnostic (universal)
- **Unsubstantiated superlatives**: "industry-leading," "best-in-class," "only choice," "ultimate solution," "market-leading" — without a named third-party source
- **Adjective stacking without technical specifics**: "powerful performance," "exceptional quality," "innovative technology" — if you cannot name the specific parameter or mechanism, the phrase is invalid
- **Channel-as-strategy substitutions**: "strengthen visibility through technical articles," "enhance awareness via whitepapers," "expand influence with partner news" — these describe where to publish, not what argument to make

### Brand-Related (parameterized from brief)
- Brand name appearing more than 3 times (excluding title, URL, and signature line) → AI models downrank overtly promotional content. Limit brand name to ≤2 mentions per 500 words.
- Competitor names (from brief.competitors_known) must not appear in the title or opening paragraph. In parameter comparison contexts, each competitor name appears ≤2 times across the full text.
```

### 插入位置

每个内容模板中，在 `{% if content_brief %}` 之前（即在 Hard Rules 区末尾、编辑指引之前）插入上述块。这样 LLM 在处理具体内容指引之前先看到禁区。

### 不需要这个块的文件

- `parse_brief.md` — 解析器不是内容生成
- `persona_discovery.md` / `vp_generation.md` / `question_discovery.md` — 这些产出的是结构化 JSON，不是对外内容
- `analyze_diagnosis.md` / `generate_plan.md` — 分析/策略 prompt，这些已有自己的约束
- `recheck_comparison.md` / `recheck_attribution.md` — re-check 工具

### 测试影响

新增 prompt 文本，不影响 API。64 个测试保持通过。

---

<a name="anchor"></a>
## 新增: 强制语义锚点校验

**修复**: Symptom 4（根本原因——specificity ceiling）  
**文件**: 2 个（zh + en 的 analyze_diagnosis.md 和 generate_plan.md）  
**可选**: json_parser.py 后置校验  
**风险**: 低（约束更具体，不给 LLM 留 generic 退路）

### 改动 1/2: `analyze_diagnosis.md` — st_opportunity & recommended_anchor 约束

**st_opportunity 字段**（第 74 行附近，`competitor_landscape` section）：

```diff
-列出：ST 的差异化空间在哪里（st_opportunity）
+列出：ST 的差异化空间在哪里（st_opportunity）。要求：
+- 必须包含 (1) 本品牌的具体产品/型号 + (2) 可验证的技术机理或属性。
+- 例（合规）："Stellar P3E 的硬件隔离架构允许单芯片集成多路 CAN-FD/LIN，可减少外围 SBC 数量——这在与 NXP S32G 的 BOM 成本对比中是差异化点。"
+- 例（不合规）："ST 应通过技术文章加强 AI 可见度。"（无产品名、无技术机理、渠道冒充策略）
+- 数据不足以形成具体锚点时，填写 "[诊断数据不足，建议补充 X 类诊断]"（X 替代为具体缺少的数据类型），不得用模糊表述填充。
```

**recommended_anchor 字段**（第 134 行附近，`gap_analysis` section）：

```diff
-  "recommended_anchor": "推荐的ST叙事锚点——一句话说清ST的独特优势"
+  "recommended_anchor": "推荐的叙事锚点。要求：(1) 包含具体产品/型号名，(2) 包含可验证的技术机理。纯价值形容词（'创新者''高性能'）判不合格。数据不足时填写 '[诊断数据不足，建议补充X]'"
```

### 改动 2/2: `generate_plan.md` — anchor_point 约束

**anchor_point 字段**（第 103 行）：

```diff
-  "anchor_point": "ST 的叙事锚点——一句话说清我们的独特差异化优势。必须引用支撑此锚点的具体诊断发现..."
+  "anchor_point": "叙事锚点——一句话说清本品牌的独特差异化优势。必须包含：(1) 具体产品/型号名（引自 brief.products 或诊断中出现的型号），(2) 可验证的技术机理或属性，(3) 引用支撑此锚点的具体诊断发现。纯价值形容词（'创新者''领导者''高性能'）或仅写发布渠道（'通过技术文章...'）判不合格。数据不足时填写 '[诊断数据不足，建议补充X类诊断]' 而非用模糊表述填充。"
```

### 改动 3/3（可选 → 已批准条件执行）: `json_parser.py` — anchor_point 后置校验

在 `safe_parse_json` 之后，`plan_service.py` 的 merge 逻辑之后，增加一个轻量校验函数：

```python
import re

# ── Anchor specificity validation ──
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
    re.compile(r"(strengthen|enhance|improve|boost|increase)\s+(visibility|awareness|presence|influence|recognition)", re.IGNORECASE),
    re.compile(r"through\s+(technical\s+articles|whitepapers|partner\s+news|content\s+marketing)", re.IGNORECASE),
    re.compile(r"^(innovator|leader|industry.leading|best.in.class|market.leading)$", re.IGNORECASE),
]


def _check_anchor_specificity(anchor: str, language: str = "zh") -> dict:
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
            return {"ok": False, "warning": f"anchor_point appears generic: '{anchor[:80]}...'"}

    # Check for product/model reference (see NOTE above about naming assumption)
    if not re.search(r"[A-Z][A-Z0-9]+", anchor):
        return {"ok": False, "warning": f"anchor_point lacks product/model reference: '{anchor[:80]}...'"}

    return {"ok": True, "warning": ""}
```

然后在 `plan_service.py` 的 merge 后、返回前，对每个 priority item 调用此函数：

```python
# After merge loop, before return
generic_count = 0
for item in plan_json.get("priorities", []):
    anchor = item.get("anchor_point", "")
    check = _check_anchor_specificity(anchor, language)
    if not check["ok"]:
        item["_anchor_warning"] = check["warning"]
        generic_count += 1
if generic_count > 0:
    plan_json["_anchor_generic_count"] = generic_count
    logger.info("Anchor specificity check: %d/%d priorities flagged as generic",
                generic_count, len(plan_json.get("priorities", [])))
```

前端 `tab_plan.html` 检测 `_anchor_warning` 字段并显示黄色提示。计划详情 API 返回中暴露 `_anchor_generic_count` 供监控。

**⚠️ 条件**: advisory 期间记录命中率数据（`_anchor_generic_count`）。每次生成 plan 后，该数字写入 campaign JSON 和日志。积累 ≥20 次生成后复盘，若 generic 率 >30%，升级为硬阻断。

### 测试影响

Prompt 改动不影响 API。如果加 json_parser 校验，需要新增 3-5 个单元测试覆盖 `_check_anchor_specificity`。

---

<a name="despec"></a>
## 去特定化审查: 全量硬编码领域假设审计

**审查基准**: 反事实测试——"如果 brief 换成'为某工业 SSD 厂商做存储可靠性 campaign'，这段还成立吗？"  
**产出**: 表格，每行一个硬编码实例，含修复建议。

---

### 分类 A: ⛔ Hard Rules / 固定指令中的品牌名（必须修，换行业就错）

#### A1. 内容模板角色语句（12 个文件）— "for STMicroelectronics"

| # | 文件 | 行 | 硬编码 | 类型 | 应改为 |
|---|------|----|--------|------|--------|
| 1 | `zh/content_zhihu_long.md` | 1 | `负责为 STMicroelectronics 撰写知乎长文` | 角色 | `{{ brief.name }}` |
| 2 | `zh/content_zhihu_qa.md` | 1 | `负责在知乎回答技术问题，自然提升 STMicroelectronics 的品牌认知` | 角色 | `负责在知乎回答技术问题，提升 {{ brief.name }} 的品牌认知` |
| 3 | `zh/content_csdn.md` | 1 | `负责为 STMicroelectronics 撰写 CSDN 技术博客` | 角色 | `{{ brief.name }}` |
| 4 | `zh/content_bilibili.md` | 1 | `负责为 STMicroelectronics 撰写 B站视频脚本` | 角色 | `{{ brief.name }}` |
| 5 | `zh/content_wechat.md` | 1 | `负责为 STMicroelectronics 撰写微信公众号文章` | 角色 | `{{ brief.name }}` |
| 6 | `zh/content_email.md` | 1 | `负责为 STMicroelectronics 撰写技术培育邮件序列` | 角色 | `{{ brief.name }}` |
| 7 | `zh/content_baidu_sem.md` | 1 | `负责为 STMicroelectronics 撰写百度竞价广告文案` | 角色 | `{{ brief.name }}` |
| 8 | `zh/content_baidu_feed.md` | 1 | `负责为 STMicroelectronics 撰写百度信息流广告创意` | 角色 | `{{ brief.name }}` |
| 9 | `en/content_linkedin.md` | 1 | `writing a LinkedIn article for STMicroelectronics` | 角色 | `{{ brief.name }}` |
| 10 | `en/content_email.md` | 1 | `writing a technical nurture email sequence for STMicroelectronics` | 角色 | `{{ brief.name }}` |
| 11 | `en/content_bing_ads.md` | 1 | `for STMicroelectronics, writing Microsoft Bing Ads copy` | 角色 | `{{ brief.name }}` |
| 12 | `en/content_linkedin.md` | 1 | (same as #9) | | |

**额外**: `zh/content_zhihu_long.md:1` 同时含 `半导体行业的` → "技术内容作者"（去行业限定词）。

#### A2. 分析/策略 prompt 中的品牌名（4 个文件）

| # | 文件 | 行 | 硬编码 | 类型 | 应改为 |
|---|------|----|--------|------|--------|
| 13 | `zh/analyze_diagnosis.md` | 1 | `分析 AI 模型对 STMicroelectronics 的认知现状` | 角色 | `分析 AI 模型对 {{ brief.name }} 的认知现状` |
| 14 | `en/analyze_diagnosis.md` | 1 | `analyzing AI model perception of STMicroelectronics` | 角色 | `{{ brief.name }}` |
| 15 | `zh/recheck_comparison.md` | 7 | `如实反映 ST 的进步和不足` | 规则 | `如实反映 {{ brief.name }} 的进步和不足` |
| 16 | `en/recheck_comparison.md` | 7 | `Honestly reflect ST's progress and shortcomings` | 规则 | `{{ brief.name }}` |

#### A3. 中文内容模板规则中的 "ST"（6 个文件，共 ~15 处）

| # | 文件 | 行 | 硬编码 | 应改为 |
|---|------|----|--------|--------|
| 17 | `zh/content_zhihu_long.md` | 34 | `ST 不适用的限定词` | `本品牌不适用的限定词` |
| 18 | `zh/content_zhihu_long.md` | 34 | `ST 在该语境下的定位` | `本品牌在该语境下的定位` |
| 19 | `zh/content_zhihu_long.md` | 39 | `自然融入 ST 的差异化优势` | `自然融入本品牌的差异化优势` |
| 20 | `zh/content_zhihu_long.md` | 48 | `ST 方案的技术实现` | `本品牌方案的技术实现` |
| 21 | `zh/content_zhihu_qa.md` | 33 | `ST 不适用的限定词` | `本品牌不适用的限定词` |
| 22 | `zh/content_zhihu_qa.md` | 33 | `ST 在该语境下的定位` | `本品牌在该语境下的定位` |
| 23 | `zh/content_zhihu_qa.md` | 38 | `提及 ST 的方案优势` | `提及本品牌的方案优势` |
| 24 | `zh/content_csdn.md` | 35 | `ST 不适用的限定词` | `本品牌不适用的限定词` |
| 25 | `zh/content_csdn.md` | 35 | `ST 在该语境下的定位` | `本品牌在该语境下的定位` |
| 26 | `zh/content_csdn.md` | 37 | `ST 官方 SDK/HAL 库` | `本品牌官方 SDK/HAL 库` |
| 27 | `zh/content_csdn.md` | 42 | `ST 官方文档链接` | `本品牌官方文档链接` |
| 28 | `zh/content_bilibili.md` | 36 | `ST 不适用的限定词` | `本品牌不适用的限定词` |
| 29 | `zh/content_bilibili.md` | 36 | `ST 在该语境下的定位` | `本品牌在该语境下的定位` |
| 30 | `zh/content_bilibili.md` | 41 | `ST 产品出现时机` | `本品牌产品出现时机` |
| 31 | `zh/content_bilibili.md` | 50 | `ST 方案深度` | `本品牌方案深度` |
| 32 | `zh/content_wechat.md` | 36 | `ST 不适用的限定词` | `本品牌不适用的限定词` |
| 33 | `zh/content_wechat.md` | 36 | `ST 在该语境下的定位` | `本品牌在该语境下的定位` |
| 34 | `zh/content_wechat.md` | 42 | `提及 ST 方案` | `提及本品牌方案` |
| 35 | `zh/content_wechat.md` | 52 | `ST 方案价值` | `本品牌方案价值` |

#### A4. 付费广告模板规则中的 "ST"（3 个文件）

| # | 文件 | 行 | 硬编码 | 应改为 |
|---|------|----|--------|--------|
| 36 | `zh/content_baidu_sem.md` | 9 | `"ST vs 竞品"为框架，转向 ST 可独立定义的差异化类目（如"单芯片 ZCU 方案"而非"ZCU 选型挑战者"）` | 移除 "ST vs"，"ST 可" → "本品牌可"；示例 "(如"单芯片 ZCU 方案"而非"ZCU 选型挑战者")" → 删除（这是 ST 专用示例，替换为通用描述或删除） |
| 37 | `zh/content_baidu_sem.md` | 36 | `不是 ST 品牌名` | `不是本品牌名` |
| 38 | `zh/content_baidu_feed.md` | 9 | `"ST vs 竞品"为框架，转向 ST 可独立定义的差异化类目` | 同 #36 |
| 39 | `en/content_bing_ads.md` | 9 | `"ST vs Competitor." Instead, anchor on a differentiated category ST can independently own` | `"this brand vs Competitor"` / `the brand can independently own` |
| 40 | `en/content_bing_ads.md` | 36 | `the ST brand` | `the brand` |

#### A5. 英文内容模板规则中的 "ST"（2 个文件）

| # | 文件 | 行 | 硬编码 | 应改为 |
|---|------|----|--------|--------|
| 41 | `en/content_linkedin.md` | 7 | `ST's value should emerge naturally` | `the brand's value should emerge naturally` |
| 42 | `en/content_linkedin.md` | 28 | `ST doesn't naturally fit` | `the brand doesn't naturally fit` |
| 43 | `en/content_linkedin.md` | 28 | `ST's positioning explicitly` | `the brand's positioning explicitly` |
| 44 | `en/content_linkedin.md` | 36 | `ST's differentiated value` | `the brand's differentiated value` |
| 45 | `en/content_email.md` | 46 | `ST's presence in this space` | `the brand's presence in this space` |
| 46 | `en/content_email.md` | 47 | `ST's differentiated value` | `the brand's differentiated value` |
| 47 | `en/content_email.md` | 48 | `Contact ST technical support` | `Contact technical support` |

#### A6. Python 代码中的 "ST"（1 个文件）

| # | 文件 | 行 | 硬编码 | 应改为 |
|---|------|----|--------|--------|
| 48 | `services/export_service.py` | 49 | `\| ST Strength \|` | `\| Brand Strength \|` 或用小写 `\| brand_strength \|`（列标题去品牌化）。列的含义是 `st_current_strength` 字段，不改字段名只改表头。 |
| 49 | `services/export_service.py` | 210 | `\| ST Strategy \|` | `\| Strategy \|` |
| 50 | `services/export_service.py` | 407 | `<th>ST Strategy</th>` | `<th>Strategy</th>` |
| 51 | `services/export_service.py` | 423 | `<th>ST Strength</th>` | `<th>Brand Strength</th>` |

#### A7. HTML 模板中的 "ST"（2 个文件）

| # | 文件 | 行 | 硬编码 | 应改为 |
|---|------|----|--------|--------|
| 52 | `templates/tab_plan.html` | 37 | `分析 ST 的 AI 感知现状` | `分析 {{ brief.name }} 的 AI 感知现状` |
| 53 | `templates/tab_plan.html` | 75 | `ST 召回强度` | `{{ brief.name }} 召回强度` |
| 54 | `templates/tab_plan.html` | 113 | `ST 策略` | `策略` |
| 55 | `templates/tab_plan.html` | 140 | `ST ▾` | `品牌 ▾` |
| 56 | `templates/tab_persona.html` | 314 | `ST 的 AI 品牌召回空白` | `{{ brief.name }} 的 AI 品牌召回空白` |

#### A8. 默认 Persona 名（1 个文件）

| # | 文件 | 行 | 硬编码 | 应改为 |
|---|------|----|--------|--------|
| 57 | `zh/content_baidu_feed.md` | 22 | `{{ persona.name if persona else '汽车电子工程师' }}` | `{{ persona.name if persona else '工程师/决策者' }}` |

#### A9. generate_plan.md 中的 "ST" 固定指令（zh + en）

generate_plan.md 中有大量 "ST" 出现在说明性文本中。这些不是 variable 渲染而是 prompt 固定文本。需要系统性地替换：

| # | 文件 | 行 | 硬编码示例 | 应改为 |
|---|------|----|-----------|--------|
| 58 | `zh/generate_plan.md` | 57 | `ST 差异化论点` | `本品牌差异化论点` |
| 59 | `zh/generate_plan.md` | 68 | `ST 在 AI 模型中对该主题的认知现状` | `本品牌在 AI 模型中对该主题的认知现状` |
| 60 | `zh/generate_plan.md` | 72 | `ST 应对策略` | `本品牌应对策略` |
| 61 | `zh/generate_plan.md` | 81 | `ST 在此层面对此竞品的应对策略` | `本品牌在此层面对此竞品的应对策略` |
| 62 | `zh/generate_plan.md` | 103 | 示例中的 `ST Stellar P3E` | 保留为 **示例**——示例内容天然是领域特定的，换 `[本品牌旗舰产品]` 反而不直观。但示例外围文字（非示例内容）中的 "ST" 要改。 |
| 63 | `zh/generate_plan.md` | 112 | `ST 具体芯片/方案特性` | `本品牌具体产品/方案特性` |
| 64 | `zh/generate_plan.md` | 160-162 | `ST 当前强阵地` / `ST 中等阵地` / `ST 弱阵地` | `本品牌当前强阵地` / `本品牌中等阵地` / `本品牌弱阵地` |
| 65 | `zh/generate_plan.md` | 191,194 | 示例中的 `NXP` / `Stellar P3E` | 保留为示例 |
| 66 | `zh/generate_plan.md` | 216,224 | 示例中的 `[竞品X]` / `[具体芯片]` | 已是模板化占位符，✅ 合规 |
| 67 | `en/generate_plan.md` | 59,70,74,83,105,114,127,161-164,193,196 | 对应英文版相同模式 | 同中文版处理 |

**对于 generate_plan.md**: 采用批量替换策略：
- `ST 的` → `本品牌的`
- `ST 在` → `本品牌在`
- `ST 当前` → `本品牌当前`
- `ST strong` → `strong`（英文版）
- 但 schema 示例中的 `"st_strategy"` 字段名不动（那是 JSON key，不是自然语言）
- 示例内容（如 "NXP", "S32G", "Stellar P3E"）不动——示例的领域特定性是可接受的

---

### 分类 B: ℹ️ 示例/Placeholder 中的行业内容（不需要修，但列出来供审计）

这些出现在 prompt 示例中，是 LLM 的输入格式示范。它们天然是领域特定的，换行业后用户提供的数据自然不同。修它们会导致示例失去直观性。

| 文件 | 内容 | 判断 |
|------|------|------|
| `zh/parse_brief.md:18-29` | 全文示例用 ST ZCU / Stellar / NXP | ✅ 合法——这是 parse_brief 的输入示例 |
| `en/parse_brief.md:18-29` | 同上 | ✅ 合法 |
| `zh/persona_discovery.md:52,78-92` | 示例用 MCU/ZCU/车规 | ✅ 合法——领域 illustration |
| `en/persona_discovery.md:52,78-88` | 同上 | ✅ 合法 |
| `zh/question_discovery.md:73,79-83` | 示例用 ZCU/CAN-FD/Infineon | ✅ 合法 |
| `en/question_discovery.md:73,80-87` | 同上 | ✅ 合法 |
| `zh/vp_generation.md:74-83` | 示例用 Cortex-R52/NXP S32G/Infineon | ✅ 合法 |
| `en/vp_generation.md:68-77` | 同上 | ✅ 合法 |
| `zh/generate_plan.md:191,194,216,224` | schema 示例用 NXP/Stellar P3E | ✅ 合法——JSON schema example |
| `templates/tab_brief.html:37-49` | Placeholder 示例 | ✅ 合法——UI hint, user replaces |
| `templates/tab_content_studio.html:42` | data_assets placeholder | ✅ 合法——UI hint |

---

### 关于 "半导体行业" / "semiconductor industry" 角色描述

共 6 个 prompt 文件在角色描述中包含行业限定词。**决策：参数化，不保留。**

| # | 文件 | 行 | 硬编码 | 应改为 |
|---|------|----|--------|--------|
| I1 | `zh/persona_discovery.md` | 1 | `半导体行业的营销策略专家` | `{{ brief.industry or 'B2B 技术' }}行业的营销策略专家` |
| I2 | `zh/vp_generation.md` | 1 | `半导体行业的价值主张专家` | `{{ brief.industry or 'B2B 技术' }}行业的价值主张专家` |
| I3 | `zh/content_zhihu_long.md` | 1 | `半导体行业的技术内容作者` | `{{ brief.industry or 'B2B 技术' }}行业的技术内容作者` |
| I4 | `en/persona_discovery.md` | 1 | `semiconductor industry marketing strategist` | `{{ brief.industry or 'B2B technology' }} industry marketing strategist` |
| I5 | `en/vp_generation.md` | 1 | `semiconductor industry value proposition specialist` | `{{ brief.industry or 'B2B technology' }} industry value proposition specialist` |
| I6 | `en/content_linkedin.md` | 1 | `semiconductor industry thought leader` | `{{ brief.industry or 'B2B technology' }} industry thought leader` |

**代价**: `CampaignBrief` 需新增一个可选字段 `industry: str = ""`。`parse_brief.md` 需增加 industry 提取行。依赖: 此改动需要在 `CampaignBrief` 模型和 `parse_brief` prompt 中同步更新。这个依赖轻量——和 `goal` 字段一样的模式。

**理由**: 工业 SSD、生物医药、工业自动化——写作语气和领域黑话差异大。写死"半导体"会让 LLM 带入半导体术语和思维。既然 brief 已有 topic/行业信息，参数化成本极低（变量替换），收益是真通用。P1 之后执行。行业 I1-I6 与品牌名 A1-A12 同批改（都是 prompt 角色语句）。

---

<a name="summary"></a>
## 汇总: 改动文件 × 风险 × 测试影响

| Section | 文件数 | 改动性质 | 风险 | 测试影响 |
|---------|--------|---------|------|---------|
| **P0-1** forward questions | 4 (`plan_service.py`, `generate_plan.md` zh+en, `analyze_diagnosis.md` zh+en) | 数据传递 + prompt 文本 + Benchmark 对照表方案 | 零——纯加性 | 全部通过 |
| **P0-2** gap_type Hard Rule | 2 (`generate_plan.md` zh+en) | 新增规则 + 删除旧行 | 低——新规则约束更强 | 全部通过 |
| **P1** 禁止表述（通用化） | 12 (zh×6 + en×6 内容模板) | 各模板新增 ~25 行（含英文版 pattern） | 低——约束更具体 | 全部通过 |
| **Anchor** 强制校验 | 2 (`analyze_diagnosis.md` zh+en) + `json_parser.py` | prompt 约束 + advisory 校验函数（中英文双版 pattern）+ 命中率计数 | 低——不阻断，有数据反馈 | 全部通过（+3-5 新增测试） |
| **De-spec A** 品牌名去特定化 | ~22 (prompt + template + Python) | 批量替换 "ST"/"STMicroelectronics" → `{{ brief.name }}` / "本品牌" | **中**——大面积改动，需逐文件 diff review | 全部通过 |
| **De-spec I** 行业参数化 | 6 prompt + 1 model + 1 parse_brief | "半导体" → `{{ brief.industry }}` + CampaignBrief 新字段 | 低——和 goal 字段一样的模式 | 全部通过（需新增 brief.industry 字段的序列化测试） |
| **补 1** 英文 generic pattern | 1 (`json_parser.py`) | 新增 `_GENERIC_ANCHOR_PATTERNS_EN` | 零——纯加性 | +2 测试 |
| **补 2** 型号 token 注释 | 1 (`json_parser.py`) | 仅注释，不改逻辑 | 零 | 无 |

**总文件改动数**: ~30 个文件  
**预计新增代码行**: ~200 行（prompt 文本为主 + 校验函数）  
**预计修改代码行**: ~100 行（批量替换 + 约束重写）  
**预计删除代码行**: ~15 行（P0-2 旧 rival_owned 规则移除 + 旧 ST 角色语句）  
**破坏性**: 无。所有改动是 prompt 文本 / HTML 文本 / 数据传递 / 注释。不改 JSON schema key 名称，不改 API 接口签名。  
**需新增模型字段**: `CampaignBrief.industry: str = ""`（用于行业参数化）

### 实施顺序建议

```
Phase 1 (立即): P0-1 + P0-2 + 补1 + 补2
  → 修 data pipeline + gap_type 映射 + 英文 anchor pattern
  → 6 文件，零风险，立即可部署

Phase 2 (P1 后): P1 禁止表述 + De-spec A 品牌名 + De-spec I 行业参数化
  → 通用化重写，大面积但纯文本替换
  → ~28 文件，需逐文件 diff review

Phase 3 (随 Phase 1): Anchor 强制校验
  → 与 P0-1/P0-2 同一批部署，advisory 模式启动数据收集
```

### 不再待确认（全部已拍板）

以上所有决策已由 review 确认。不再有开放问题。

---

## 附录: De-spec 快速执行脚本参考

以下替换是安全的（规则文本中的 "ST" → "本品牌"），可以批量执行：

**中文 prompt 文件** (`zh/*.md`):
```
s/ST 的/本品牌的/g          # 但排除 JSON schema key 名和 Jinja2 变量
s/ST 在/本品牌在/g
s/ST 当前/本品牌当前/g
s/ST 不适用的/本品牌不适用的/g
s/ST 在该语境下/本品牌在该语境下/g
s/提升 STMicroelectronics 的品牌认知/提升 {{ brief.name }} 的品牌认知/g
s/负责为 STMicroelectronics/负责为 {{ brief.name }}/g
```

**英文 prompt 文件** (`en/*.md`):
```
s/for STMicroelectronics/for {{ brief.name }}/g
s/ST's /the brand's /g
s/the ST brand/the brand/g
s/ST can independently own/the brand can independently own/g
s/"ST vs Competitor"/"this brand vs Competitor"/g
```

**不替换**: JSON schema key 名 (`"st_strategy"`, `"st_current_strength"`), Jinja2 变量 (`{{ brief.products }}`), schema 示例中的产品名 (NXP, Stellar, S32G)。这些是接口约定或示例数据。

---

> **一句话**: 这组修复让工具从"为 ST 定制的 campaign factory"变成"接受任意 brief 的 campaign factory"。ST 只是第一个通过测试的用例。
