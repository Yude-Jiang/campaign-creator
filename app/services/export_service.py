"""Export Campaign Plan as Markdown or HTML report."""

import html
from datetime import datetime

# Fields that must NEVER appear in user-facing exports.
# anchor = internal master-persona mapping code; basis = research provenance label.
_PERSONA_EXCLUDE_KEYS = {"anchor", "basis"}


def _e(value: object, limit: int | None = None) -> str:
    """Escape a value for safe interpolation into the HTML export.

    Every field rendered by export_to_html originates from LLM output or from
    an uploaded diagnosis file, so none of it can be trusted as markup. The
    report is served same-origin from /plan/export/html, which would make any
    unescaped tag a stored XSS vector.
    """
    text = "" if value is None else str(value)
    if limit is not None:
        text = text[:limit]
    return html.escape(text, quote=True)


_VALID_PRIORITIES = {"P0", "P1", "P2"}


def _priority_badge(priority: object) -> str:
    """Render a priority badge, constraining the CSS class to a known set.

    The priority label comes from LLM output, so it is not safe to splice
    straight into a class attribute even after escaping.
    """
    label = str(priority or "P2").strip().upper()
    if label not in _VALID_PRIORITIES:
        return f'<span class="badge-p2">{_e(label, 12)}</span>'
    return f'<span class="badge-{label.lower()}">{label}</span>'


def _compute_coverage(plan: dict, campaign_data: dict | None = None) -> dict:
    """Compute the plan-coverage figures shared by the Markdown and HTML exports."""
    all_questions = (campaign_data or {}).get("questions", [])
    priorities = plan.get("priorities", [])
    metrics = plan.get("monitoring_metrics", [])

    high_value_ids = {
        q.get("id") for q in all_questions if q.get("diagnostic_value") == "high" and q.get("id")
    }
    models: set[str] = set()
    for m in metrics:
        for mdl in (m.get("target_models") or []):
            models.add(str(mdl))

    total = len(all_questions)
    prioritized = len(priorities)
    return {
        "total": total,
        "prioritized": prioritized,
        "covered": sum(1 for p in priorities if p.get("content_plan")),
        "high_value_total": len(high_value_ids),
        "high_value_covered": sum(
            1 for p in priorities
            if p.get("question_id") in high_value_ids and p.get("content_plan")
        ),
        "p0": sum(1 for p in priorities if p.get("priority") == "P0"),
        "p1": sum(1 for p in priorities if p.get("priority") == "P1"),
        "p2": sum(1 for p in priorities if p.get("priority") == "P2"),
        "diagnoses": len((campaign_data or {}).get("diagnoses", [])),
        "metrics": len(metrics),
        "models_label": ", ".join(sorted(models)) if models else "N/A",
        "missing": total - prioritized if total > 0 and prioritized < total else 0,
    }


def _scrub_persona_for_export(persona: dict) -> dict:
    """Return a copy of the persona dict with internal-only keys removed."""
    return {k: v for k, v in persona.items() if k not in _PERSONA_EXCLUDE_KEYS}


def _scrub_personas_for_export(personas: list[dict]) -> list[dict]:
    """Return a list of personas with internal-only keys removed."""
    return [_scrub_persona_for_export(p) for p in personas]


def _format_timeline(timeline: list[dict]) -> str:
    """Render timeline phases as markdown."""
    lines = []
    for phase in timeline:
        week = phase.get("week", phase.get("phase", ""))
        actions = phase.get("actions", phase.get("items", []))
        lines.append(f"### {week}")
        if isinstance(actions, list):
            for a in actions:
                if isinstance(a, dict):
                    desc = a.get("description", a.get("action", str(a)))
                    channel = a.get("channel", "")
                    if channel:
                        lines.append(f"- **[{channel}]** {desc}")
                    else:
                        lines.append(f"- {desc}")
                else:
                    lines.append(f"- {a}")
        lines.append("")
    return "\n".join(lines)


