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
### Who owns the answer today (internal — for choosing ground, not for contesting it)

⚠ None of these names may appear in the copy. They are listed so you know which
positions are taken and can avoid them, not so you can compare against them.

{% for c in diagnostic.competitor_landscape %}
- **{{ c.competitor }}**{% if c.position %}: holds "{{ c.position }}"{% endif %}
{% endfor %}
{% endif %}
{% if diagnostic.diagnosis_excerpt %}
### Diagnosis excerpt (what the models actually answered)

```
{{ diagnostic.diagnosis_excerpt }}
```

**Use it**: find the **dimension the answer overlooks** — a constraint it does
not weigh, a condition it treats as unimportant, a path it assumes is the only
one. Build the piece on that dimension: what to do when it becomes the binding
constraint.

Note this is about **supplying the missing dimension**, not rebutting the
approaches mentioned. No vendor name appearing in the excerpt may appear in
your copy.
{% endif %}
{% endif %}
