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
### 当前占位者
{% for c in diagnostic.competitor_landscape %}
- **{{ c.competitor }}**{% if c.position %}：{{ c.position }}{% endif %}{% if c.strategy %} → 应对：{{ c.strategy }}{% endif %}
{% endfor %}
{% endif %}
{% if diagnostic.diagnosis_excerpt %}
### 诊断原文节选（AI 模型对该问题的真实回答）

```
{{ diagnostic.diagnosis_excerpt }}
```

**用法**：从上面这段真实回答里找出至少一个具体的认知偏差——被忽略的维度、被错误归因的能力、被默认成唯一解的方案——并在正文中正面处理它。不要泛泛地说"市场存在误解"，要针对上面出现过的具体说法。
{% endif %}
{% endif %}