def _format_priorities(priorities: list[dict]) -> str:
    """Render priority matrix as markdown table."""
    if not priorities:
        return "_No priorities defined._"

    lines = [
        "| Priority | Question | Strategic | Brand Strength | Winnability | Gap Type | Anchor Point |",
        "|----------|----------|-----------|-------------|-------------|----------|-------------|",
    ]
    for p in priorities:
        qtext = p.get("question_text", "")[:60]
        priority = p.get("priority", "")
        si = p.get("strategic_importance", "-")
        sts = p.get("st_current_strength", "-")
        w = p.get("winnability", "-")
        gap = p.get("gap_type", "")
        anchor = p.get("anchor_point", "")[:80]

        lines.append(
            f"| **{priority}** | {qtext} | {si} | {sts} | {w} | {gap} | {anchor} |"
        )

    lines.append("")
    return "\n".join(lines)


def _format_content_plan(priorities: list[dict]) -> str:
    """Render content plans per priority."""
    lines = []
    for p in priorities:
        priority = p.get("priority", "")
        qid = p.get("question_id", "")
        anchor = p.get("anchor_point", "")
        content_plan = p.get("content_plan", [])

        if not content_plan:
            continue

        lines.append(f"#### {priority} — {qid}")
        lines.append(f"**Anchor:** {anchor}")
        lines.append("")
        lines.append("| Format | Channel | Type | Target | Title |")
        lines.append("|--------|---------|------|--------|-------|")
        for cp in content_plan:
            fmt = cp.get("format", "")
            channel = cp.get("channel", "")
            ctype = cp.get("channel_type", "")
            target = cp.get("target_persona_id", "")
            title = cp.get("title_suggestion", "")[:60]
            lines.append(f"| {fmt} | {channel} | {ctype} | {target} | {title} |")
        lines.append("")
    return "\n".join(lines)


def _format_monitoring_metrics(metrics: list[dict]) -> str:
    """Render monitoring metrics as markdown."""
    if not metrics:
        return "_No metrics defined._"

    lines = [
        "| Question | Expected Recall Position | Associated Keywords |",
        "|----------|-------------------------|-------------------|",
    ]
    for m in metrics:
        qid = m.get("question_id", m.get("question", ""))
        position = m.get("expected_recall_position", m.get("target_position", "-"))
        keywords = m.get("associated_keywords", m.get("keywords", []))
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)
        lines.append(f"| {qid} | {position} | {keywords} |")
    lines.append("")
    return "\n".join(lines)


def _format_coverage(plan: dict, campaign_data: dict | None = None) -> str:
    """Render a coverage disclosure section in markdown.

    Total = all campaign questions (not just plan priorities), so the
    denominator correctly reflects the full question set rather than
    appearing to be 100% covered when only a subset is analyzed.
    """
    cov = _compute_coverage(plan, campaign_data)

    lines = [
        "",
        "## Plan Coverage",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Questions (all) | {cov['total']} |",
        f"| In Plan (prioritized) | {cov['prioritized']} |",
        f"| With Content Strategy | {cov['covered']} |",
        f"| High-Value Covered | {cov['high_value_covered']} / {cov['high_value_total']} |",
        f"| P0 / P1 / P2 | {cov['p0']} / {cov['p1']} / {cov['p2']} |",
        f"| Diagnosis Files | {cov['diagnoses']} |",
        f"| Monitoring Targets | {cov['metrics']} |",
        f"| Target Models | {cov['models_label']} |",
        "",
    ]
    if cov["missing"]:
        lines.append(
            f"⚠ {cov['missing']} question(s) from the full question set have no plan coverage. "
            f"Consider uploading additional diagnosis files or reviewing whether these "
            f"questions are out of scope."
        )
        lines.append("")
    return "\n".join(lines)


