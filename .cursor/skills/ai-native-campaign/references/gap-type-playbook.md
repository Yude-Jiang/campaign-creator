# Gap-type playbook

Source of truth for strategy direction: `app/prompts/{zh,en}/generate_plan.md` Hard Rule 9 and `analyze_diagnosis.md` gap taxonomy.

| gap_type | Meaning | Strategy | Forbidden |
|----------|---------|----------|-----------|
| `open_gap` / `absence` | Nobody owns the answer; brand can define the frame | **造语料** — define how the problem should be thought, then introduce the brand solution as the natural fit | “We are also an option” tone; defensive framing when there is no rival to defend against |
| `rival_owned` / `dominance` | Rival is the AI default | **换语义绕开** — own a differentiated category as the subject; rivals only in parameter tables | Head-to-head “Brand vs Rival” narrative; victim tone (“AI ignored us”); rival name in title/lede |
| `not_linked` / `mismatch` | Brand can solve it but AI never links them | **架桥** — co-occur **specific product/SKU + scenario** repeatedly | Brand-only mentions without product model |
| `buried_in_pdf` | Facts exist in datasheets/PDFs, not in narrative | **结构化搬运** — translate specs into engineer value (“param X → in scene Y you drop Z”); keep verifiable numbers | Vague “high performance / high reliability” without the buried facts |

## Anchor quality bar

`recommended_anchor` / `anchor_point` must include:

1. Concrete product or model name from the brief (or diagnosis)
2. Verifiable technical mechanism or attribute
3. Tie-back to a diagnosis finding when diagnosis exists

Fail: pure adjectives (“innovator”, “leader”) or channel-as-strategy (“publish a tech article”).

Insufficient data → `[诊断数据不足，建议补充X类诊断]` — never pad with fluff.
