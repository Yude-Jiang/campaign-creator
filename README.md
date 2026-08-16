# Campaign Factory

A Cloud Run web application that systematizes marketing campaign creation from brief to execution to re-test.

## Overview

Campaign Factory helps marketing teams systematically generate AI perception diagnosis-driven campaign plans for any technical topic (SDV, eFuse, SiC, MCU, etc.).

### Workflow

The app is a five-tab pipeline. Each tab's output is the next tab's input, and
the campaign's state lives in `data/campaigns/{campaign_id}/campaign.json`.

| Tab | Name | What happens |
|-----|------|--------------|
| 0 | **Brief** | Describe the campaign in natural language; AI parses it into structured fields (topic, industry, products, keywords, competitors, goal). Review and edit before submitting. |
| 1 | **Persona & Questions** | Three-phase LLM pipeline generates target personas (with web grounding), a differentiated value proposition per persona, and the benchmark questions used for diagnosis. |
| 2 | **GEO Diagnosis** | Upload one AI-model diagnosis file per question from GEO-hub. The first upload freezes the question baseline so later diagnoses stay comparable. |
| 3 | **Campaign Plan** | Two-step pipeline analyzes the diagnoses, then produces a priority matrix, competitive landscape, 90-day timeline, and per-priority content strategy. Exportable as Markdown or HTML. |
| 4 | **Content Studio** | Generate channel-specific content from each strategy card (Zhihu, CSDN, Bilibili, WeChat, email, Baidu SEM/feed, LinkedIn, Bing Ads), or add custom content items outside the plan. Copy the composed prompt or generate in place. |

Campaigns run in either Chinese or English; the language is chosen on the
Brief and selects the prompt set for every generation step. It can be changed
later from the top bar.

## Quick Start

Requires Python 3.12+.

```bash
pip install -e ".[dev]"
cp .env.example .env        # then fill in at least one provider key
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Tests and lint

```bash
pytest
ruff check .
```

## Docker

```bash
docker build -t campaign-factory .
docker run -p 8000:8000 --env-file .env campaign-factory
```

The container serves on `$PORT` (default `8080`), which is what Cloud Run sets.

> **Note on persistence:** campaign data is written to the local filesystem
> under `data/`. In a container that directory is ephemeral and is not shared
> between instances, so a multi-instance Cloud Run deployment will lose and
> fragment campaign data. Mount a volume, or pin the service to a single
> instance, until this moves to object storage.

## Environment Variables

At least one model provider must be configured. Tasks are routed per-task with
a primary → secondary → fallback chain (see `TASK_ROUTING` in
`app/services/llm_router.py`), so a missing provider degrades routing rather
than breaking the app.

| Variable | Purpose |
|----------|---------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID — enables Gemini via Vertex AI (uses gcloud ADC). Required for web-grounded persona and question discovery. |
| `GEMINI_API_KEY` | Google AI Studio key — simpler alternative to Vertex AI, used as the Gemini fallback. |
| `DEEPSEEK_API_KEY` | DeepSeek key. |
| `DEEPSEEK_BASE_URL` | DeepSeek endpoint (default `https://api.deepseek.com`). |
| `KIMI_API_KEY` | Kimi / Moonshot key. |
| `KIMI_BASE_URL` | Kimi endpoint (default `https://api.moonshot.cn/v1` — keep the `/v1`). |
| `APP_ENV` | `development` or `production`. |
| `DEFAULT_LANGUAGE` | `zh` or `en`. |
| `DATA_DIR` | Campaign storage root (default `data`). |