def export_to_markdown(plan: dict, campaign_data: dict | None = None) -> str:
    """Convert Campaign Plan to a structured Markdown document.

    Args:
        plan: The campaign plan dict (from plan_service / stored JSON)
        campaign_data: Optional full campaign data for extra context

    Returns:
        Markdown string
    """
    brief = (campaign_data or {}).get("brief", {})
    campaign_name = brief.get("name", plan.get("campaign_id", "Campaign Plan"))

    lines = [
        f"# {campaign_name} — Campaign Plan",
        "",
        f"**Generated:** {plan.get('generated_at', datetime.now().isoformat())}",
        f"**Campaign ID:** `{plan.get('campaign_id', 'N/A')}`",
        f"**Topic:** {brief.get('topic', 'N/A')}",
        f"**Target Page:** {brief.get('target_page_url', 'N/A')}",
        "",
        "---",
        "",
        "## 1. AI Perception Summary",
        "",
        plan.get("ai_perception_summary", "_No summary available._"),
        "",
        "---",
        "",
        "## 2. Competitive Landscape",
        "",
    ]

    # Competitor landscape
    comp_landscape = plan.get("competitor_landscape", [])
    if comp_landscape:
        lines.append("| Layer | Competitor | Position | Strategy |")
        lines.append("|-------|-----------|----------|-------------|")
        for cl in comp_landscape:
            layer = cl.get("layer", "")
            competitor = cl.get("competitor", "")
            position = cl.get("position", "")
            strategy = cl.get("st_strategy", cl.get("strategy", ""))
            lines.append(f"| {layer} | {competitor} | {position} | {strategy} |")
    else:
        lines.append("_No competitor data available._")
    lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. Priority Matrix",
        "",
    ])
    lines.append(_format_priorities(plan.get("priorities", [])))

    lines.extend([
        "---",
        "",
        "## 4. Content Strategy per Priority",
        "",
    ])
    lines.append(_format_content_plan(plan.get("priorities", [])))

    lines.extend([
        "---",
        "",
        "## 5. 90-Day Timeline",
        "",
    ])
    lines.append(_format_timeline(plan.get("timeline_90days", [])))

    lines.extend([
        "---",
        "",
        "## 6. Monitoring Metrics",
        "",
    ])
    lines.append(_format_monitoring_metrics(plan.get("monitoring_metrics", [])))

    # Coverage disclosure
    lines.append(_format_coverage(plan, campaign_data))

    return "\n".join(lines)


