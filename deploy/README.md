# Deploying from Google Cloud Shell

## One-time setup

```bash
# Cloud Shell already has gcloud and git authenticated as you.
gcloud config set project YOUR_PROJECT_ID

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com

git clone https://github.com/Yude-Jiang/campaign-creator.git
cd campaign-creator
chmod +x deploy/deploy.sh
```

### Model credentials

Put the keys in Secret Manager rather than in `--set-env-vars`, so they do not
show up in `gcloud run services describe` output or in deploy logs:

```bash
printf '%s' 'sk-...'  | gcloud secrets create deepseek-api-key --data-file=-
printf '%s' 'sk-...'  | gcloud secrets create kimi-api-key     --data-file=-
printf '%s' 'AIza...' | gcloud secrets create gemini-api-key   --data-file=-   # optional
```

Grant the runtime service account read access:

```bash
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" \
  --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for s in deepseek-api-key kimi-api-key gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role=roles/secretmanager.secretAccessor
done
```

### Gemini via Vertex AI

The Gemini provider prefers Vertex AI with Application Default Credentials, so
the runtime service account needs Vertex access. Without this, Gemini is
skipped and persona/question discovery loses web grounding — silently, because
the router just falls through to the next model.

```bash
gcloud projects add-iam-policy-binding "$(gcloud config get-value project)" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/aiplatform.user
```

Then set `GOOGLE_CLOUD_PROJECT` in `ENV_VARS` (see below) so the provider takes
the Vertex path.

## Updating

```bash
cd campaign-creator
git fetch origin
git checkout claude/project-review-uadnzt     # or main, once merged
git pull

./deploy/deploy.sh
```

The script prints what it is about to do — project, service, region, branch,
commit, instance limits — and asks before proceeding. `--yes` skips the prompt.

Typical invocation with secrets and Vertex:

```bash
SECRETS='DEEPSEEK_API_KEY=deepseek-api-key:latest,KIMI_API_KEY=kimi-api-key:latest' \
ENV_VARS='APP_ENV=production,DEFAULT_LANGUAGE=zh,DATA_DIR=/app/data,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID' \
./deploy/deploy.sh
```

Everything is overridable: `SERVICE`, `REGION`, `PROJECT_ID`, `MIN_INSTANCES`,
`MAX_INSTANCES`, `MEMORY`, `CPU`, `TIMEOUT`, `ENV_VARS`, `SECRETS`.

## Why `max-instances=1`

Campaign data is written to the container's own filesystem
(`app/utils/file_handler.py`), and the write lock is a `threading.Lock`, which
only serialises writers inside a single process.

With more than one instance:

- each instance has its own copy of `data/`, so two people editing the same
  campaign see different content depending on which instance they land on, and
- the lock does not span instances, so concurrent writes overwrite each other.

`min-instances=1` keeps one container warm so the data directory survives
between requests. **This is not durable storage.** A deploy, a crash, or a
platform-initiated restart still discards everything. Use the export endpoints
for anything worth keeping:

```
GET /api/campaigns/{id}/export/all              # full campaign JSON
GET /api/campaigns/{id}/persona/export/md       # personas + VPs + questions
GET /api/campaigns/{id}/plan/export/md
```

The fix is to move storage off the container disk — `app/storage/base.py`
defines the interface for that, with compare-and-swap semantics to replace the
in-process lock. Until a backend is implemented, keep both instance limits at 1.

## Rollback

```bash
gcloud run revisions list --service campaign-factory --region asia-east1 --limit 5
gcloud run services update-traffic campaign-factory --region asia-east1 \
  --to-revisions REVISION_NAME=100
```

## Access

The application has no authentication of its own. If the Cloud Run service
allows unauthenticated invocations, anyone who finds the URL can list every
campaign, read competitor analysis, and spend LLM quota through
`/api/parse-brief`. The deploy script does not change the IAM policy, but it
reports when the service is public.

To require a Google identity:

```bash
gcloud run services remove-iam-policy-binding campaign-factory \
  --region asia-east1 --member=allUsers --role=roles/run.invoker
```

For a team, prefer Identity-Aware Proxy in front of the service over
distributing invoker roles individually.

## Note for users in mainland China

`*.run.app` URLs are not reliably reachable from mainland China. This affects
end users only — the application's own calls to `googleapis.com` (Vertex AI,
Secret Manager) go over Google's network from inside Cloud Run and are not
affected. If the audience is primarily in mainland China, the service needs a
custom domain with a China-reachable path in front of it; that is a separate
piece of work from anything in this directory.
