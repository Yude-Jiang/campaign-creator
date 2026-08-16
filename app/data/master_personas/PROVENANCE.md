# Master Persona Skeletons — Provenance

> **⚠ Status: the provenance fields below are unfilled.**
> Everything in "What these are" and "What depends on them" was derived from the
> code and is accurate. The **Sources** table is not — nobody has recorded where
> m01/m02/m03 actually came from. Whoever authored the skeletons needs to fill it
> in. Until then, treat the skeletons as undocumented expert judgment.

---

## What these are

`m01.json`, `m02.json`, `m03.json` are hand-written audience skeletons. They are
the **only human-authored input** to persona generation — every other field in a
generated persona comes from an LLM.

| Code | label | decision_role | funnel_stage | gate_question |
|------|-------|---------------|--------------|---------------|
| m01 | 外部技术把关型 | `gatekeeper` | `why` | 这个技术方向到底可不可行？ |
| m02 | 内部拍板型 | `decision_maker` | `what` | 选哪个平台、哪家供应商？ |
| m03 | 执行验证型 | `implementer` | `how` | 这个选择好不好用、能不能长期维护？ |

## What depends on them

`app/prompts/{zh,en}/persona_discovery.md` injects the skeletons and instructs
the model to instantiate them. The consequences, in order of how much they
matter:

1. **Hard constraints.** `decision_role`, `funnel_stage`, and
   `channel_map[region].preferred` / `.avoid` are inherited, not invented. These
   are the most trustworthy fields on any generated persona.
2. **Channel-fit warnings.** `avoid_channels` drives
   `check_channel_fit()` in `content_service.py`, which warns when a content
   item targets a channel its audience avoids. A wrong `avoid` list here
   produces wrong warnings — or silently produces none.
3. **The `anchored` badge.** `persona_service.py` sets `basis="anchored"` when a
   persona's `anchor` matches a loaded skeleton code, and the UI shows a green
   chip for it. That badge is a claim of human authorship, and this file is what
   backs it.
4. **Coverage.** The prompt says audiences the skeletons do not cover — notably
   `influencer` (KOLs, analysts, academics) — may be generated freely with an
   empty `anchor`. **There is no skeleton for the influencer tier**, so those
   personas carry no human-authored constraint at all.

Codes are internal. `_scrub_codes()` strips any `m0X` that leaks into a text
field, and `_PERSONA_EXCLUDE_KEYS` removes `anchor` and `basis` from exports.

## Sources — ⚠ TO BE FILLED IN

For each skeleton, record what it is based on. If a field was a judgment call
rather than derived from evidence, write that — "expert judgment, no formal
study" is a legitimate and useful answer. An honest blank is better than an
implied rigor that does not exist.

### m01 · 外部技术把关型

- **Basis** (interviews / win-loss analysis / CRM data / analyst report / expert judgment):
- **Sample or evidence** (how many, which accounts, which region, when):
- **Author**:
- **Last reviewed**:
- **Known limits** (which markets or segments this does *not* describe):

### m02 · 内部拍板型

- **Basis**:
- **Sample or evidence**:
- **Author**:
- **Last reviewed**:
- **Known limits**:

### m03 · 执行验证型

- **Basis**:
- **Sample or evidence**:
- **Author**:
- **Last reviewed**:
- **Known limits**:

### Channel maps

`channel_map` splits into `emea_us` and `china`, selected by campaign language
(`zh` → `china`, otherwise `emea_us`) in `persona_service.py`.

- **Basis for the `china` channel lists**:
- **Basis for the `emea_us` channel lists**:
- **Last reviewed**:

## Schema

`schema_version` is currently `1.0` on all three and is snapshotted into each
campaign as `master_persona_snapshot`, so a campaign records which skeleton
version produced its personas.

**Bump `schema_version` when you change a skeleton's meaning**, not for
typos — existing campaigns keep the old snapshot and stay interpretable.

## Adding a skeleton

1. Add `mNN.json` following the existing shape (`code`, `schema_version`,
   `label`, `decision_role`, `funnel_stage`, `decision_weight`, `gate_question`,
   `jobs_to_be_done`, `pain_point_themes`, `channel_map`,
   `campaign_objective_fit`).
2. Add its Sources section above. `tests/test_regression_guards.py` fails if a
   skeleton file has no entry here.
3. `_load_master_personas()` picks up `m*.json` automatically — no code change.
