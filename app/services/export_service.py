"""Export Campaign Plan as Markdown or HTML report."""

import json
from datetime import datetime

# Fields that must NEVER appear in user-facing exports.
# anchor = internal master-persona mapping code; basis = research provenance label.
_PERSONA_EXCLUDE_KEYS = {"anchor", "basis"}


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
        "| Priority | Question | Strategic | ST Strength | Winnability | Gap Type | Anchor Point |",
        "|----------|----------|-----------|-------------|-------------|----------|-------------|",
    ]
    for p in priorities:
        qid = p.get("question_id", "")
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
        lines.append("| Layer | Competitor | Position | ST Strategy |")
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

    # Generation metadata
    meta = plan.get("_generation_meta", {})
    if meta:
        lines.extend([
            "---",
            "",
            "## Generation Info",
            "",
            f"- **Analysis Model:** {meta.get('analysis_model', 'N/A')}",
            f"- **Plan Model:** {meta.get('plan_model', 'N/A')}",
            f"- **Grounding Used:** {meta.get('analysis_grounding') or meta.get('plan_grounding')}",
        ])

    return "\n".join(lines)


def export_to_html(plan: dict, campaign_data: dict | None = None) -> str:
    """Convert Campaign Plan to a styled HTML report.

    Returns a self-contained HTML document with ST brand styling.
    """
    brief = (campaign_data or {}).get("brief", {})
    campaign_name = brief.get("name", plan.get("campaign_id", "Campaign Plan"))

    html = f"""<!DOCTYPE html>
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
      <span>📅 Generated: {plan.get('generated_at', datetime.now().isoformat())[:19]}</span>
      <span>🏷 {plan.get('campaign_id', 'N/A')}</span>
      <span>📌 {brief.get('topic', 'N/A')}</span>
    </div>

    <h2>1. AI Perception Summary</h2>
    <div class="summary">{plan.get('ai_perception_summary', '<em>No summary available.</em>')}</div>

    <h2>2. Competitive Landscape</h2>
"""

    comp_landscape = plan.get("competitor_landscape", [])
    if comp_landscape:
        html += """<table>
      <tr><th>Layer</th><th>Competitor</th><th>Position</th><th>ST Strategy</th></tr>"""
        for cl in comp_landscape:
            layer = cl.get("layer", "")
            competitor = cl.get("competitor", "")
            position = cl.get("position", "")
            strategy = cl.get("st_strategy", cl.get("strategy", ""))
            html += f"<tr><td>{layer}</td><td>{competitor}</td><td>{position}</td><td>{strategy}</td></tr>"
        html += "</table>"
    else:
        html += "<p><em>No competitor data available.</em></p>"

    html += "<h2>3. Priority Matrix</h2>"

    priorities = plan.get("priorities", [])
    if priorities:
        html += """<table>
      <tr><th>Priority</th><th>Question</th><th>Strategic</th><th>ST Strength</th><th>Winnability</th><th>Gap Type</th><th>Anchor</th></tr>"""
        for p in priorities:
            priority = p.get("priority", "P2")
            badge = f'<span class="badge-{priority.lower()}">{priority}</span>'
            html += (
                f"<tr><td>{badge}</td>"
                f"<td>{p.get('question_text', p.get('question_id', ''))[:80]}</td>"
                f"<td>{p.get('strategic_importance', '-')}</td>"
                f"<td>{p.get('st_current_strength', '-')}</td>"
                f"<td>{p.get('winnability', '-')}</td>"
                f"<td>{p.get('gap_type', '')}</td>"
                f"<td>{p.get('anchor_point', '')[:80]}</td></tr>"
            )
        html += "</table>"
    else:
        html += "<p><em>No priorities defined.</em></p>"

    html += "<h2>4. 90-Day Timeline</h2>"
    timeline = plan.get("timeline_90days", [])
    if timeline:
        for phase in timeline:
            week = phase.get("week", phase.get("phase", ""))
            actions = phase.get("actions", phase.get("items", []))
            html += f"<h3>{week}</h3><ul>"
            if isinstance(actions, list):
                for a in actions:
                    if isinstance(a, dict):
                        desc = a.get("description", a.get("action", str(a)))
                        channel = a.get("channel", "")
                        label = f"<strong>[{channel}]</strong> " if channel else ""
                        html += f"<li>{label}{desc}</li>"
                    else:
                        html += f"<li>{a}</li>"
            html += "</ul>"
    else:
        html += "<p><em>No timeline defined.</em></p>"

    html += "<h2>5. Monitoring Metrics</h2>"
    metrics = plan.get("monitoring_metrics", [])
    if metrics:
        html += """<table>
      <tr><th>Question</th><th>Expected Recall Position</th><th>Keywords</th></tr>"""
        for m in metrics:
            qid = m.get("question_id", m.get("question", ""))
            position = m.get("expected_recall_position", m.get("target_position", "-"))
            keywords = m.get("associated_keywords", m.get("keywords", []))
            if isinstance(keywords, list):
                keywords = ", ".join(keywords)
            html += f"<tr><td>{qid}</td><td>{position}</td><td>{keywords}</td></tr>"
        html += "</table>"
    else:
        html += "<p><em>No metrics defined.</em></p>"

    # Generation metadata
    meta_data = plan.get("_generation_meta", {})
    if meta_data:
        html += f"""<hr>
    <p style="font-size:12px;color:var(--slate);">
      Generated with: Analysis → {meta_data.get('analysis_model', 'N/A')} |
      Plan → {meta_data.get('plan_model', 'N/A')} |
      Grounding: {meta_data.get('analysis_grounding') or meta_data.get('plan_grounding')}
    </p>"""

    html += """
  </div>
</body>
</html>"""
    return html
