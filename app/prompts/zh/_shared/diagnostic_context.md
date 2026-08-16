{% if diagnostic and (diagnostic.gap_strategy or diagnostic.diagnosis_excerpt or diagnostic.ai_perception_summary) %}
## GEO 诊断结论（本篇要填补的认知缺口）

这不是背景信息，是**写作任务本身**。下面每一项都来自对 AI 模型的实测诊断，全文必须服务于填补这个缺口。

{% if diagnostic.gap_strategy %}
### 缺口类型：{{ diagnostic.gap_type }}

{{ diagnostic.gap_strategy }}
{% endif %}
{% if diagnostic.st_current_strength or diagnostic.winnability %}
- **本品牌当前认知强度**：{{ diagnostic.st_current_strength }}/5{% if diagnostic.st_current_strength and diagnostic.st_current_strength <= 2 %}（几乎不可见——不要假设读者或模型已知本品牌在此领域的能力，需要从头建立）{% endif %}
- **可赢度**：{{ diagnostic.winnability }}/5
{% endif %}
{% if diagnostic.ai_perception_summary %}
### AI 目前如何看待这个品类

{{ diagnostic.ai_perception_summary }}
{% endif %}
{% if diagnostic.competitor_landscape %}
### 当前占位者（内部输入 — 用于判断该避开哪块地、该主打哪个场景）

⚠ 以下名称**一律不得出现在正文中**。列在这里是让你知道哪些位置已经被占住、不要去争，
不是让你去比较。

{% for c in diagnostic.competitor_landscape %}
- **{{ c.competitor }}**{% if c.position %}：已占据「{{ c.position }}」{% endif %}
{% endfor %}
{% endif %}
{% if diagnostic.diagnosis_excerpt %}
### 诊断原文节选（AI 模型对该问题的真实回答）

```
{{ diagnostic.diagnosis_excerpt }}
```

**用法**：从这段真实回答里找出**被忽略的那个维度**——模型没考虑到的约束、被当成不重要的条件、
被默认成唯一路径的做法。然后把文章建立在那个维度上，讲清楚"当这个维度成为主要约束时，
事情该怎么做"。

注意：是**补上被忽略的维度**，不是反驳上面提到的方案。诊断原文里出现的任何厂商名，
都不得出现在你的正文中。
{% endif %}
{% endif %}
