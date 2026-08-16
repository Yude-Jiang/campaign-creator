{% if diagnostic and (diagnostic.gap_strategy or diagnostic.diagnosis_excerpt or diagnostic.ai_perception_summary) %}
## GEO Diagnosis (the perception gap this piece must close)

This is not background — it is the assignment. Every item below comes from
testing what AI models actually say, and the whole piece must serve closing
this specific gap.

{% if diagnostic.gap_strategy %}
### Gap type: {{ diagnostic.gap_type }}

{{ diagnostic.gap_strategy }}
{% endif %}
{% if diagnostic.st_current_strength or diagnostic.winnability %}
- **Current brand visibility**: {{ diagnostic.st_current_strength }}/5{% if diagnostic.st_current_strength and diagnostic.st_current_strength <= 2 %} (effectively invisible — do not assume the reader or the model already knows this brand's capability here; build it from scratch){% endif %}
- **Winnability**: {{ diagnostic.winnability }}/5
{% endif %}
{% if diagnostic.ai_perception_summary %}
### How AI currently frames this category

{{ diagnostic.ai_perception_summary }}
{% endif %}
{% if diagnostic.competitor_landscape %}
### Who owns the answer today
{% for c in diagnostic.competitor_landscape %}
- **{{ c.competitor }}**{% if c.position %}: {{ c.position }}{% endif %}{% if c.strategy %} → counter: {{ c.strategy }}{% endif %}
{% endfor %}
{% endif %}
{% if diagnostic.diagnosis_excerpt %}
### Diagnosis excerpt (what the models actually answered)

```
{{ diagnostic.diagnosis_excerpt }}
```

**Use it**: find at least one concrete misconception in the answer above — a
dimension it ignores, a capability it misattributes, a solution it treats as
the only option — and address that head-on in the body. Do not write "there
are misconceptions in the market"; address what the excerpt actually says.
{% endif %}
{% endif %}
