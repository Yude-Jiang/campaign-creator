# Output schemas & scoring

Aligned with `app/models/campaign.py` and prompt JSON contracts in `app/prompts/`.

## CampaignBrief

```json
{
  "name": "",
  "topic": "",
  "target_page_url": "",
  "products": [],
  "keywords": [],
  "competitors_known": [],
  "materials": [],
  "goal": "",
  "notes": "",
  "industry": "",
  "language": "zh"
}
```

## Analysis (Step A)

Key fields: `ai_perception_summary`, `inverted_pyramid` (object keyed by `question_id`), `competitor_landscape[]`, `gap_analysis[]`, `priority_scores[]`.

Strength tiers: `strong` | `moderate` | `weak` | `absent`.

Perception tiers (adjust labels to topic): `concept` | `solution` | `product`.

Each `priority_scores` item **must** carry exact `question_text` from the benchmark list.

## Priority formula

Scores are 1–5. Label:

- **P0**: `strategic_importance ≥ 4` AND `winnability ≥ 3` AND `st_current_strength ≤ 2`
- **P1**: `strategic_importance ≥ 3` OR (`winnability ≥ 3` AND `st_current_strength ≤ 3`)
- **P2**: everything else

Do not invent a different mapping; validators may recompute.

## Plan (Step B)

Expect at least:

- `ai_perception_summary`
- `competitor_landscape` (cognitive layers, not persona layers)
- `priorities[]` with `question_id`, exact `question_text`, `gap_type`, `anchor_point`, `content_plan[]` (`channel`, `target_persona_id`, `content_brief`, …)
- `timeline_90days[]`
- `monitoring_metrics[]`
- `content_strategy_summary`

Pass **questions** into Step B so `question_text` can be copied — never ask the model to invent them from diagnosis alone.

## Content risk scan

Treat as warnings (non-blocking):

- Markers like `[需核实…]` / `[TBD…]` / `[To verify…]`
- Numeric claims when campaign has empty `data_assets`

`data_assets` item shape: `{ "claim", "source", "verified_by", "added_at" }`.
