# Campaign Factory

A cloud-run web application that systematizes marketing campaign creation from brief to execution to re-test.

## Overview

Campaign Factory helps ST marketing teams systematically generate AI perception diagnosis-driven campaign plans for any technical topic (SDV, eFuse, SiC, MCU, etc.).

### Workflow

1. **Brief** — Enter campaign topic, target page, products, keywords
2. **Persona & Questions** — AI generates target personas, value propositions, and benchmark questions (with web grounding)
3. **GEO Diagnosis** — Upload AI model diagnosis results from GEO-hub
4. **Campaign Plan** — AI analyzes diagnoses and generates priority matrix, 90-day timeline, and content strategy

## Quick Start

```bash
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker

```bash
docker build -t campaign-factory .
docker run -p 8000:8000 campaign-factory
```

## Environment Variables

- `ANTHROPIC_API_KEY` — Claude API key
- `GOOGLE_CLOUD_PROJECT` — GCP Project ID (for Vertex AI Gemini)
- `DEEPSEEK_API_KEY` — DeepSeek API key
- `DEEPSEEK_BASE_URL` — DeepSeek endpoint (default: `https://api.deepseek.com`)
- `KIMI_API_KEY` — Kimi/Moonshot API key
- `KIMI_BASE_URL` — Kimi endpoint (default: `https://api.moonshot.cn`)