def export_to_html(plan: dict, campaign_data: dict | None = None) -> str:
    """Convert Campaign Plan to a styled HTML report.

    Returns a self-contained HTML document with ST brand styling.
    """
    brief = (campaign_data or {}).get("brief", {})
    campaign_name = _e(brief.get("name") or plan.get("campaign_id") or "Campaign Plan")

    out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{campaign_name} — Campaign Plan</title>
  <style>
    :root {{
      --navy: #03234B;
      --gold: #FFD200;
      --blue: #3CB4E6;
      --slate: #64748B;
      --line: #E5E7EB;
      --bg: #F8FAFC;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: #1E293B;
      line-height: 1.6;
      padding: 40px 20px;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
      background: white;
      border-radius: 12px;
      padding: 40px 48px;
      box-shadow: 0 1px 3px rgba(0,0,0,.1);
    }}
    h1 {{
      font-size: 28px;
      color: var(--navy);
      border-bottom: 3px solid var(--gold);
      padding-bottom: 12px;
      margin-bottom: 16px;
    }}
    h2 {{
      font-size: 20px;
      color: var(--navy);
      margin: 32px 0 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--line);
    }}
    h3 {{ font-size: 16px; color: var(--blue); margin: 20px 0 8px; }}
    h4 {{ font-size: 14px; color: var(--slate); margin: 16px 0 6px; }}
    p {{ margin-bottom: 10px; }}
    .meta {{
      font-size: 13px;
      color: var(--slate);
      margin-bottom: 20px;
    }}
    .meta span {{
      display: inline-block;
      margin-right: 20px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
      font-size: 13px;
    }}
    th {{
      background: var(--navy);
      color: white;
      padding: 8px 12px;
      text-align: left;
      font-weight: 600;
    }}
    td {{
      padding: 8px 12px;
      border-bottom: 1px solid var(--line);
    }}
    tr:nth-child(even) {{ background: var(--bg); }}
    .badge-p0 {{
      display: inline-block;
      background: #EF4444;
      color: white;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
    }}
    .badge-p1 {{
      display: inline-block;
      background: #F59E0B;
      color: white;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
    }}
    .badge-p2 {{
      display: inline-block;
      background: #3B82F6;
      color: white;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
    }}
    ul {{ margin-left: 20px; margin-bottom: 12px; }}
    hr {{
      border: none;
      border-top: 1px solid var(--line);
      margin: 24px 0;
    }}
    .summary {{
      background: var(--bg);
      padding: 16px 20px;
      border-radius: 8px;
      border-left: 3px solid var(--blue);
      margin: 12px 0;
    }}
    @media print {{
      body {{ background: white; padding: 0; }}
      .container {{ box-shadow: none; max-width: 100%; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{campaign_name} — Campaign Plan</h1>
    <div class="meta">
      <span>📅 Generated: {_e(plan.get('generated_at') or datetime.now().isoformat(), 19)}</span>
      <span>🏷 {_e(plan.get('campaign_id') or 'N/A')}</span>
      <span>📌 {_e(brief.get('topic') or 'N/A')}</span>
    </div>

    <h2>1. AI Perception Summary</h2>
    <div class="summary">{_e(plan.get('ai_perception_summary')) or '<em>No summary available.</em>'}</div>

    <h2>2. Competitive Landscape</h2>
"""

    comp_landscape = plan.get("competitor_landscape", [])
    if comp_landscape:
        out += """<table>
      <tr><th>Layer</th><th>Competitor</th><th>Position</th><th>Strategy</th></tr>"""
        for cl in comp_landscape:
            layer = _e(cl.get("layer", ""))
            competitor = _e(cl.get("competitor", ""))
            position = _e(cl.get("position", ""))
            strategy = _e(cl.get("st_strategy") or cl.get("strategy") or "")
            out += f"<tr><td>{layer}</td><td>{competitor}</td><td>{position}</td><td>{strategy}</td></tr>"
        out += "</table>"
    else:
        out += "<p><em>No competitor data available.</em></p>"

    out += "<h2>3. Priority Matrix</h2>"

    priorities = plan.get("priorities", [])
    if priorities:
        out += """<table>
      <tr><th>Priority</th><th>Question</th><th>Strategic</th><th>Brand Strength</th><th>Winnability</th><th>Gap Type</th><th>Anchor</th></tr>"""
        for p in priorities:
            badge = _priority_badge(p.get("priority"))
            qtext = _e(p.get("question_text") or p.get("question_id") or "", 80)
            anchor_text = _e(p.get("anchor_point") or "", 80)
            out += (
                f"<tr><td>{badge}</td>"
                f"<td>{qtext}</td>"
                f"<td>{_e(p.get('strategic_importance', '-'))}</td>"
                f"<td>{_e(p.get('st_current_strength', '-'))}</td>"
                f"<td>{_e(p.get('winnability', '-'))}</td>"
                f"<td>{_e(p.get('gap_type', ''))}</td>"
                f"<td>{anchor_text}</td></tr>"
            )
        out += "</table>"
    else:
        out += "<p><em>No priorities defined.</em></p>"

    out += "<h2>4. Content Strategy per Priority</h2>"

    # Content plan per priority (was missing from HTML export)
    if priorities:
        for p in priorities:
            badge = _priority_badge(p.get("priority"))
            qid = _e(p.get("question_id", ""))
            anchor = _e(p.get("anchor_point") or "", 80)
            content_plan = p.get("content_plan", [])
            if not content_plan:
                continue
            out += f"<h3>{badge} {qid} &mdash; {anchor}</h3>"
            out += """<table>
          <tr><th>Format</th><th>Channel</th><th>Type</th><th>Target Persona</th><th>Title</th></tr>"""
            for cp in content_plan:
                fmt = _e(cp.get("format", ""))
                channel = _e(cp.get("channel", ""))
                ctype = _e(cp.get("channel_type", ""))
                target = _e(cp.get("target_persona_id", ""))
                title = _e(cp.get("title_suggestion") or "", 60)
                out += f"<tr><td>{fmt}</td><td>{channel}</td><td>{ctype}</td><td>{target}</td><td>{title}</td></tr>"
            out += "</table>"

    out += "<h2>5. 90-Day Timeline</h2>"
    timeline = plan.get("timeline_90days", [])
    if timeline:
        for phase in timeline:
            week = _e(phase.get("week") or phase.get("phase") or "")
            actions = phase.get("actions", phase.get("items", []))
            out += f"<h3>{week}</h3><ul>"
            if isinstance(actions, list):
                for a in actions:
                    if isinstance(a, dict):
                        desc = _e(a.get("description") or a.get("action") or str(a))
                        channel = a.get("channel", "")
                        label = f"<strong>[{_e(channel)}]</strong> " if channel else ""
                        out += f"<li>{label}{desc}</li>"
                    else:
                        out += f"<li>{_e(a)}</li>"
            out += "</ul>"
    else:
        out += "<p><em>No timeline defined.</em></p>"

    out += "<h2>6. Monitoring Metrics</h2>"
    metrics = plan.get("monitoring_metrics", [])
    if metrics:
        out += """<table>
      <tr><th>Question</th><th>Expected Recall Position</th><th>Keywords</th></tr>"""
        for m in metrics:
            qid = _e(m.get("question_id") or m.get("question") or "")
            position = _e(m.get("expected_recall_position") or m.get("target_position") or "-")
            keywords = m.get("associated_keywords", m.get("keywords", []))
            if isinstance(keywords, list):
                keywords = ", ".join(str(k) for k in keywords)
            out += f"<tr><td>{qid}</td><td>{position}</td><td>{_e(keywords)}</td></tr>"
        out += "</table>"
    else:
        out += "<p><em>No metrics defined.</em></p>"

    # Coverage disclosure — use full question set as denominator
    cov = _compute_coverage(plan, campaign_data)

    missing_warning = ""
    if cov["missing"]:
        missing_warning = (
            f'<p style="color:#d97706;font-size:12px;margin-top:8px;">'
            f'⚠ {cov["missing"]} question(s) from the full set have no plan coverage. '
            f'Consider uploading additional diagnosis files.</p>'
        )

    out += f"""<h2>7. Plan Coverage</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Total Questions (all)</td><td>{cov["total"]}</td></tr>
      <tr><td>In Plan (prioritized)</td><td>{cov["prioritized"]}</td></tr>
      <tr><td>With Content Strategy</td><td>{cov["covered"]}</td></tr>
      <tr><td>High-Value Covered</td><td>{cov["high_value_covered"]} / {cov["high_value_total"]}</td></tr>
      <tr><td>P0 / P1 / P2</td><td>{cov["p0"]} / {cov["p1"]} / {cov["p2"]}</td></tr>
      <tr><td>Diagnosis Files</td><td>{cov["diagnoses"]}</td></tr>
      <tr><td>Monitoring Targets</td><td>{cov["metrics"]}</td></tr>
      <tr><td>Target Models</td><td>{_e(cov["models_label"])}</td></tr>
    </table>
    {missing_warning}"""

    out += """
  </div>
</body>
</html>"""
    return out
